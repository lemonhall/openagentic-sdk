from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path


_DOC_E2E_TESTS_MODULE_RE = re.compile(r"\be2e_tests\.[A-Za-z0-9_]+\b")
_DOC_TEST_PATH_RE = re.compile(r"\b(e2e_tests_offline|e2e_tests)/[A-Za-z0-9_./-]+\.py\b")


@dataclass(frozen=True, slots=True)
class SuiteDef:
    suite_module: str
    suite_file: Path
    members: tuple[str, ...]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _module_to_file(root: Path, module: str) -> Path | None:
    if module.startswith("e2e_tests."):
        rel = Path("e2e_tests") / Path(*module.split(".")[1:])
        return (root / rel).with_suffix(".py")
    if module.startswith("e2e_tests_offline."):
        rel = Path("e2e_tests_offline") / Path(*module.split(".")[1:])
        return (root / rel).with_suffix(".py")
    return None


def _extract_string_tuple_assignments(tree: ast.AST) -> dict[str, tuple[str, ...]]:
    out: dict[str, tuple[str, ...]] = {}

    def _strings_from_seq(value: ast.AST) -> tuple[str, ...] | None:
        if not isinstance(value, (ast.Tuple, ast.List)):
            return None
        items: list[str] = []
        for elt in value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                items.append(elt.value)
            else:
                return None
        return tuple(items)

    for node in tree.body if isinstance(tree, ast.Module) else []:
        name: str | None = None
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                value = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                name = node.target.id
                value = node.value
        if not name or value is None:
            continue

        if not (name.endswith("_MODULES") or name.endswith("_SUITES")):
            continue

        seq = _strings_from_seq(value)
        if seq is not None:
            out[name] = seq

    return out


def _discover_suite_defs(root: Path) -> list[SuiteDef]:
    e2e_dir = root / "e2e_tests"
    suite_defs: list[SuiteDef] = []

    for p in sorted(e2e_dir.glob("*.py")):
        if p.name.startswith("__"):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "def load_tests" not in text:
            continue
        try:
            tree = ast.parse(text, filename=str(p))
        except SyntaxError:
            continue

        assigns = _extract_string_tuple_assignments(tree)
        members: list[str] = []
        for _k, v in assigns.items():
            members.extend(v)
        if not members:
            continue
        suite_defs.append(SuiteDef(suite_module=f"e2e_tests.{p.stem}", suite_file=p, members=tuple(members)))

    return suite_defs


def _expand_suite_members(
    root: Path,
    suite_by_module: dict[str, SuiteDef],
    *,
    suite_module: str,
) -> tuple[str, ...]:
    out: list[str] = []
    seen_suites: set[str] = set()

    def _walk(mod: str) -> None:
        if mod in suite_by_module:
            if mod in seen_suites:
                return
            seen_suites.add(mod)
            for m in suite_by_module[mod].members:
                _walk(m)
            return
        out.append(mod)

    _walk(suite_module)
    return tuple(out)


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _iter_plan_indexes(root: Path) -> list[Path]:
    plan_dir = root / "docs" / "plan"
    return sorted(plan_dir.glob("v*-index.md"))


def _extract_suites_and_tests_from_doc(text: str) -> tuple[set[str], set[str]]:
    suites_or_modules = set(_DOC_E2E_TESTS_MODULE_RE.findall(text))
    tests = {m.group(0) for m in _DOC_TEST_PATH_RE.finditer(text)}
    return suites_or_modules, tests


@dataclass(frozen=True, slots=True)
class Problem:
    kind: str
    message: str


def main() -> int:
    ap = argparse.ArgumentParser(description="Check curated E2E suites against docs/plan traceability references.")
    ap.add_argument("--root", default=None, help="Repo root (default: auto-detect from this script path).")
    ap.add_argument("--fail-on-warn", action="store_true", help="Treat warnings as failures (exit code 2).")
    args = ap.parse_args()

    root = Path(args.root).resolve() if args.root else _repo_root()

    suites = _discover_suite_defs(root)
    suite_by_module = {s.suite_module: s for s in suites}

    problems: list[Problem] = []
    warnings: list[Problem] = []

    # 1) Suite internal sanity: duplicates + missing module files.
    for s in suites:
        seen: set[str] = set()
        dups: list[str] = []
        for m in s.members:
            if m in seen:
                dups.append(m)
            seen.add(m)
        if dups:
            problems.append(Problem("suite.duplicate", f"{s.suite_module}: duplicate members: {sorted(set(dups))}"))

        expanded = _expand_suite_members(root, suite_by_module, suite_module=s.suite_module)
        for m in expanded:
            fp = _module_to_file(root, m)
            if fp is None:
                warnings.append(Problem("suite.unknown_module", f"{s.suite_module}: member not under e2e_tests*: {m}"))
                continue
            if not fp.exists():
                problems.append(Problem("suite.missing_file", f"{s.suite_module}: missing module file for {m}: {fp}"))

    # 2) Plan indexes: referenced files must exist.
    index_paths = _iter_plan_indexes(root)
    all_doc_suites: set[str] = set()
    all_doc_test_paths: set[str] = set()

    for idx in index_paths:
        text = _read_text(idx)
        doc_modules, doc_tests = _extract_suites_and_tests_from_doc(text)
        all_doc_suites |= doc_modules
        all_doc_test_paths |= doc_tests

        for rel in sorted(doc_tests):
            p = root / rel
            if not p.exists():
                problems.append(Problem("doc.missing_test_file", f"{idx}: references missing file: {rel}"))

        # 3) Suite vs doc consistency (within the same index doc).
        doc_suites = {m for m in doc_modules if m in suite_by_module}
        doc_leaf_e2e_tests = {
            t for t in doc_tests if t.startswith("e2e_tests/") and Path(t).name.startswith("e2e_")
        }
        if not doc_suites or not doc_leaf_e2e_tests:
            continue

        expanded_suite_files: set[str] = set()
        for sm in sorted(doc_suites):
            sd = suite_by_module.get(sm)
            assert sd is not None
            expanded = _expand_suite_members(root, suite_by_module, suite_module=sd.suite_module)
            for m in expanded:
                if not m.startswith("e2e_tests."):
                    continue
                fp = _module_to_file(root, m)
                if fp is None:
                    continue
                rel_fp = fp.relative_to(root).as_posix()
                if rel_fp.startswith("e2e_tests/") and fp.name.startswith("e2e_"):
                    expanded_suite_files.add(rel_fp)

        missing_in_suites = sorted(doc_leaf_e2e_tests - expanded_suite_files)
        if missing_in_suites:
            problems.append(
                Problem(
                    "doc.missing_in_suite",
                    f"{idx}: e2e_tests referenced in Traceability Matrix but not present in suites listed in this doc: {missing_in_suites}",
                )
            )

    # 4) Docs reference suite modules that we never discovered (typos).
    for sm in sorted(all_doc_suites):
        if sm.startswith("e2e_tests.") and sm not in suite_by_module:
            # This may be a reference to a *test module* (not a suite). Only warn
            # if the module corresponds to a missing file.
            fp = _module_to_file(root, sm)
            if fp is not None and not fp.exists():
                warnings.append(Problem("doc.unknown_suite_global", f"docs reference unknown/missing module: {sm} ({fp})"))

    # Output.
    print(f"Root: {root}")
    print(f"Suites found: {len(suites)}")
    print(f"Plan indexes checked: {len(index_paths)}")
    print(f"Plan referenced test files: {len(all_doc_test_paths)}")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"- [{w.kind}] {w.message}")

    if problems:
        print("\nFailures:")
        for pr in problems:
            print(f"- [{pr.kind}] {pr.message}")
        return 2

    if args.fail_on_warn and warnings:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
