"""Minimal tool-calling agent runtime for the Gemini API.

Loads an agent definition (Markdown with YAML front matter) and Agent Skills
(SKILL.md), then runs a request-bounded tool loop. Every tool enforces its own
access rules, so the model cannot act outside them.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(os.getenv("AGENT_REPO_ROOT") or Path(__file__).resolve().parents[2]).resolve()
RUNNER_SCRIPT = Path(__file__).resolve().with_name("run-tests.sh")
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_FILE_CHARS = 40_000
WRITABLE = [
    re.compile(r"^backend/tests/([A-Za-z0-9_]+/)*(test_[A-Za-z0-9_]+|conftest|__init__)\.py$"),
    re.compile(r"^frontend/src/([A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.test\.tsx?$"),
]
REFERENCE_FILES = {
    "backend": ["backend/tests/conftest.py", "backend/tests/mocks.py"],
    "frontend": ["frontend/src/test/setup.ts", "frontend/src/test/todoFixture.ts",
                 "frontend/src/features/todos/types.ts", "frontend/src/features/todos/api/queryKeys.ts"],
}
UNREADABLE = re.compile(r"(^|/)(\.env(\..*)?|\.git|node_modules|\.venv|__pycache__)(/|$)")
TRANSIENT_STATUS = {429, 500, 503, 504}
MAX_ATTEMPTS = 4
MAX_RETRY_DELAY = 90


class ToolError(Exception):
    """A tool call was rejected or failed; the message is returned to the model."""


class QuotaExhausted(Exception):
    """Every configured model is out of quota or unavailable."""


def parse_front_matter(text: str) -> tuple[dict, str]:
    """Split a Markdown document into simple YAML front matter and body."""
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text.replace("\r\n", "\n"), re.S)
    if not match:
        return {}, text
    meta, key = {}, None
    for line in match.group(1).splitlines():
        if item := re.match(r"^\s+-\s+(.+)$", line):
            meta.setdefault(key, []).append(item.group(1).strip())
        elif pair := re.match(r"^([A-Za-z_]+):\s*(.*)$", line):
            key, value = pair.groups()
            meta[key] = value.strip() if value.strip() else []
    return meta, match.group(2).strip()


def load_skills(skills_dir: Path) -> dict[str, dict]:
    """Load every SKILL.md below a directory, keyed by skill name."""
    skills = {}
    for path in sorted(skills_dir.glob("*/SKILL.md")):
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        skills[meta.get("name", path.parent.name)] = {"description": meta.get("description", ""), "body": body}
    return skills


def repo_path(path: str) -> tuple[Path, str]:
    """Resolve a repository-relative path and reject anything outside the repository."""
    relative = str(path).replace("\\", "/").lstrip("/")
    resolved = (ROOT / relative).resolve()
    if ROOT != resolved and ROOT not in resolved.parents:
        raise ToolError(f"Path is outside the repository: {path}")
    return resolved, resolved.relative_to(ROOT).as_posix()


class Tools:
    """Tool implementations exposed to the model."""

    def __init__(self, skills: dict, allowed: list[str]):
        self.skills = skills
        self.allowed = allowed
        self.report = None
        self.written: set[str] = set()

    def declarations(self) -> list[dict]:
        """Return Gemini function declarations for the allowed tools."""
        string = {"type": "STRING"}
        all_tools = {
            "activate_skill": ("Load the full instructions of a skill.", {"name": string}, ["name"]),
            "read_file": ("Read a text file from the repository.", {"path": string}, ["path"]),
            "list_files": (
                "List repository files that match a glob pattern, for example frontend/src/**/*.test.tsx.",
                {"pattern": string}, ["pattern"],
            ),
            "write_file": (
                "Create or overwrite a unit test file. Only backend/tests/**/test_*.py, conftest.py, "
                "__init__.py and frontend/src/**/*.test.ts(x) are writable.",
                {"path": string, "content": string}, ["path", "content"],
            ),
            "replace_in_file": (
                "Replace one exact, unique occurrence of text in a writable unit test file.",
                {"path": string, "old_text": string, "new_text": string}, ["path", "old_text", "new_text"],
            ),
            "run_tests": (
                "Run unit tests. suite is backend or frontend; paths are relative to the suite "
                "directory (tests/... or src/...). Empty paths run the whole suite.",
                {"suite": {"type": "STRING", "enum": ["backend", "frontend"]},
                 "paths": {"type": "ARRAY", "items": string}},
                ["suite"],
            ),
            "finish": (
                "Submit the final report and end the run. Call exactly once, last.",
                {
                    "summary": string,
                    "decisions": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                        "source": string,
                        "action": {"type": "STRING", "enum": ["create", "update", "skip"]},
                        "test_file": string,
                        "reason": string,
                    }, "required": ["source", "action", "reason"]}},
                    "test_runs": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                        "suite": string, "command": string, "passed": {"type": "BOOLEAN"}, "notes": string,
                    }, "required": ["suite", "passed"]}},
                    "findings": {"type": "ARRAY", "items": string},
                },
                ["summary", "decisions", "test_runs", "findings"],
            ),
        }
        return [
            {"name": name, "description": desc,
             "parameters": {"type": "OBJECT", "properties": props, "required": required}}
            for name, (desc, props, required) in all_tools.items()
            if name in self.allowed
        ]

    def call(self, name: str, args: dict) -> dict:
        """Run one tool call and return its JSON-serializable result."""
        if name not in self.allowed:
            raise ToolError(f"Tool not allowed: {name}")
        return getattr(self, f"tool_{name}")(**args)

    def tool_activate_skill(self, name: str) -> dict:
        """Return the instructions of one skill."""
        if name not in self.skills:
            raise ToolError(f"Unknown skill: {name}. Available: {', '.join(self.skills)}")
        return {"skill": name, "instructions": self.skills[name]["body"]}

    def tool_read_file(self, path: str) -> dict:
        """Return the content of a readable repository file."""
        resolved, relative = repo_path(path)
        if UNREADABLE.search(relative):
            raise ToolError(f"File is not readable: {relative}")
        if not resolved.is_file():
            raise ToolError(f"File not found: {relative}")
        content = resolved.read_text(encoding="utf-8", errors="replace")
        return {"path": relative, "content": content[:MAX_FILE_CHARS]}

    def tool_list_files(self, pattern: str) -> dict:
        """Return readable repository files that match a glob pattern."""
        if ".." in pattern:
            raise ToolError("Pattern must not contain '..'")
        matches = sorted(
            p.relative_to(ROOT).as_posix() for p in ROOT.glob(pattern)
            if p.is_file() and not UNREADABLE.search(p.relative_to(ROOT).as_posix())
        )
        return {"files": matches[:200]}

    def _writable(self, path: str) -> Path:
        """Resolve a path and reject it unless it is a unit test file."""
        resolved, relative = repo_path(path)
        if not any(p.match(relative) for p in WRITABLE):
            raise ToolError(f"Only unit test files are writable, not: {relative}")
        self.written.add(relative)
        return resolved

    def tool_write_file(self, path: str, content: str) -> dict:
        """Create or overwrite a unit test file."""
        resolved = self._writable(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8", newline="\n")
        return {"written": path, "bytes": len(content.encode())}

    def tool_replace_in_file(self, path: str, old_text: str, new_text: str) -> dict:
        """Replace one unique text fragment in a unit test file."""
        resolved = self._writable(path)
        if not resolved.is_file():
            raise ToolError(f"File not found: {path}")
        content = resolved.read_text(encoding="utf-8")
        count = content.count(old_text)
        if count != 1:
            raise ToolError(f"old_text must occur exactly once; found {count} occurrences")
        resolved.write_text(content.replace(old_text, new_text), encoding="utf-8", newline="\n")
        return {"replaced_in": path}

    def tool_run_tests(self, suite: str, paths: list | None = None) -> dict:
        """Run unit tests through the sandboxed runner script."""
        paths = [normalize_test_path(suite, p) for p in paths or []]
        command = [shutil.which("bash") or "bash", str(RUNNER_SCRIPT), suite, *paths]
        try:
            proc = subprocess.run(
                command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=600, env=sandbox_env(),
            )
        except subprocess.TimeoutExpired:
            raise ToolError("Test run timed out after 600 seconds")
        return {
            "command": " ".join(["run-tests.sh", suite, *paths]),
            "exit_code": proc.returncode,
            "output": (proc.stdout + proc.stderr)[-6000:],
        }

    def tool_finish(self, **report) -> dict:
        """Store the final report and end the run."""
        self.report = report
        return {"status": "accepted"}


def normalize_test_path(suite: str, path: str) -> str:
    """Convert a repository-relative or partial test path to a suite-relative one."""
    path = str(path).replace("\\", "/").lstrip("./")
    path = path.removeprefix(f"{suite}/")
    top = "tests/" if suite == "backend" else "src/"
    return path if path.startswith(top) else top + path


def sandbox_env() -> dict:
    """Return the environment for test runs, without credentials."""
    secret = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIALS)", re.I)
    return {k: v for k, v in os.environ.items() if not secret.search(k)}


def quota_info(error: dict) -> tuple[bool, int]:
    """Return whether an API error is a daily quota and the suggested retry delay in seconds."""
    details = (error.get("error") or {}).get("details") or []
    daily, delay = False, 0
    for detail in details:
        for violation in detail.get("violations", []):
            daily = daily or "PerDay" in violation.get("quotaId", "")
        if match := re.match(r"^(\d+)", detail.get("retryDelay", "")):
            delay = int(match.group(1)) + 1
    return daily, delay


class Gemini:
    """Gemini generateContent client with per-model fallback on quota errors."""

    def __init__(self, api_key: str, models: list[str], temperature: float):
        self.api_key = api_key
        self.models = list(models)
        self.temperature = temperature
        self.usage: list[dict] = []

    def generate(self, system: str, contents: list, tools: list, only: str | None = None) -> dict:
        """Send one request, moving to the next model when one is exhausted.

        With ``only`` set, the model must call that single function.
        """
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "tools": [{"functionDeclarations": tools}],
            "generationConfig": {"temperature": self.temperature},
        }
        if only:
            body["toolConfig"] = {"functionCallingConfig": {"mode": "ANY", "allowedFunctionNames": [only]}}
        while self.models:
            model = self.models[0]
            for attempt in range(MAX_ATTEMPTS):
                status, data = self._post(model, body)
                if status == 200:
                    self.usage.append({"model": model, **data.get("usageMetadata", {})})
                    return data
                if status not in TRANSIENT_STATUS:
                    raise RuntimeError(f"{model}: HTTP {status}: {json.dumps(data)[:500]}")
                daily, delay = quota_info(data)
                print(f"[agent] {model}: HTTP {status}, attempt {attempt + 1}, retry in {delay}s", file=sys.stderr)
                if daily or delay > MAX_RETRY_DELAY:
                    break
                time.sleep(delay or 10 * (attempt + 1))
            print(f"[agent] switching away from {model}", file=sys.stderr)
            self.models.pop(0)
        raise QuotaExhausted("All configured models are out of quota or unavailable")

    def _post(self, model: str, body: dict) -> tuple[int, dict]:
        """POST one request and return the status code and JSON body."""
        request = urllib.request.Request(
            API_URL.format(model=model), data=json.dumps(body).encode(),
            headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.load(error)
            except ValueError:
                return error.code, {}
        except (urllib.error.URLError, TimeoutError) as error:
            return 503, {"error": str(error)}


def build_system_prompt(agent_body: str, skills: dict) -> str:
    """Combine the agent instructions with the skill catalogue."""
    catalogue = "\n".join(f"- `{name}`: {s['description']}" for name, s in skills.items())
    return (
        f"{agent_body}\n\n## Available skills\n\nActivate a skill with `activate_skill` "
        f"before the step it covers. You may call several tools in one turn.\n\n{catalogue}\n"
    )


def example_test(entry: dict) -> str | None:
    """Return an existing test file near the expected test, as a style example."""
    if entry.get("test_exists"):
        return None
    directory = (ROOT / entry["expected_test"]).parent
    pattern = "test_*.py" if entry["suite"] == "backend" else "*.test.ts*"
    while ROOT in directory.parents:
        if candidates := sorted(directory.glob(pattern)):
            return candidates[0].relative_to(ROOT).as_posix()
        directory = directory.parent
    return None


def build_task(context_path: Path) -> str:
    """Build the first user message: change context plus the files the agent needs."""
    context = json.loads(context_path.with_suffix(".json").read_text(encoding="utf-8"))
    suites = {e["suite"] for e in context["files"] if "suite" in e}
    paths = [p for suite in sorted(suites) for p in REFERENCE_FILES[suite]]
    for entry in context["files"]:
        if entry["status"] != "D":
            paths.append(entry["path"])
        if "expected_test" in entry:
            paths += [entry["expected_test"], example_test(entry)]
    parts = [context_path.read_text(encoding="utf-8"), "\n# File contents\n"]
    for path in dict.fromkeys(p for p in paths if p):
        if (ROOT / path).is_file():
            text = (ROOT / path).read_text(encoding="utf-8", errors="replace")[:MAX_FILE_CHARS]
            parts += [f"\n## `{path}`\n", "```", text, "```"]
    parts.append("\nThese files are already loaded; do not read them again. "
                 "Process this change now and end with the `finish` tool.")
    return "\n".join(parts)


def run(args) -> int:
    """Run the agent loop and write the report and run log."""
    meta, body = parse_front_matter(args.agent.read_text(encoding="utf-8"))
    skills = load_skills(args.skills)
    tools = Tools(skills, meta.get("tools") or [])
    client = Gemini(os.environ["GEMINI_API_KEY"], args.models, float(meta.get("temperature", 0.2)))
    system = build_system_prompt(body, skills)
    contents = [{"role": "user", "parts": [{"text": build_task(args.context)}]}]
    max_requests = int(meta.get("max_requests", 12))
    log, outcome = [], "request_budget_exhausted"

    for request_no in range(1, max_requests + 1):
        remaining = max_requests - request_no
        try:
            data = client.generate(system, contents, tools.declarations(), only="finish" if remaining == 0 else None)
        except QuotaExhausted as error:
            outcome = "quota_exhausted"
            log.append({"request": request_no, "error": str(error)})
            break
        candidate = (data.get("candidates") or [{}])[0]
        content = candidate.get("content") or {"role": "model", "parts": []}
        content["role"] = "model"
        contents.append(content)
        calls = [p["functionCall"] for p in content.get("parts", []) if "functionCall" in p]
        log.append({"request": request_no, "model": client.usage[-1]["model"], "tools": [c["name"] for c in calls]})
        if not calls:
            contents.append({"role": "user", "parts": [{"text": "Use the tools. End the run with `finish`."}]})
            continue
        responses = []
        for call in calls:
            try:
                result = tools.call(call["name"], call.get("args") or {})
            except ToolError as error:
                result = {"error": str(error)}
            except TypeError as error:
                result = {"error": f"Invalid arguments: {error}"}
            print(f"[agent] #{request_no} {call['name']} -> {json.dumps(result)[:160]}", file=sys.stderr)
            responses.append({"functionResponse": {"name": call["name"], "response": result}})
        if tools.report is not None:
            outcome = "success"
            break
        if remaining <= 2:
            responses.append({"text": f"Only {remaining} request(s) left. Wrap up and call `finish`."})
        contents.append({"role": "user", "parts": responses})

    args.out_dir.mkdir(parents=True, exist_ok=True)
    if tools.report is not None:
        (args.out_dir / "report.json").write_text(json.dumps(tools.report, indent=2), encoding="utf-8")
    run_log = {"outcome": outcome, "requests": log, "usage": client.usage, "written": sorted(tools.written)}
    (args.out_dir / "agent-run.json").write_text(json.dumps(run_log, indent=2), encoding="utf-8")
    models = sorted({u["model"] for u in client.usage}) or ["none"]
    if github_output := os.getenv("GITHUB_OUTPUT"):
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write(f"outcome={outcome}\nmodel={','.join(models)}\n")
    print(f"[agent] outcome={outcome} requests={len(client.usage)} models={','.join(models)}", file=sys.stderr)
    return 0 if outcome == "success" else 1


def main() -> int:
    """Parse arguments and run the agent."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", type=Path, default=ROOT / ".gemini/agents/unit-test-agent.md")
    parser.add_argument("--skills", type=Path, default=ROOT / ".gemini/skills")
    parser.add_argument("--context", type=Path, default=ROOT / ".agent/context.md")
    parser.add_argument("--out-dir", type=Path, default=ROOT / ".agent")
    parser.add_argument(
        "--models", nargs="+",
        default=os.getenv("AGENT_MODELS", "gemini-3-flash-preview gemini-3.6-flash gemini-3.8-flash gemini-3.5-flash gemini-3.5-flash-lite gemini-3.1-flash-lite").split(),
    )
    return run(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
