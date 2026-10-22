"""Run both unit test suites with coverage and record the results."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.getenv("AGENT_REPO_ROOT") or Path(__file__).resolve().parents[2]).resolve()
SUITES = {
    "backend": {
        "cwd": ROOT / "backend",
        "cmd": [sys.executable, "-m", "pytest", "-q", "--cov=app", "--cov-report=json"],
        "summary": ROOT / "backend/coverage/coverage.json",
    },
    "frontend": {
        "cwd": ROOT / "frontend",
        "cmd": ["npx", "--no-install", "vitest", "run", "--coverage"],
        "summary": ROOT / "frontend/coverage/coverage-summary.json",
    },
}


def line_coverage(suite: str, summary: Path) -> float | None:
    """Read the total line coverage percentage from a coverage summary file."""
    if not summary.is_file():
        return None
    data = json.loads(summary.read_text(encoding="utf-8"))
    if suite == "backend":
        return round(data["totals"]["percent_covered"], 2)
    return round(data["total"]["lines"]["pct"], 2)


def run_suite(suite: str) -> dict:
    """Run one suite and return its status, coverage and output tail."""
    spec = SUITES[suite]
    spec["summary"].unlink(missing_ok=True)
    proc = subprocess.run(
        spec["cmd"], cwd=spec["cwd"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", shell=sys.platform == "win32",
    )
    output = (proc.stdout + proc.stderr).splitlines()
    return {
        "passed": proc.returncode == 0,
        "coverage": line_coverage(suite, spec["summary"]),
        "output_tail": "\n".join(output[-40:]),
    }


def main() -> int:
    """Append the results of one verification stage to the output file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["before", "after"], required=True)
    parser.add_argument("--out", default=".agent/verify.json")
    args = parser.parse_args()

    out = Path(args.out)
    results = json.loads(out.read_text(encoding="utf-8")) if out.is_file() else {}
    results[args.stage] = {suite: run_suite(suite) for suite in SUITES}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    for suite, result in results[args.stage].items():
        print(f"{args.stage} {suite}: passed={result['passed']} coverage={result['coverage']}")
    return 0 if all(r["passed"] for r in results[args.stage].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
