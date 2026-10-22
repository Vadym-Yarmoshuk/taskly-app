"""Accept only safe test-file changes from the agent and export them as a patch.

By default the script only reports. With --revert it also restores or deletes
every rejected change; use that only in a disposable CI checkout.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ALLOWED = [
    re.compile(r"^backend/tests/([A-Za-z0-9_]+/)*(test_[A-Za-z0-9_]+|conftest|__init__)\.py$"),
    re.compile(r"^frontend/src/([A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.test\.tsx?$"),
]
IGNORED_PREFIXES = (".agent/",)
ASSERTION = re.compile(r"^\s*(assert\b|expect\(|await expect\()")
FORBIDDEN_CODE = re.compile(
    r"\b(it|test|describe)\.(skip|only|todo)\b"
    r"|\bx(it|describe)\("
    r"|\bpytest\.mark\.(skip|skipif|xfail)\b"
    r"|\bpytest\.(skip|xfail)\("
)


def git(*args: str) -> str:
    """Run a git command and return its standard output."""
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout


def changed_paths() -> list[tuple[str, str]]:
    """Return (status, path) for every changed or untracked file."""
    entries = git("status", "--porcelain=v1", "-z", "--untracked-files=all").split("\0")
    return [(e[:2], e[3:]) for e in entries if e]


def added_lines(status: str, path: str) -> str:
    """Return the lines the agent added to a file."""
    if status == "??":
        return Path(path).read_text(encoding="utf-8")
    diff = git("diff", "HEAD", "--", path)
    return "\n".join(l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))


def removed_assertions(status: str, path: str) -> list[str]:
    """Return existing assertion lines that the change removes or rewrites."""
    if status == "??":
        return []
    removed, added = [], set()
    for line in git("diff", "HEAD", "--", path).splitlines():
        if line.startswith("-") and not line.startswith("---") and ASSERTION.match(line[1:]):
            removed.append(line[1:].strip())
        elif line.startswith("+") and not line.startswith("+++"):
            added.add(line[1:].strip())
    return [line for line in removed if line not in added]


def revert(status: str, path: str) -> None:
    """Restore a file to its committed state, or delete it if it is new."""
    if status == "??":
        Path(path).unlink(missing_ok=True)
    else:
        git("checkout", "HEAD", "--", path)


def review(status: str, path: str) -> str | None:
    """Return the rejection reason for a change, or None if it is accepted."""
    if not any(p.match(path) for p in ALLOWED):
        return "not a unit test file"
    if "D" in status:
        return "deleting test files is not allowed"
    if FORBIDDEN_CODE.search(added_lines(status, path)):
        return "adds skipped, focused or expected-to-fail tests"
    if removed := removed_assertions(status, path):
        return f"removes existing assertions: {removed[0][:80]}"
    return None


def main() -> int:
    """Review changes, write the guard result and the accepted patch."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", default=".agent")
    parser.add_argument("--revert", action="store_true", help="restore or delete rejected changes")
    args = parser.parse_args()

    accepted, rejected = [], []
    for status, path in changed_paths():
        if path.startswith(IGNORED_PREFIXES):
            continue
        reason = review(status, path)
        if reason:
            if args.revert:
                revert(status, path)
            rejected.append({"path": path, "reason": reason})
        else:
            accepted.append(path)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    patch = ""
    if accepted:
        git("add", "--intent-to-add", "--", *accepted)
        patch = git("diff", "--binary", "--", *accepted)
        git("reset", "-q", "--", *accepted)
    (out_dir / "tests.patch").write_text(patch, encoding="utf-8")
    result = {"accepted": accepted, "rejected": rejected}
    (out_dir / "guard.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
