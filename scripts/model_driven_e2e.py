from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


_HTTP_STATUS_RE = re.compile(r"\bHTTP\s+(\d{3})\b")
_NON_SLUG_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class RunResult:
    index: int
    ok: bool
    returncode: int
    elapsed_s: float
    failure_kind: str | None
    failing_tests: list[str]
    stdout_head: str
    stdout_tail: str
    stderr_head: str
    stderr_tail: str


def _now_utc_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _trim(text: str, *, head: int = 6000, tail: int = 6000) -> tuple[str, str]:
    if len(text) <= head + tail:
        return text, ""
    return text[:head], text[-tail:]


def _extract_http_status(text: str) -> int | None:
    m = _HTTP_STATUS_RE.search(text)
    if m is None:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def _classify_failure(stdout: str, stderr: str) -> str:
    blob = f"{stdout}\n{stderr}"

    code = _extract_http_status(blob)
    if code in (408, 409, 425, 429, 500, 502, 503, 504):
        return "network"

    network_markers = (
        "TimeoutError",
        "ReadTimeout",
        "ConnectTimeout",
        "timed out",
        "ConnectionError",
        "NameResolutionError",
        "Temporary failure in name resolution",
        "Failed to establish a new connection",
        "RemoteDisconnected",
        "TLSV",
        "SSLError",
    )
    if any(m in blob for m in network_markers):
        return "network"

    model_markers = (
        "model did not complete",
        "did not complete",
        "did not prompt",
        "did not prompt+allow",
        "did not complete the",
    )
    if any(m in blob for m in model_markers):
        return "model"

    return "regression"


def _parse_failing_tests(stdout: str, stderr: str) -> list[str]:
    failing: list[str] = []
    for line in (stdout + "\n" + stderr).splitlines():
        s = line.strip()
        if s.startswith("FAIL: ") or s.startswith("ERROR: "):
            failing.append(s)
    return failing


def _aggregate_failure_tests(run_results: list[RunResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in run_results:
        if r.ok:
            continue
        for t in r.failing_tests:
            counts[t] = counts.get(t, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def _run_unittest_suite(*, suite: str, timeout_s: float) -> tuple[int, float, str, str]:
    cmd = [sys.executable, "-m", "unittest", "-v", suite]
    start = time.perf_counter()
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=max(1.0, timeout_s))
    elapsed = time.perf_counter() - start
    return p.returncode, elapsed, p.stdout or "", p.stderr or ""


def _default_report_dir() -> Path:
    root = Path.cwd()
    return root / ".openagentic_e2e_reports" / _now_utc_compact()


def _suite_slug(suite: str) -> str:
    s = suite.strip() or "suite"
    s = _NON_SLUG_CHARS_RE.sub("-", s)
    s = s.replace("/", "-").replace("\\", "-")
    s = s.strip("-")
    return s or "suite"


def _write_report(dir_path: Path, *, payload: dict) -> tuple[Path, Path]:
    dir_path.mkdir(parents=True, exist_ok=True)
    json_path = dir_path / "run_report.json"
    md_path = dir_path / "run_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines: list[str] = []
    lines.append("# Model-Driven E2E Report\n")
    lines.append(f"- Timestamp (UTC): `{payload.get('timestamp_utc')}`\n")
    lines.append(f"- Suite: `{payload.get('suite')}`\n")
    lines.append(f"- Runs: `{payload.get('runs')}`\n")
    lines.append(f"- Passes: `{payload.get('passes')}`\n")
    lines.append(f"- Pass rate: `{payload.get('pass_rate')}`\n")
    lines.append(f"- Verdict: `{payload.get('verdict')}`\n")
    lines.append("\n## Failure Breakdown\n")
    for k in ("network", "model", "regression"):
        lines.append(f"- {k}: `{payload.get('failures', {}).get(k, 0)}`\n")

    lines.append("\n## Runs\n")
    for r in payload.get("run_results", []):
        idx = r.get("index")
        ok = r.get("ok")
        kind = r.get("failure_kind")
        elapsed = r.get("elapsed_s")
        lines.append(f"- run {idx}: ok=`{ok}` kind=`{kind}` elapsed_s=`{elapsed}`\n")
        failing_tests = r.get("failing_tests") or []
        if failing_tests:
            lines.append("  - failing_tests:\n")
            for t in failing_tests[:10]:
                lines.append(f"    - `{t}`\n")

    counts = payload.get("failure_test_counts") or {}
    if isinstance(counts, dict) and counts:
        lines.append("\n## Failing Test Frequency\n")
        for k, v in list(counts.items())[:30]:
            lines.append(f"- `{v}` × `{k}`\n")

    md_path.write_text("".join(lines), encoding="utf-8")
    return json_path, md_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Model-driven E2E runner (pass-rate gate + failure triage).")
    ap.add_argument("--suite", default="e2e_tests.smoke_core", help="unittest module name (default: e2e_tests.smoke_core)")
    ap.add_argument("--runs", type=int, default=3, help="number of independent runs (default: 3)")
    ap.add_argument("--min-pass-rate", type=float, default=1.0, help="quality gate threshold (default: 1.0)")
    ap.add_argument("--timeout-s", type=float, default=900.0, help="per-run timeout seconds (default: 900)")
    ap.add_argument("--report-dir", default="", help="directory to write reports (default: .openagentic_e2e_reports/<ts>)")
    args = ap.parse_args()

    runs = max(1, int(args.runs))
    suite = str(args.suite).strip()
    timeout_s = max(1.0, float(args.timeout_s))
    min_pass_rate = min(1.0, max(0.0, float(args.min_pass_rate)))

    report_dir = Path(args.report_dir) if str(args.report_dir).strip() else _default_report_dir()
    if not str(args.report_dir).strip():
        # Avoid collisions when multiple runners execute concurrently (e.g., in parallel).
        report_dir = report_dir.with_name(f"{report_dir.name}-{_suite_slug(suite)}-pid{os.getpid()}")

    run_results: list[RunResult] = []
    failures = {"network": 0, "model": 0, "regression": 0}

    for i in range(1, runs + 1):
        rc, elapsed, out, err = _run_unittest_suite(suite=suite, timeout_s=timeout_s)
        ok = rc == 0
        kind: str | None = None
        failing_tests: list[str] = []
        if not ok:
            kind = _classify_failure(out, err)
            failures[kind] += 1
            failing_tests = _parse_failing_tests(out, err)

        out_head, out_tail = _trim(out)
        err_head, err_tail = _trim(err)
        run_results.append(
            RunResult(
                index=i,
                ok=ok,
                returncode=rc,
                elapsed_s=round(elapsed, 3),
                failure_kind=kind,
                failing_tests=failing_tests,
                stdout_head=out_head,
                stdout_tail=out_tail,
                stderr_head=err_head,
                stderr_tail=err_tail,
            )
        )

    passes = sum(1 for r in run_results if r.ok)
    pass_rate = passes / runs
    verdict = "pass" if pass_rate >= min_pass_rate else "fail"
    failure_test_counts = _aggregate_failure_tests(run_results)

    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "suite": suite,
        "runs": runs,
        "passes": passes,
        "pass_rate": round(pass_rate, 4),
        "min_pass_rate": min_pass_rate,
        "verdict": verdict,
        "failures": failures,
        "failure_test_counts": failure_test_counts,
        "env": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "cwd": str(Path.cwd()),
            "has_http_proxy": bool(os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")),
            "has_https_proxy": bool(os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")),
        },
        "run_results": [asdict(r) for r in run_results],
    }

    json_path, md_path = _write_report(report_dir, payload=payload)

    print(f"Suite: {suite}")
    print(f"Runs: {runs}  Passes: {passes}  Pass rate: {pass_rate:.3f}  Gate: >= {min_pass_rate:.3f}  Verdict: {verdict}")
    print(f"Failures: network={failures['network']} model={failures['model']} regression={failures['regression']}")
    print(f"Report: {json_path}")
    print(f"Report: {md_path}")

    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

