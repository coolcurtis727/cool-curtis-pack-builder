"""Print and assembly notes derived from the current settings."""

from __future__ import annotations

import math

from packgen.layout import PackLayout
from packgen.models import BMS_SIDE_LABELS, PackParams


def print_notes(params: PackParams, layout: PackLayout | None = None) -> str:
    wall = params.case_wall
    perimeters = max(3, math.ceil(wall / 0.45))
    lines = [
        "### Print notes",
        "",
        "- **Units and orientation.** Everything is millimetres. Files are already oriented for the bed: holders with holes facing up, the case with the opening up, and the lid with its outer face down so the skirt and clips print upward.",
        f"- **Walls and infill.** Use a 0.2 mm layer and about a 0.45 mm line. The case wall is {wall:.1f} mm, so use at least {perimeters} perimeters if you want that wall mostly solid. Holders like 4–5 perimeters and 30–40% gyroid. The case can be 4 perimeters and 20–30% infill once the walls are solid.",
        "- **Material.** PETG is the practical default: it holds up to pack heat better than PLA and is less fussy than ABS. ABS or ASA is reasonable if the pack sits near a hot controller and your printer can hold the corners down. Skip PLA for an enclosed pack; it creeps in a hot garage or under charge heat.",
        "- **Fit.** Print one cell hole before the full holder. If the cell is tight, add about 0.1 mm of hole clearance and reprint the test. If it rattles, reduce the clearance. Cell spacing is the air gap for nickel and heat; do not crush cells down to zero.",
        "- **Holders.** The bottom piece can keep a ledge with a weld window so you can spot-weld through the floor. The top piece is an open ring that slides on after the cells are in. A small notch marks the −X/−Y corner of every section.",
        "- **Sections.** Split pieces meet on rim tabs (holders) and a lap joint (case and lid). The notch shows which way each piece rotates. Dry-fit the tabs, then glue the case lap if you want one shell. A strap through the mounting tabs is enough for many e-bike installs.",
        "- **BMS bay.** The bay is open under the lid. Balance leads cross the lowered divider. Main leads leave through the notch in the outer wall; add a zip tie there. That notch is a strain-relief slot, not a sealed gland.",
        "- **Lid.** A friction skirt locates the lid. Magnet pockets are sized for the diameter you set (6×3 mm magnets are the usual match for a 6.4 mm pocket) and should be glued if they are loose. Clip tabs want PETG and a test fit; if they miss the rib, switch the lid to magnets.",
        "- **Venting.** This model does not add vents. Do not build an airtight box around cells that can vent. Follow the cell maker's guidance on insulation, fusing, and charge supervision.",
        "- **What this does not do.** It does not size series voltage, continuous current, wire gauge, or nickel thickness. Those stay with the builder.",
    ]
    if layout is not None and layout.extra_y > 0.05:
        lines.append(
            f"- **Row joint gap.** Row sections are {layout.extra_y:.1f} mm farther apart than the normal pitch so the cut misses the cells."
        )
    if layout is not None and layout.extra_x > 0.05:
        lines.append(
            f"- **Column joint gap.** Column sections are {layout.extra_x:.1f} mm farther apart than the normal pitch."
        )
    if params.bms_enabled:
        lines.append(
            f"- **This BMS bay** is {params.bms_length:.0f} × {params.bms_width:.0f} × {params.bms_height:.0f} mm, "
            f"placed on {BMS_SIDE_LABELS.get(params.bms_side, params.bms_side)}."
        )
    return "\n".join(lines)
