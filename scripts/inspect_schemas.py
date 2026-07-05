#!/usr/bin/env python
"""Report which TCX/GPX schemas and extensions a file (or directory) uses, and flag
data that doesn't fit the known field tables in ``activity_parser.xml_fields``.

Usage:
    uv run python scripts/inspect_schemas.py <path> [<path> ...]

Each ``<path>`` may be a single ``.tcx``/``.gpx`` file (optionally ``.gz``) or a
directory, which is searched recursively for such files.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from lxml import etree

from activity_parser.parse_activity import infer_extension
from activity_parser.parse_tcx_gpx import (
    build_dataframe,
    remove_elements,
    unknown_column_name,
    walk_fields,
)
from activity_parser.xml_fields import (
    AEXT_NS,
    GPX10_NS,
    GPX11_NS,
    GPX_TRACKPOINT_FIELDS,
    GPXDATA_NS,
    TCX_LAP_FIELDS,
    TCX_NS,
    TCX_TRACKPOINT_FIELDS,
    TPX1_NS,
    TPX2_NS,
    Convert,
    FieldPath,
    XmlField,
    column_converts,
)

ROOT_LABELS = {TCX_NS: "TCX", GPX10_NS: "GPX 1.0", GPX11_NS: "GPX 1.1"}

NAMESPACE_LABELS = {
    TCX_NS: "TCX base",
    GPX10_NS: "GPX 1.0 base",
    GPX11_NS: "GPX 1.1 base",
    AEXT_NS: "ActivityExtension/v2",
    TPX1_NS: "TrackPointExtension/v1",
    TPX2_NS: "TrackPointExtension/v2",
    GPXDATA_NS: "gpxdata",
}

# Strava's bare, un-namespaced <power>: namespace-wise indistinguishable from GPX base
# fields (it inherits the default namespace), but it's really an informal convention.
BARE_POWER_PATH: FieldPath = ((GPX11_NS, "extensions"), (GPX11_NS, "power"))


@dataclass
class FileReport:
    path: Path
    root_label: str
    extensions_seen: set[str] = field(default_factory=set)
    unknown_counts: Counter[str] = field(default_factory=Counter)
    coercion_failures: dict[str, str] = field(default_factory=dict)


def _is_activity_xml(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith((".tcx", ".gpx", ".tcx.gz", ".gpx.gz"))


def find_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(sorted(f for f in p.rglob("*") if f.is_file() and _is_activity_xml(f)))
        else:
            files.append(p)
    return files


def _namespace_label(path: FieldPath, root_label: str) -> str:
    if path == BARE_POWER_PATH:
        return "bare <power>"
    # Unprefixed attributes never inherit a default namespace, so attribute leaves have
    # namespace None; attribute them to their nearest namespaced ancestor (e.g. TPX's
    # CadenceSensor -> ActivityExtension). All-None paths (trkpt's lat/lon, Lap's
    # StartTime) are base-schema fields.
    namespace = next((ns for ns, _name in reversed(path) if ns is not None), None)
    if namespace is None:
        return f"{root_label} base"
    return NAMESPACE_LABELS.get(namespace, namespace)


def _record_coercion_failures(
    df: pd.DataFrame, fields: dict[FieldPath, XmlField], failures: dict[str, str]
) -> None:
    for column, convert in column_converts(fields).items():
        if convert in (Convert.STRING, Convert.DATETIME) or column not in df.columns:
            continue
        if pd.api.types.is_numeric_dtype(df[column]):
            continue
        values = df[column]
        bad = values.notna() & pd.to_numeric(values, errors="coerce").isna()
        if bad.any():
            failures.setdefault(column, str(values[bad].iloc[0]))


def _inspect_container(
    root: etree._Element, tag: str, fields: dict[FieldPath, XmlField], report: FileReport
) -> None:
    elements = list(root.iter(tag))
    for element in elements:
        for element_path, _value in walk_fields(element):
            if element_path in fields:
                report.extensions_seen.add(_namespace_label(element_path, report.root_label))
            else:
                report.unknown_counts[unknown_column_name(element_path[-1])] += 1

    _record_coercion_failures(build_dataframe(elements, fields), fields, report.coercion_failures)


def inspect_file(path: Path) -> FileReport:
    ext = infer_extension(path)
    root = etree.parse(str(path), etree.XMLParser(recover=True)).getroot()
    root_namespace = etree.QName(root).namespace
    root_label = ROOT_LABELS.get(root_namespace, f"unrecognized root {root_namespace!r}")
    report = FileReport(path, root_label)

    if ext == "tcx":
        _inspect_container(root, "{*}Trackpoint", TCX_TRACKPOINT_FIELDS, report)
        # Mirrors parse_tcx: laps must not still contain their nested trackpoints, or
        # walk_fields would re-descend into them and flag trackpoint fields as unknown
        # against the lap field table.
        remove_elements(root, "{*}Track")
        _inspect_container(root, "{*}Lap", TCX_LAP_FIELDS, report)
    elif ext == "gpx":
        _inspect_container(root, "{*}trkpt", GPX_TRACKPOINT_FIELDS, report)
    else:
        raise ValueError(f"not a TCX/GPX file (ext={ext!r})")

    return report


def format_report(report: FileReport) -> str:
    lines = [f"{report.path}: {report.root_label}"]
    lines.append(f"  extensions seen:   {', '.join(sorted(report.extensions_seen)) or '(none)'}")
    if report.unknown_counts:
        unknown = ", ".join(
            f"{name} (x{count})" for name, count in report.unknown_counts.most_common()
        )
    else:
        unknown = "(none)"
    lines.append(f"  unknown elements:  {unknown}")
    if report.coercion_failures:
        failures = ", ".join(f"{col}={value!r}" for col, value in report.coercion_failures.items())
    else:
        failures = "(none)"
    lines.append(f"  coercion failures: {failures}")
    return "\n".join(lines)


def format_summary(reports: list[FileReport]) -> str:
    root_counts = Counter(r.root_label for r in reports)
    extension_counts: Counter[str] = Counter()
    unknown_names: set[str] = set()
    failing_files: list[str] = []
    for r in reports:
        extension_counts.update(r.extensions_seen)
        unknown_names.update(r.unknown_counts)
        if r.coercion_failures:
            failing_files.append(str(r.path))

    lines = [f"Summary across {len(reports)} files:"]
    lines.append(
        "  Schemas:    " + ", ".join(f"{label} ({n})" for label, n in root_counts.most_common())
    )
    if extension_counts:
        lines.append(
            "  Extensions: "
            + ", ".join(f"{label} ({n})" for label, n in extension_counts.most_common())
        )
    if unknown_names:
        lines.append("  Unknown elements encountered: " + ", ".join(sorted(unknown_names)))
    if failing_files:
        lines.append("  Files with coercion failures: " + ", ".join(failing_files))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="TCX/GPX file(s) or directories to inspect")
    args = parser.parse_args(argv)

    files = find_files(args.paths)
    if not files:
        print("No .tcx/.gpx files found.", file=sys.stderr)
        return 1

    reports = []
    for path in files:
        try:
            report = inspect_file(path)
        except (ValueError, OSError, etree.XMLSyntaxError) as exc:
            # Keep going on unreadable/corrupt files: an archive audit shouldn't die on
            # one bad export.
            print(f"{path}: skipped ({exc})", file=sys.stderr)
            continue
        reports.append(report)
        print(format_report(report))
        print()

    if len(reports) > 1:
        print(format_summary(reports))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
