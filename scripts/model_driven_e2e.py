from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_HTTP_STATUS_RE = re.compile(r"\bHTTP\s+(\d{3})\b")
_NON_SLUG_CHARS_RE = re.compile(r"[^A-Za-z0-9._-]+")
_FAIL_OR_ERROR_RE = re.compile(r"^(FAIL|ERROR):\s+.+?\s+\((?P<test_id>[^)]+)\)\s*$")


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


@dataclass(frozen=True)
class RerunResult:
    run_index: int
    test_id: str
    attempt: int
    ok: bool
    returncode: int
    elapsed_s: float
    failure_kind: str | None
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
        "did not rewrite",
        "did not recover",
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


def _parse_failing_test_ids(stdout: str, stderr: str) -> list[str]:
    ids: list[str] = []
    for line in (stdout + "\n" + stderr).splitlines():
        m = _FAIL_OR_ERROR_RE.match(line.strip())
        if m:
            ids.append(m.group("test_id"))
    # Preserve order but de-dup.
    seen: set[str] = set()
    out: list[str] = []
    for tid in ids:
        if tid in seen:
            continue
        seen.add(tid)
        out.append(tid)
    return out


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


def _run_unittest_test_id(*, test_id: str, timeout_s: float) -> tuple[int, float, str, str]:
    cmd = [sys.executable, "-m", "unittest", "-v", test_id]
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

    required_passes = payload.get("required_passes")
    allowed_failures = payload.get("allowed_failures")
    if required_passes is not None and allowed_failures is not None:
        lines.append(f"- Gate budget: required_passes=`{required_passes}` allowed_failures=`{allowed_failures}`\n")
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

    reruns = payload.get("rerun_results") or []
    if isinstance(reruns, list) and reruns:
        lines.append("\n## Reruns (Failing Tests)\n")
        for rr in reruns[:60]:
            run_idx = rr.get("run_index")
            tid = rr.get("test_id")
            att = rr.get("attempt")
            ok = rr.get("ok")
            kind = rr.get("failure_kind")
            elapsed = rr.get("elapsed_s")
            lines.append(f"- run {run_idx} test=`{tid}` attempt=`{att}` ok=`{ok}` kind=`{kind}` elapsed_s=`{elapsed}`\n")

    flake = payload.get("flake_test_counts") or {}
    persistent = payload.get("persistent_test_counts") or {}
    if isinstance(flake, dict) and flake:
        lines.append("\n## Flake Summary\n")
        for k, v in list(flake.items())[:30]:
            lines.append(f"- flaky `{v}` × `{k}`\n")
    if isinstance(persistent, dict) and persistent:
        lines.append("\n## Persistent Failures\n")
        for k, v in list(persistent.items())[:30]:
            lines.append(f"- persistent `{v}` × `{k}`\n")

    md_path.write_text("".join(lines), encoding="utf-8")
    return json_path, md_path


def _iter_report_jsons(history_dir: Path) -> list[Path]:
    if not history_dir.exists() or not history_dir.is_dir():
        return []
    out: list[Path] = []
    for p in history_dir.rglob("run_report.json"):
        if p.is_file():
            out.append(p)
    return out


def _safe_json_load(path: Path) -> dict[str, Any] | None:
    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:  # noqa: BLE001
        return None
    if isinstance(obj, dict):
        return obj
    return None


def _load_history(*, history_dir: Path, suite: str, limit: int) -> list[dict[str, Any]]:
    paths = _iter_report_jsons(history_dir)
    items: list[dict[str, Any]] = []
    for p in paths:
        obj = _safe_json_load(p)
        if not obj:
            continue
        if obj.get("suite") != suite:
            continue
        ts = obj.get("timestamp_utc")
        if not isinstance(ts, str):
            continue
        items.append(
            {
                "timestamp_utc": ts,
                "suite": suite,
                "runs": obj.get("runs"),
                "passes": obj.get("passes"),
                "pass_rate": obj.get("pass_rate"),
                "verdict": obj.get("verdict"),
                "failures": obj.get("failures"),
                "report_path": str(p),
            }
        )
    items.sort(key=lambda x: str(x.get("timestamp_utc") or ""), reverse=True)
    return items[: max(0, int(limit))]


def main() -> int:
    ap = argparse.ArgumentParser(description="Model-driven E2E runner (pass-rate gate + failure triage).")
    ap.add_argument("--suite", default="e2e_tests.smoke_core", help="unittest module name (default: e2e_tests.smoke_core)")
    ap.add_argument("--runs", type=int, default=3, help="number of independent runs (default: 3)")
    ap.add_argument("--min-pass-rate", type=float, default=1.0, help="quality gate threshold (default: 1.0)")
    ap.add_argument("--timeout-s", type=float, default=900.0, help="per-run timeout seconds (default: 900)")
    ap.add_argument("--rerun-failures", type=int, default=0, help="rerun failing test ids N times per failed run (default: 0)")
    ap.add_argument("--rerun-timeout-s", type=float, default=300.0, help="per-test rerun timeout seconds (default: 300)")
    ap.add_argument("--include-history", action="store_true", help="include recent pass-rate history for this suite in the report")
    ap.add_argument("--history-limit", type=int, default=10, help="history items to include when --include-history (default: 10)")
    ap.add_argument("--report-dir", default="", help="directory to write reports (default: .openagentic_e2e_reports/<ts>)")
    args = ap.parse_args()

    runs = max(1, int(args.runs))
    suite = str(args.suite).strip()
    timeout_s = max(1.0, float(args.timeout_s))
    min_pass_rate = min(1.0, max(0.0, float(args.min_pass_rate)))
    rerun_failures = max(0, int(args.rerun_failures))
    rerun_timeout_s = max(1.0, float(args.rerun_timeout_s))
    include_history = bool(args.include_history)
    history_limit = max(0, int(args.history_limit))

    report_dir = Path(args.report_dir) if str(args.report_dir).strip() else _default_report_dir()
    if not str(args.report_dir).strip():
        # Avoid collisions when multiple runners execute concurrently (e.g., in parallel).
        report_dir = report_dir.with_name(f"{report_dir.name}-{_suite_slug(suite)}-pid{os.getpid()}")

    run_results: list[RunResult] = []
    rerun_results: list[RerunResult] = []
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
            if rerun_failures > 0:
                failing_ids = _parse_failing_test_ids(out, err)
                for test_id in failing_ids:
                    for attempt in range(1, rerun_failures + 1):
                        r_rc, r_elapsed, r_out, r_err = _run_unittest_test_id(test_id=test_id, timeout_s=rerun_timeout_s)
                        r_ok = r_rc == 0
                        r_kind: str | None = None
                        if not r_ok:
                            r_kind = _classify_failure(r_out, r_err)
                        r_out_head, r_out_tail = _trim(r_out)
                        r_err_head, r_err_tail = _trim(r_err)
                        rerun_results.append(
                            RerunResult(
                                run_index=i,
                                test_id=test_id,
                                attempt=attempt,
                                ok=r_ok,
                                returncode=r_rc,
                                elapsed_s=round(r_elapsed, 3),
                                failure_kind=r_kind,
                                stdout_head=r_out_head,
                                stdout_tail=r_out_tail,
                                stderr_head=r_err_head,
                                stderr_tail=r_err_tail,
                            )
                        )

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
    required_passes = min(runs, max(0, int(math.ceil(min_pass_rate * runs))))
    allowed_failures = max(0, runs - required_passes)

    flake_test_counts: dict[str, int] = {}
    persistent_test_counts: dict[str, int] = {}
    if rerun_results:
        by_key: dict[tuple[int, str], list[RerunResult]] = {}
        for rr in rerun_results:
            by_key.setdefault((rr.run_index, rr.test_id), []).append(rr)
        for (_run_idx, tid), rrs in by_key.items():
            if any(x.ok for x in rrs):
                flake_test_counts[tid] = flake_test_counts.get(tid, 0) + 1
            else:
                persistent_test_counts[tid] = persistent_test_counts.get(tid, 0) + 1

    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "suite": suite,
        "runs": runs,
        "passes": passes,
        "pass_rate": round(pass_rate, 4),
        "min_pass_rate": min_pass_rate,
        "required_passes": required_passes,
        "allowed_failures": allowed_failures,
        "verdict": verdict,
        "failures": failures,
        "failure_test_counts": failure_test_counts,
        "rerun_failures": rerun_failures,
        "rerun_timeout_s": rerun_timeout_s,
        "rerun_results": [asdict(r) for r in rerun_results],
        "flake_test_counts": dict(sorted(flake_test_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "persistent_test_counts": dict(sorted(persistent_test_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "env": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "cwd": str(Path.cwd()),
            "has_http_proxy": bool(os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")),
            "has_https_proxy": bool(os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")),
        },
        "run_results": [asdict(r) for r in run_results],
    }
    if include_history:
        payload["history"] = _load_history(history_dir=Path.cwd() / ".openagentic_e2e_reports", suite=suite, limit=history_limit)

    json_path, md_path = _write_report(report_dir, payload=payload)

    print(f"Suite: {suite}")
    print(f"Runs: {runs}  Passes: {passes}  Pass rate: {pass_rate:.3f}  Gate: >= {min_pass_rate:.3f}  Verdict: {verdict}")
    print(f"Gate budget: required_passes={required_passes} allowed_failures={allowed_failures}")
    print(f"Failures: network={failures['network']} model={failures['model']} regression={failures['regression']}")
    print(f"Report: {json_path}")
    print(f"Report: {md_path}")

    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

