"""Cell-holder solids.

Each section is a sleeve around its cells. A bottom holder can keep a ledge
and a weld window. A top holder is the same sleeve with a through hole.
Interlocking tabs live in the outer rim so they do not cut into the cell holes.
"""

from __future__ import annotations

import cadquery as cq

from packgen.constants import BUTT_GAP_MM
from packgen.cqutil import cut, cut_cylinders, make_box, safe_fillet_vertical, union
from packgen.layout import SectionSpec


def make_holder(
    section: SectionSpec,
    height: float,
    base_thickness: float,
    weld_window: float,
    hole_radius: float,
    corner_radius: float,
) -> cq.Workplane:
    half_gap = BUTT_GAP_MM / 2.0
    x0 = section.x0 + (half_gap if section.joint_nx else 0.0)
    x1 = section.x1 - (half_gap if section.joint_px else 0.0)
    y0 = section.y0 + (half_gap if section.joint_ny else 0.0)
    y1 = section.y1 - (half_gap if section.joint_py else 0.0)
    body = make_box(x0, y0, 0.0, x1, y1, height)
    body = safe_fillet_vertical(body, min(corner_radius, 2.5))
    for tongue in section.tongues:
        if tongue.pocket:
            continue
        body = union(
            body,
            make_box(tongue.x0, tongue.y0, 0.0, tongue.x1, tongue.y1, height * tongue.z_fraction),
        )
    # Witness notch at the local -X/-Y corner so split sections keep their orientation.
    body = cut(body, make_box(x0 + 1.6, y0 + 1.6, height - 1.3, x0 + 6.2, y0 + 6.2, height + 0.2))
    for tongue in section.tongues:
        if not tongue.pocket:
            continue
        body = cut(
            body,
            make_box(
                tongue.x0,
                tongue.y0,
                -0.1,
                tongue.x1,
                tongue.y1,
                height * tongue.z_fraction + 0.35,
            ),
        )
    centers = [(cell.x, cell.y) for cell in section.cells]
    if base_thickness > 0:
        body = cut_cylinders(body, centers, base_thickness, height + 0.2, hole_radius)
        if weld_window > 0:
            body = cut_cylinders(body, centers, -0.2, base_thickness + 0.05, weld_window / 2.0)
    else:
        body = cut_cylinders(body, centers, -0.2, height + 0.2, hole_radius)
    for channel in section.channels:
        body = cut(
            body,
            make_box(
                channel.x0,
                channel.y0,
                height - channel.depth,
                channel.x1,
                channel.y1,
                height + 0.2,
            ),
        )
    for slot in section.slots:
        body = cut(
            body,
            make_box(
                slot.x0,
                slot.y0,
                height * slot.z0_fraction,
                slot.x1,
                slot.y1,
                height + 0.2,
            ),
        )
    if body is None:
        raise RuntimeError(f"Holder section {section.suffix or 'main'} produced an empty solid.")
    return body
