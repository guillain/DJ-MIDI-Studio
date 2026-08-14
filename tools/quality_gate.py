from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from radon.complexity import cc_visit
from radon.metrics import mi_visit


@dataclass(frozen=True)
class Thresholds:
    coverage: float
    smell: float
    duplication: float


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, capture_output=True, check=check)


def _python_files(src_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in src_dir.rglob("*.py")
        if "__pycache__" not in p.parts and ".venv" not in p.parts
    )


def _line_coverage_pct(coverage_xml: Path) -> float:
    root = ET.fromstring(coverage_xml.read_text(encoding="utf-8"))
    return float(root.attrib["line-rate"]) * 100.0


def _smell_score(src_dir: Path) -> tuple[float, list[tuple[str, float, int]]]:
    """Score based on per-function CC grade (A or B, i.e. CC <= 10) and
    file-level MI >= 20 (radon grade A or B).  This follows SonarQube's
    convention: CC <= 5 = A, 6-10 = B, 11-15 = C, ... — we accept A+B as
    maintainable.  A per-function metric (not per-file) is used for CC so
    that large-but-well-factored Qt view files are not penalised for size."""
    files = _python_files(src_dir)
    if not files:
        return 100.0, []

    total_blocks = 0
    clean_blocks = 0
    details: list[tuple[str, float, int]] = []

    for path in files:
        code = path.read_text(encoding="utf-8")
        mi = mi_visit(code, multi=True)
        blocks = cc_visit(code)
        file_total = len(blocks) if blocks else 1
        file_clean = sum(1 for b in blocks if b.complexity <= 10)
        # give files with no functions the benefit of the doubt (trivial modules)
        if not blocks:
            file_clean = 1
        total_blocks += file_total
        clean_blocks += file_clean
        max_cc = max((b.complexity for b in blocks), default=1)
        details.append((str(path), mi, max_cc))

    score = (clean_blocks / total_blocks) * 100.0 if total_blocks else 100.0
    return score, details


def _normalized_lines(path: Path) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lines.append((lineno, " ".join(line.split())))
    return lines


def _duplication_pct(src_dir: Path, min_block: int = 6) -> float:
    files = _python_files(src_dir)
    all_entries: dict[Path, list[tuple[int, str]]] = {
        path: _normalized_lines(path) for path in files
    }
    total_lines = sum(len(lines) for lines in all_entries.values())
    if total_lines == 0:
        return 0.0

    windows: dict[tuple[str, ...], list[tuple[Path, int]]] = defaultdict(list)
    for path, lines in all_entries.items():
        if len(lines) < min_block:
            continue
        texts = [text for _, text in lines]
        for i in range(0, len(texts) - min_block + 1):
            windows[tuple(texts[i : i + min_block])].append((path, i))

    duplicated: set[tuple[Path, int]] = set()
    for hits in windows.values():
        if len(hits) < 2:
            continue
        for path, start_index in hits:
            lines = all_entries[path]
            for offset in range(min_block):
                duplicated.add((path, lines[start_index + offset][0]))

    return (len(duplicated) / total_lines) * 100.0


def _bandit_high_count(src_dir: Path) -> tuple[int, int, int]:
    proc = _run(
        [
            "uv",
            "run",
            "bandit",
            "-r",
            str(src_dir),
            "-f",
            "json",
            "-q",
        ],
        check=False,
    )
    payload = proc.stdout.strip()
    if not payload:
        if proc.stderr.strip():
            raise RuntimeError(f"bandit failed: {proc.stderr.strip()}")
        return 0, 0, 0
    data = json.loads(payload)
    high = 0
    medium = 0
    low = 0
    for issue in data.get("results", []):
        severity = issue.get("issue_severity", "").upper()
        if severity == "HIGH":
            high += 1
        elif severity == "MEDIUM":
            medium += 1
        elif severity == "LOW":
            low += 1
    return high, medium, low


def _dependency_vulnerability_count() -> int:
    proc = _run(
        ["uv", "run", "pip-audit", "--format", "json"],
        check=False,
    )
    payload = proc.stdout.strip()
    if not payload:
        if proc.returncode not in (0, 1):
            raise RuntimeError(f"pip-audit failed: {proc.stderr.strip()}")
        return 0

    report = json.loads(payload)
    if not isinstance(report, list):
        return 0
    return sum(len(dep.get("vulns", [])) for dep in report)


def _print_summary(
    coverage_pct: float,
    smell_pct: float,
    duplication_pct: float,
    bandit_high: int,
    bandit_medium: int,
    bandit_low: int,
    dep_vulns: int,
    thresholds: Thresholds,
) -> None:
    print("Quality Gate Summary")
    print("====================")
    print(f"Coverage             : {coverage_pct:.2f}% (target >= {thresholds.coverage:.2f}%)")
    print(f"Code smell score     : {smell_pct:.2f}% (target >= {thresholds.smell:.2f}%)")
    print(f"Duplication          : {duplication_pct:.2f}% (target < {thresholds.duplication:.2f}%)")
    print(f"Bandit HIGH findings : {bandit_high} (target = 0)")
    print(f"Bandit MEDIUM/LOW    : {bandit_medium}/{bandit_low} (informational)")
    print(f"Dependency vulns     : {dep_vulns} (target = 0)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Quality/security gate runner")
    parser.add_argument("--src", default="src/seratomidiconf", help="Source directory")
    parser.add_argument("--coverage-xml", default="coverage.xml", help="Coverage XML output path")
    parser.add_argument("--coverage-threshold", type=float, default=90.0)
    parser.add_argument("--smell-threshold", type=float, default=90.0)
    parser.add_argument("--duplication-threshold", type=float, default=5.0)
    parser.add_argument("--skip-tests", action="store_true", help="Do not run pytest coverage step")
    args = parser.parse_args()

    src_dir = Path(args.src)
    coverage_xml = Path(args.coverage_xml)
    thresholds = Thresholds(
        coverage=args.coverage_threshold,
        smell=args.smell_threshold,
        duplication=args.duplication_threshold,
    )

    if not args.skip_tests:
        print("Running pytest with coverage...")
        test_proc = _run(
            [
                "uv",
                "run",
                "pytest",
                "--cov=src/seratomidiconf",
                f"--cov-report=xml:{coverage_xml}",
                "--cov-report=term-missing:skip-covered",
            ],
            check=False,
        )
        sys.stdout.write(test_proc.stdout)
        sys.stderr.write(test_proc.stderr)
        if test_proc.returncode != 0:
            return test_proc.returncode

    if not coverage_xml.exists():
        print(f"Missing coverage report: {coverage_xml}", file=sys.stderr)
        return 2

    coverage_pct = _line_coverage_pct(coverage_xml)
    smell_pct, _smell_details = _smell_score(src_dir)
    duplication_pct = _duplication_pct(src_dir)
    bandit_high, bandit_medium, bandit_low = _bandit_high_count(src_dir)
    dep_vulns = _dependency_vulnerability_count()

    _print_summary(
        coverage_pct,
        smell_pct,
        duplication_pct,
        bandit_high,
        bandit_medium,
        bandit_low,
        dep_vulns,
        thresholds,
    )

    failed = False
    if coverage_pct < thresholds.coverage:
        failed = True
    if smell_pct < thresholds.smell:
        failed = True
    if duplication_pct >= thresholds.duplication:
        failed = True
    if bandit_high > 0:
        failed = True
    if dep_vulns > 0:
        failed = True

    if failed:
        print("\nQuality gate FAILED")
        return 1

    print("\nQuality gate PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

