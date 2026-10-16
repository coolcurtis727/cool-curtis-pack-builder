"""User-facing pack parameters and validation.

All dimensions are millimetres. One cell size is used for the whole pack.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
from typing import Any, get_type_hints

CELL_PRESETS: dict[str, dict[str, float | str]] = {
    "18650": {
        "diameter": 18.5,
        "length": 65.2,
        "note": "Unprotected 18650 nominal. Measure your cells; protected cells are often 67–70 mm long.",
    },
    "21700": {
        "diameter": 21.2,
        "length": 70.2,
        "note": "Unprotected 21700 nominal. Measure your cells before printing a full pack.",
    },
    "Custom": {
        "diameter": 18.5,
        "length": 65.2,
        "note": "Set diameter and length yourself.",
    },
}

LAYOUT_MODES = ("series_parallel", "grid")
PACKING_MODES = ("rectangular", "staggered")
SERIES_ALONG = ("rows", "columns")
LID_STYLES = ("friction", "magnets", "clips")
BMS_SIDES = ("pos_y", "neg_y", "pos_x", "neg_x")
SCREWS = ("M3", "M4")

BMS_SIDE_LABELS = {
    "pos_y": "End (+Y, beyond the last row)",
    "neg_y": "End (−Y, before the first row)",
    "pos_x": "Side (+X, beside the last column)",
    "neg_x": "Side (−X, beside the first column)",
}


@dataclass(frozen=True)
class PackParams:
    """Complete, UI-serialisable description of a pack."""

    cell_preset: str = "18650"
    diameter: float = 18.5
    length: float = 65.2
    layout_mode: str = "series_parallel"
    series: int = 4
    parallel: int = 2
    rows: int = 4
    cols: int = 2
    series_along: str = "rows"
    packing: str = "rectangular"
    cell_spacing: float = 2.0
    hole_clearance: float = 0.4
    holder_margin: float = 4.0
    holder_height: float = 15.0
    base_thickness: float = 1.6
    weld_window: float = 10.0
    make_top_holder: bool = True
    top_holder_height: float = 12.0
    wire_channels: bool = True
    strain_relief: bool = True
    make_case: bool = True
    make_lid: bool = True
    case_wall: float = 2.4
    floor_thickness: float = 2.4
    case_fit: float = 0.4
    top_clearance: float = 6.0
    corner_radius: float = 2.0
    lid_thickness: float = 3.4
    lid_style: str = "friction"
    magnet_diameter: float = 6.4
    magnet_depth: float = 2.2
    mounting_tabs: bool = True
    screw: str = "M3"
    bms_enabled: bool = True
    bms_length: float = 60.0
    bms_width: float = 28.0
    bms_height: float = 16.0
    bms_side: str = "pos_y"
    wire_access: float = 12.0
    row_sections: int = 1
    col_sections: int = 1
    max_print_mm: float = 240.0

    def resolved_rows_cols(self) -> tuple[int, int]:
        """Return (rows, columns) after applying series/parallel mapping."""
        if self.layout_mode == "grid":
            return max(1, int(self.rows)), max(1, int(self.cols))
        if self.series_along == "columns":
            return max(1, int(self.parallel)), max(1, int(self.series))
        return max(1, int(self.series)), max(1, int(self.parallel))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PackParams:
        hints = get_type_hints(cls)
        kwargs: dict[str, Any] = {}
        for item in fields(cls):
            if item.name not in data:
                continue
            value = data[item.name]
            kind = hints[item.name]
            if kind is int:
                value = int(value)
            elif kind is float:
                value = float(value)
            elif kind is bool:
                value = bool(value)
            elif kind is str:
                value = str(value)
            kwargs[item.name] = value
        return cls(**kwargs)


def screw_hole_diameter(screw: str) -> float:
    """Clearance hole for a metric machine screw."""
    return 4.5 if screw == "M4" else 3.4


def validate(params: PackParams) -> list[str]:
    """Return blocking errors. Warnings live on the layout result."""
    errors: list[str] = []
    rows, cols = params.resolved_rows_cols()
    if params.layout_mode not in LAYOUT_MODES:
        errors.append(f"Unknown layout mode '{params.layout_mode}'.")
    if params.packing not in PACKING_MODES:
        errors.append(f"Unknown packing '{params.packing}'.")
    if params.series_along not in SERIES_ALONG:
        errors.append(f"Unknown series direction '{params.series_along}'.")
    if params.lid_style not in LID_STYLES:
        errors.append(f"Unknown lid style '{params.lid_style}'.")
    if params.bms_side not in BMS_SIDES:
        errors.append(f"Unknown BMS side '{params.bms_side}'.")
    if params.screw not in SCREWS:
        errors.append(f"Unknown screw size '{params.screw}'.")
    if rows < 1 or cols < 1:
        errors.append("The grid needs at least one row and one column.")
    if rows > 40 or cols > 40:
        errors.append("Grids above 40 along one side are outside what this builder targets.")
    if not 8.0 <= params.diameter <= 40.0:
        errors.append("Cell diameter must be between 8 and 40 mm.")
    if not 20.0 <= params.length <= 150.0:
        errors.append("Cell length must be between 20 and 150 mm.")
    if not 0.4 <= params.cell_spacing <= 12.0:
        errors.append("Cell spacing must be between 0.4 and 12 mm.")
    if not 0.0 <= params.hole_clearance <= 2.0:
        errors.append("Hole clearance must be between 0 and 2 mm.")
    gap = params.cell_spacing - params.hole_clearance
    if gap < 0.8:
        errors.append(
            "Holes would nearly touch. Increase cell spacing or reduce hole clearance "
            f"(plastic between holes would be {gap:.2f} mm)."
        )
    if not 2.4 <= params.holder_margin <= 12.0:
        errors.append("Holder margin must be between 2.4 and 12 mm.")
    if not 6.0 <= params.holder_height <= 40.0:
        errors.append("Holder height must be between 6 and 40 mm.")
    if params.base_thickness < 0:
        errors.append("Base thickness cannot be negative.")
    if params.base_thickness >= params.holder_height - 2.0:
        errors.append("Base thickness must leave at least 2 mm of open sleeve above the floor.")
    if params.weld_window < 0:
        errors.append("Weld window cannot be negative.")
    if params.weld_window >= params.diameter:
        errors.append("Weld window must be smaller than the cell diameter.")
    if params.make_top_holder and not 6.0 <= params.top_holder_height <= 40.0:
        errors.append("Top holder height must be between 6 and 40 mm.")
    if params.make_case:
        if not 1.6 <= params.case_wall <= 6.0:
            errors.append("Case wall must be between 1.6 and 6 mm.")
        if not 1.6 <= params.floor_thickness <= 8.0:
            errors.append("Floor thickness must be between 1.6 and 8 mm.")
        if not 0.2 <= params.case_fit <= 2.0:
            errors.append("Case fit clearance must be between 0.2 and 2 mm.")
        if not 2.0 <= params.top_clearance <= 20.0:
            errors.append("Top clearance must be between 2 and 20 mm.")
        if params.corner_radius < 0 or params.corner_radius > 8:
            errors.append("Corner radius must be between 0 and 8 mm.")
    if params.make_lid:
        if not 2.0 <= params.lid_thickness <= 8.0:
            errors.append("Lid thickness must be between 2 and 8 mm.")
        if params.lid_style == "magnets":
            if not 3.0 <= params.magnet_diameter <= 12.0:
                errors.append("Magnet pocket diameter must be between 3 and 12 mm.")
            if params.magnet_depth <= 0 or params.magnet_depth >= params.lid_thickness - 0.6:
                errors.append(
                    "Magnet pocket is deeper than the lid. Increase lid thickness or use a shallower pocket."
                )
    if params.bms_enabled:
        if params.bms_length < 10 or params.bms_width < 10 or params.bms_height < 6:
            errors.append("BMS compartment must be at least 10 × 10 mm in plan and 6 mm tall.")
        if params.bms_length > 180 or params.bms_width > 120 or params.bms_height > 60:
            errors.append("BMS compartment is larger than this builder's practical range.")
        if not 4.0 <= params.wire_access <= 30.0:
            errors.append("Wire access height must be between 4 and 30 mm.")
    if params.row_sections < 1 or params.col_sections < 1:
        errors.append("Section counts start at 1.")
    if params.row_sections > rows:
        errors.append(f"Row sections ({params.row_sections}) cannot exceed row count ({rows}).")
    if params.col_sections > cols:
        errors.append(f"Column sections ({params.col_sections}) cannot exceed column count ({cols}).")
    if not 120.0 <= params.max_print_mm <= 400.0:
        errors.append("Printer limit must be between 120 and 400 mm.")
    return errors


def with_updates(params: PackParams, **changes: Any) -> PackParams:
    return replace(params, **changes)
