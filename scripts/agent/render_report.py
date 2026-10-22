"""Render the agent report, guard result and verification into a PR comment."""

import argparse
import json
import sys
from pathlib import Path

MARKER = "<!-- unit-test-agent-report -->"
ACTIONS = {"create", "update", "skip"}
MAX_TEXT = 500


def load(path: Path) -> dict | None:
    """Load a JSON file, returning None if it is missing or invalid."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def clean(value, limit: int = MAX_TEXT) -> str:
    """Make untrusted text safe for a Markdown table cell."""
    text = " ".join(str(value or "").split())
    text = text.replace("<", "&lt;").replace(">", "&gt;").replace("|", "\\|")
    text = text.replace("@", "@​")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def validate(report) -> list[str]:
    """Return structural problems in the agent report."""
    if not isinstance(report, dict):
        return ["report is missing or is not a JSON object"]
    problems = []
    if not isinstance(report.get("summary"), str):
        problems.append("summary must be a string")
    for key in ("decisions", "test_runs", "findings"):
        if not isinstance(report.get(key), list):
            problems.append(f"{key} must be a list")
    for d in report.get("decisions") or []:
        if not isinstance(d, dict) or d.get("action") not in ACTIONS or not d.get("source"):
            problems.append(f"invalid decision: {clean(d, 120)}")
    return problems


def coverage_row(suite: str, verify: dict) -> str:
    """Return one table row comparing coverage before and after the agent."""
    before = verify.get("before", {}).get(suite, {})
    after = verify.get("after", {}).get(suite, {})
    status = "✅ passed" if after.get("passed") else "❌ failed"

    def fmt(value):
        return "n/a" if value is None else f"{value:.1f}%"

    delta = ""
    if before.get("coverage") is not None and after.get("coverage") is not None:
        delta = f" ({after['coverage'] - before['coverage']:+.1f})"
    return f"| {suite} | {status} | {fmt(before.get('coverage'))} | {fmt(after.get('coverage'))}{delta} |"


def render(args) -> str:
    """Build the full Markdown comment."""
    report = load(args.dir / "report.json")
    guard = load(args.dir / "guard.json") or {"accepted": [], "rejected": []}
    verify = load(args.dir / "verify.json") or {}
    problems = validate(report)
    verified = bool(verify.get("after")) and all(r.get("passed") for r in verify["after"].values())

    if args.agent_outcome != "success":
        headline = f"⚠️ The agent did not finish (`{clean(args.agent_outcome, 40)}`). No tests were committed."
    elif not guard["accepted"]:
        headline = "ℹ️ No test changes were needed or accepted."
    elif verified and args.committed:
        headline = f"✅ Added or updated {len(guard['accepted'])} test file(s) and committed them to this branch."
    elif verified:
        headline = f"✅ {len(guard['accepted'])} test file(s) pass verification but were not committed."
    else:
        headline = "❌ Generated tests failed verification. Nothing was committed."

    out = [MARKER, "## 🧪 Unit test agent", "", headline, ""]
    out.append(f"<sub>Model: `{clean(args.model, 60)}` · Commit: `{clean(args.sha, 12)[:12]}`</sub>")

    if report and not problems:
        out += ["", "### Summary", "", clean(report["summary"], 1000)]
        out += ["", "### Decisions", "", "| Source | Action | Test file | Reason |", "|---|---|---|---|"]
        for d in report["decisions"]:
            test_file = f"`{clean(d.get('test_file'), 120)}`" if d.get("test_file") else "-"
            out.append(f"| `{clean(d['source'], 120)}` | {d['action']} | {test_file} | {clean(d.get('reason'))} |")
        if report["test_runs"]:
            out += ["", "### Agent test runs", "", "| Suite | Result | Notes |", "|---|---|---|"]
            for r in report["test_runs"]:
                if isinstance(r, dict):
                    result = "passed" if r.get("passed") else "failed"
                    out.append(f"| {clean(r.get('suite'), 20)} | {result} | {clean(r.get('notes'))} |")
        if report["findings"]:
            out += ["", "### Findings for reviewers", ""]
            out += [f"- {clean(f)}" for f in report["findings"]]
    else:
        out += ["", "### Report", "", "The agent report is invalid:", ""]
        out += [f"- {clean(p)}" for p in problems]

    if guard["rejected"]:
        out += ["", "### Rejected changes", "", "| File | Reason |", "|---|---|"]
        out += [f"| `{clean(r['path'], 120)}` | {clean(r['reason'])} |" for r in guard["rejected"]]

    if verify.get("after"):
        out += [
            "",
            "### Verification (clean run, no secrets)",
            "",
            "| Suite | Tests | Line coverage before | Line coverage after |",
            "|---|---|---|---|",
        ]
        out += [coverage_row(s, verify) for s in verify["after"]]

    if args.run_url:
        out += ["", f"[Workflow run]({args.run_url})"]
    return "\n".join(out) + "\n"


def main() -> int:
    """Write the rendered comment to a file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=Path(".agent"))
    parser.add_argument("--out", type=Path, default=Path(".agent/comment.md"))
    parser.add_argument("--agent-outcome", default="success")
    parser.add_argument("--model", default="unknown")
    parser.add_argument("--sha", default="")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--committed", action="store_true")
    args = parser.parse_args()
    args.out.write_text(render(args), encoding="utf-8")
    print(args.out.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
