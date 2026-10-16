"""Case and lid solids.

The case is printed opening-up. The lid is printed outer-face down, with the
skirt and any clips pointing up so they need no support.
"""

from __future__ import annotations

import cadquery as cq

from packgen.constants import SKIRT_CLEARANCE_MM, SKIRT_HEIGHT_MM, SKIRT_THICKNESS_MM
from packgen.cqutil import cut, cut_cylinders, extrude_rect, make_box, safe_fillet_vertical, split_along_planes, union
from packgen.layout import ClipSpec, PackLayout, SectionSpec


def make_case(layout: PackLayout) -> cq.Workplane:
    if layout.wall_outer is None or layout.cell_cavity is None:
        raise RuntimeError("This layout has no case.")
    total_z = layout.case_total_z
    floor = layout.floor
    body = extrude_rect(layout.wall_outer, 0.0, total_z)
    body = safe_fillet_vertical(body, layout.params.corner_radius)
    body = cut(body, extrude_rect(layout.cell_cavity, floor, total_z + 0.2))
    if layout.bms_cavity is not None and layout.bms_outer is not None:
        body = union(body, extrude_rect(layout.bms_outer, 0.0, total_z))
        body = cut(body, extrude_rect(layout.bms_cavity, floor, total_z + 0.2))
        window = _wire_window(layout.cell_cavity, layout.bms_cavity, layout.params.bms_side)
        z_open = total_z - max(layout.top_zone, 8.0)
        body = cut(body, extrude_rect(window, z_open, total_z + 0.2))
    if layout.lead_notch is not None:
        nx0, ny0, nz0, nx1, ny1, nz1 = layout.lead_notch
        body = cut(body, make_box(nx0, ny0, nz0, nx1, ny1, nz1))
    for magnet in layout.magnets:
        body = union(body, make_box(magnet.x0, magnet.y0, floor, magnet.x1, magnet.y1, total_z))
    if layout.magnets:
        body = cut_cylinders(
            body,
            [(magnet.cx, magnet.cy) for magnet in layout.magnets],
            total_z - layout.magnets[0].depth,
            total_z + 0.3,
            layout.magnets[0].radius,
        )
    for tab in layout.tabs:
        body = union(body, make_box(tab.x0, tab.y0, 0.0, tab.x1, tab.y1, tab.thickness))
        body = cut_cylinders(body, [(tab.hole_x, tab.hole_y)], -0.2, tab.thickness + 0.2, tab.hole_d / 2.0)
    for clip in layout.clips:
        body = union(body, make_box(clip.rib_x0, clip.rib_y0, clip.rib_z0, clip.rib_x1, clip.rib_y1, clip.rib_z1))
    if body is None:
        raise RuntimeError("Case solid is empty.")
    return body


def make_lid(layout: PackLayout) -> cq.Workplane:
    if layout.wall_outer is None or layout.top_opening is None:
        raise RuntimeError("This layout has no lid.")
    thickness = layout.params.lid_thickness
    plate = extrude_rect(layout.wall_outer, 0.0, thickness)
    if layout.bms_outer is not None:
        plate = union(plate, extrude_rect(layout.bms_outer, 0.0, thickness))
    for magnet in layout.magnets:
        plate = union(plate, make_box(magnet.x0, magnet.y0, 0.0, magnet.x1, magnet.y1, thickness))
    plate = union(plate, _skirt(layout, thickness))
    if layout.magnets:
        plate = cut_cylinders(
            plate,
            [(magnet.cx, magnet.cy) for magnet in layout.magnets],
            thickness - layout.magnets[0].depth,
            thickness + 0.3,
            layout.magnets[0].radius,
        )
    if layout.lead_notch is not None:
        nx0, ny0, _, nx1, ny1, _ = layout.lead_notch
        plate = cut(
            plate,
            make_box(nx0 - 0.3, ny0 - 0.3, thickness - 0.1, nx1 + 0.3, ny1 + 0.3, thickness + SKIRT_HEIGHT_MM + 0.4),
        )
    for clip in layout.clips:
        plate = union(plate, make_box(clip.tab_x0, clip.tab_y0, thickness, clip.tab_x1, clip.tab_y1, thickness + clip.drop))
        plate = union(plate, _hook(clip, thickness))
    if plate is None:
        raise RuntimeError("Lid solid is empty.")
    return plate


def split_for_sections(solid: cq.Workplane, sections: tuple[SectionSpec, ...]) -> list[cq.Workplane]:
    """Return one solid per section, in the same order as `sections`."""
    if not sections:
        return []
    if sections[0].n_row_groups == 1 and sections[0].n_col_groups == 1:
        return [solid]
    x_planes = sorted({section.x1 for section in sections if section.joint_px})
    y_planes = sorted({section.y1 for section in sections if section.joint_py})
    columns = split_along_planes(solid, x_planes, "x") if x_planes else [solid]
    pieces: list[cq.Workplane] = []
    for section in sections:
        column = columns[section.col_group]
        if y_planes:
            rows = split_along_planes(column, y_planes, "y")
            pieces.append(rows[section.row_group])
        else:
            pieces.append(column)
    return pieces


def _wire_window(
    cell: tuple[float, float, float, float],
    bms: tuple[float, float, float, float],
    side: str,
) -> tuple[float, float, float, float]:
    """Opening through the divider so leads can leave the cell bay."""
    cx0, cy0, cx1, cy1 = cell
    bx0, by0, bx1, by1 = bms
    if side == "pos_x":
        return (cx1 - 0.5, max(cy0, by0), bx0 + 0.5, min(cy1, by1))
    if side == "neg_x":
        return (bx1 - 0.5, max(cy0, by0), cx0 + 0.5, min(cy1, by1))
    if side == "pos_y":
        return (max(cx0, bx0), cy1 - 0.5, min(cx1, bx1), by0 + 0.5)
    return (max(cx0, bx0), by1 - 0.5, min(cx1, bx1), cy0 + 0.5)


def _skirt(layout: PackLayout, thickness: float) -> cq.Workplane | None:
    assert layout.top_opening is not None
    x0, y0, x1, y1 = layout.top_opening
    clearance = SKIRT_CLEARANCE_MM
    wall = SKIRT_THICKNESS_MM
    outer = (x0 + clearance, y0 + clearance, x1 - clearance, y1 - clearance)
    inner = (outer[0] + wall, outer[1] + wall, outer[2] - wall, outer[3] - wall)
    if inner[2] - inner[0] < 4 or inner[3] - inner[1] < 4:
        return None
    ring = extrude_rect(outer, thickness, thickness + SKIRT_HEIGHT_MM)
    return cut(ring, extrude_rect(inner, thickness - 0.1, thickness + SKIRT_HEIGHT_MM + 0.2))


def _hook(clip: ClipSpec, thickness: float) -> cq.Workplane | None:
    """Triangular lead-in. The full tooth is at the catch; it tapers toward the tip."""
    z_catch = thickness + clip.hook_z0
    z_tip = thickness + clip.hook_z1
    try:
        if clip.side in ("pos_y", "neg_y"):
            y_wall, y_tab = _wall_and_tab(clip.side, clip.hook_y0, clip.hook_y1)
            y_tab = y_tab + (0.35 if y_tab > y_wall else -0.35)
            depth = abs(clip.hook_x1 - clip.hook_x0)
            profile = (
                cq.Workplane("YZ")
                .polyline([(y_tab, z_catch), (y_wall, z_catch), (y_tab, z_tip)])
                .close()
                .extrude(depth)
            )
            box = profile.val().BoundingBox()
            return profile.translate((min(clip.hook_x0, clip.hook_x1) - box.xmin, 0, 0))
        x_wall, x_tab = _wall_and_tab(clip.side, clip.hook_x0, clip.hook_x1)
        x_tab = x_tab + (0.35 if x_tab > x_wall else -0.35)
        depth = abs(clip.hook_y1 - clip.hook_y0)
        profile = (
            cq.Workplane("XZ")
            .polyline([(x_tab, z_catch), (x_wall, z_catch), (x_tab, z_tip)])
            .close()
            .extrude(depth)
        )
        return _place_xz_extrusion(profile, min(clip.hook_y0, clip.hook_y1), max(clip.hook_y0, clip.hook_y1))
    except Exception:
        return make_box(clip.hook_x0, clip.hook_y0, z_catch, clip.hook_x1, clip.hook_y1, z_tip)


def _wall_and_tab(side: str, a0: float, a1: float) -> tuple[float, float]:
    """Return (wall-side coordinate, tab-side coordinate) along the outward axis."""
    if side in ("pos_y", "pos_x"):
        return (min(a0, a1), max(a0, a1))
    return (max(a0, a1), min(a0, a1))


def _place_xz_extrusion(profile: cq.Workplane, y0: float, y1: float) -> cq.Workplane:
    box = profile.val().BoundingBox()
    # An XZ workplane extrudes along -Y, so a positive extrude occupies negative Y.
    return profile.translate((0, y0 - box.ymin, 0))
