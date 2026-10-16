"""Export STLs from the command line.

Examples:
    python -m packgen.cli --example 13s4p --out dist/13s4p
    python -m packgen.cli --series 10 --parallel 3 --packing rectangular --out dist/10s3p
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from packgen.build import build_parts
from packgen.examples import EXAMPLES
from packgen.layout import build_layout, recommend_sections
from packgen.models import PackParams, validate
from packgen.preview import draw_layout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate cylindrical-cell holder and case STLs.")
    parser.add_argument("--example", choices=sorted(EXAMPLES), help="Start from a named configuration.")
    parser.add_argument("--out", default="dist", help="Directory for STL files and pack_spec.json.")
    parser.add_argument("--preview", help="Also write a PNG of the 2D layout to this path.")
    parser.add_argument("--series", type=int)
    parser.add_argument("--parallel", type=int)
    parser.add_argument("--rows", type=int)
    parser.add_argument("--cols", type=int)
    parser.add_argument("--packing", choices=("rectangular", "staggered"))
    parser.add_argument("--preset", choices=("18650", "21700", "Custom"))
    parser.add_argument("--diameter", type=float)
    parser.add_argument("--length", type=float)
    parser.add_argument("--bms-side", choices=("pos_y", "neg_y", "pos_x", "neg_x"))
    parser.add_argument("--no-bms", action="store_true")
    parser.add_argument("--no-case", action="store_true")
    parser.add_argument("--lid", choices=("friction", "magnets", "clips"))
    parser.add_argument("--row-sections", type=int)
    parser.add_argument("--col-sections", type=int)
    parser.add_argument("--recommend", action="store_true", help="Print a bed-limit split and exit.")
    args = parser.parse_args(argv)

    params = EXAMPLES[args.example] if args.example else PackParams()
    updates: dict = {}
    if args.series is not None:
        updates["series"] = args.series
        updates["layout_mode"] = "series_parallel"
    if args.parallel is not None:
        updates["parallel"] = args.parallel
        updates["layout_mode"] = "series_parallel"
    if args.rows is not None:
        updates["rows"] = args.rows
        updates["layout_mode"] = "grid"
    if args.cols is not None:
        updates["cols"] = args.cols
        updates["layout_mode"] = "grid"
    if args.packing:
        updates["packing"] = args.packing
    if args.preset:
        updates["cell_preset"] = args.preset
    if args.diameter is not None:
        updates["diameter"] = args.diameter
        updates["cell_preset"] = "Custom"
    if args.length is not None:
        updates["length"] = args.length
        updates["cell_preset"] = "Custom"
    if args.bms_side:
        updates["bms_side"] = args.bms_side
        updates["bms_enabled"] = True
    if args.no_bms:
        updates["bms_enabled"] = False
    if args.no_case:
        updates["make_case"] = False
        updates["make_lid"] = False
    if args.lid:
        updates["lid_style"] = args.lid
        updates["make_lid"] = True
    if args.row_sections is not None:
        updates["row_sections"] = args.row_sections
    if args.col_sections is not None:
        updates["col_sections"] = args.col_sections
    if updates:
        params = PackParams.from_dict({**params.to_dict(), **updates})

    errors = validate(params)
    if errors:
        for error in errors:
            print(f"error: {error}")
        return 1

    if args.recommend:
        rows, cols = recommend_sections(params)
        print(f"recommended row sections: {rows}")
        print(f"recommended column sections: {cols}")
        return 0

    layout = build_layout(params)
    _print_summary(layout)
    if args.preview:
        figure = draw_layout(layout)
        preview_path = Path(args.preview)
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(preview_path, dpi=140)
        print(f"wrote {preview_path}")

    result = build_parts(layout)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for part in result.parts:
        if part.stl is None:
            print(f"failed {part.name}: {part.error}")
            continue
        path = out / part.name
        path.write_bytes(part.stl)
        sx, sy, sz = part.size
        print(f"wrote {path.name:32s} {sx:7.1f} x {sy:6.1f} x {sz:6.1f} mm")
    spec = {
        "params": params.to_dict(),
        "cells": layout.cell_count,
        "warnings": result.warnings,
        "notes": result.notes,
        "errors": result.errors,
        "parts": [
            {"name": part.name, "role": part.role, "size_mm": part.size, "error": part.error}
            for part in result.parts
        ],
    }
    (out / "pack_spec.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    for warning in result.warnings:
        print(f"warning: {warning}")
    for error in result.errors:
        print(f"error: {error}")
    return 1 if result.errors else 0


def _print_summary(layout) -> None:
    print(
        f"{layout.cell_count} cells  {layout.rows} rows x {layout.cols} cols  "
        f"pitch {layout.pitch_x:.2f} x {layout.pitch_y:.2f} mm  "
        f"longest part {layout.max_part_mm:.1f} mm"
    )
    for note in layout.notes:
        print(f"note: {note}")
    for warning in layout.warnings:
        print(f"warning: {warning}")


if __name__ == "__main__":
    raise SystemExit(main())
