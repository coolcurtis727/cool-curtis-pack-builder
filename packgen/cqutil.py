"""Small CadQuery helpers shared by the holder and the enclosure."""

from __future__ import annotations

import os
import tempfile
from typing import Iterable

import cadquery as cq

from packgen.constants import CASE_LAP_CLEARANCE_MM, CASE_LAP_MM


def extrude_rect(
    rect: tuple[float, float, float, float],
    z0: float,
    z1: float,
) -> cq.Workplane | None:
    """Extrude an (x0, y0, x1, y1) rectangle between two Z heights."""
    x0, y0, x1, y1 = rect
    return make_box(x0, y0, z0, x1, y1, z1)


def make_box(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> cq.Workplane | None:
    x0, x1 = (x0, x1) if x0 <= x1 else (x1, x0)
    y0, y1 = (y0, y1) if y0 <= y1 else (y1, y0)
    z0, z1 = (z0, z1) if z0 <= z1 else (z1, z0)
    dx, dy, dz = x1 - x0, y1 - y0, z1 - z0
    if dx < 1e-4 or dy < 1e-4 or dz < 1e-4:
        return None
    center = ((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0)
    return cq.Workplane("XY").box(dx, dy, dz).translate(center)


def union(solid: cq.Workplane | None, extra: cq.Workplane | None) -> cq.Workplane | None:
    if solid is None:
        return extra
    if extra is None:
        return solid
    return solid.union(extra)


def cut(solid: cq.Workplane | None, cutter: cq.Workplane | None) -> cq.Workplane | None:
    if solid is None or cutter is None:
        return solid
    return solid.cut(cutter)


def cut_cylinders(
    solid: cq.Workplane | None,
    centers: Iterable[tuple[float, float]],
    z0: float,
    z1: float,
    radius: float,
) -> cq.Workplane | None:
    points = [(float(x), float(y)) for x, y in centers]
    if solid is None or not points or radius <= 0 or z1 - z0 < 1e-4:
        return solid
    cutter = (
        cq.Workplane("XY")
        .pushPoints(points)
        .circle(radius)
        .extrude(z1 - z0)
        .translate((0, 0, z0))
    )
    return solid.cut(cutter)


def safe_fillet_vertical(solid: cq.Workplane | None, radius: float) -> cq.Workplane | None:
    if solid is None or radius <= 0.05:
        return solid
    try:
        return solid.edges("|Z").fillet(radius)
    except Exception:
        return solid


def bounding_size(solid: cq.Workplane) -> tuple[float, float, float]:
    box = solid.val().BoundingBox()
    return (box.xmax - box.xmin, box.ymax - box.ymin, box.zmax - box.zmin)


def volume(solid: cq.Workplane) -> float:
    try:
        return float(solid.val().Volume())
    except Exception:
        return 0.0


def export_stl_bytes(solid: cq.Workplane, tolerance: float = 0.12, angular: float = 0.25) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "part.stl")
        cq.exporters.export(solid, path, tolerance=tolerance, angularTolerance=angular)
        with open(path, "rb") as handle:
            return handle.read()


def split_along_planes(
    solid: cq.Workplane,
    planes: list[float],
    axis: str,
    lap: float = CASE_LAP_MM,
    clearance: float = CASE_LAP_CLEARANCE_MM,
) -> list[cq.Workplane]:
    """Split a solid on sorted planes with a full-height lap joint.

    The piece on the lower side of each plane keeps a tongue on the bottom
    half. The piece on the higher side keeps the matching tongue on the top
    half. A small clearance keeps the printed faces from welding together.
    """
    if not planes:
        return [solid]
    box = solid.val().BoundingBox()
    pad = 2.0
    z0, z1 = box.zmin - pad, box.zmax + pad
    if axis == "x":
        start, end = box.xmin - pad, box.xmax + pad
        other = (box.ymin - pad, box.ymax + pad)
    else:
        start, end = box.ymin - pad, box.ymax + pad
        other = (box.xmin - pad, box.xmax + pad)
    edges = [start, *sorted(planes), end]
    parts: list[cq.Workplane] = []
    for index in range(len(edges) - 1):
        region = _lap_region(
            axis=axis,
            left=edges[index],
            right=edges[index + 1],
            has_left=index > 0,
            has_right=index < len(edges) - 2,
            other0=other[0],
            other1=other[1],
            z0=z0,
            z1=z1,
            lap=lap,
            clearance=clearance,
        )
        if region is None:
            parts.append(solid)
            continue
        parts.append(solid.intersect(region))
    return parts


def _lap_region(
    axis: str,
    left: float,
    right: float,
    has_left: bool,
    has_right: bool,
    other0: float,
    other1: float,
    z0: float,
    z1: float,
    lap: float,
    clearance: float,
) -> cq.Workplane | None:
    width = right - left
    lap_use = min(lap, max(0.0, width / 2.0 - clearance - 0.8))
    if lap_use < 1.0:
        lap_use = 0.0
    if has_left:
        upper0 = left - lap_use + clearance
        lower0 = left + lap_use + clearance
    else:
        upper0 = lower0 = left
    if has_right:
        upper1 = right - lap_use - clearance
        lower1 = right + lap_use - clearance
    else:
        upper1 = lower1 = right
    # Full-height core where the two halves already agree, plus tongues that
    # occupy only one half. The tongues overlap the core slightly so the piece
    # is one solid, and they stay clear of the mating piece.
    core0 = max(lower0, upper0)
    core1 = min(lower1, upper1)
    if core1 - core0 < 0.4:
        inset_left = clearance if has_left else 0.0
        inset_right = clearance if has_right else 0.0
        core0 = left + inset_left
        core1 = right - inset_right
        lower0 = upper0 = core0
        lower1 = upper1 = core1
    mid = (z0 + z1) / 2.0
    z_gap = min(0.15, clearance)
    pieces = [_interval_box(axis, core0, core1, other0, other1, z0, z1)]
    if lower0 < core0 - 0.05:
        pieces.append(_interval_box(axis, lower0, core0 + 0.08, other0, other1, z0, mid - z_gap))
    if lower1 > core1 + 0.05:
        pieces.append(_interval_box(axis, core1 - 0.08, lower1, other0, other1, z0, mid - z_gap))
    if upper0 < core0 - 0.05:
        pieces.append(_interval_box(axis, upper0, core0 + 0.08, other0, other1, mid + z_gap, z1))
    if upper1 > core1 + 0.05:
        pieces.append(_interval_box(axis, core1 - 0.08, upper1, other0, other1, mid + z_gap, z1))
    region = None
    for piece in pieces:
        region = union(region, piece)
    return region


def _interval_box(
    axis: str,
    a0: float,
    a1: float,
    other0: float,
    other1: float,
    z0: float,
    z1: float,
) -> cq.Workplane | None:
    if a1 - a0 < 1e-4:
        return None
    if axis == "x":
        return make_box(a0, other0, z0, a1, other1, z1)
    return make_box(other0, a0, z0, other1, a1, z1)
