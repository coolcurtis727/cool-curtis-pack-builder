"""2D layout drawing and a lightweight STL mesh reader for the 3D view."""

from __future__ import annotations

import struct
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle

from packgen.layout import PackLayout


def draw_layout(layout: PackLayout):
    """Return a matplotlib figure with a top view and an assembly side view."""
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 5.6), gridspec_kw={"width_ratios": [1.35, 1]})
    _draw_top(axes[0], layout)
    _draw_side(axes[1], layout)
    fig.subplots_adjust(left=0.07, right=0.98, bottom=0.14, top=0.92, wspace=0.28)
    return fig


def stl_mesh(data: bytes, stride: int = 1) -> dict[str, list[float] | list[int]]:
    """Parse a binary or ASCII STL into Plotly Mesh3d arrays."""
    if data[:5].lower() == b"solid" and b"facet" in data[:200].lower():
        return _ascii_stl(data.decode("utf-8", errors="ignore"), stride)
    return _binary_stl(data, stride)


def _draw_top(ax, layout: PackLayout) -> None:
    ax.set_aspect("equal")
    ax.set_title("Top view")
    if layout.wall_outer is not None:
        _rect(ax, layout.wall_outer, "#f4f7fa", "#5d7284", 1.0, None)
    if layout.bms_outer is not None:
        _rect(ax, layout.bms_outer, "#fbf6e8", "#b0892e", 1.0, None)
    if layout.cell_cavity is not None:
        _rect(ax, layout.cell_cavity, "#ffffff", "#9aa8b5", 0.6, None)
    if layout.bms_cavity is not None:
        _rect(ax, layout.bms_cavity, "#f6e7b8", "#b0892e", 1.0, "BMS")
    colors = ["#1f4b99", "#2f7d4a", "#b85c38", "#6b4c9a", "#0f6f8a", "#8a5a00"]
    radius = layout.params.diameter / 2.0
    for section in layout.sections:
        color = colors[(section.row_group * 3 + section.col_group) % len(colors)]
        _rect(ax, (section.x0, section.y0, section.x1, section.y1), "none", color, 1.3, None)
        for cell in section.cells:
            ax.add_patch(Circle((cell.x, cell.y), radius, facecolor="#f7f7f5", edgecolor=color, linewidth=1.1))
            ax.add_patch(
                Circle((cell.x, cell.y), layout.hole_radius, facecolor="none", edgecolor=color, linewidth=0.4, linestyle="--")
            )
    for tab in layout.tabs:
        _rect(ax, (tab.x0, tab.y0, tab.x1, tab.y1), "#d5e4da", "#3d6b4f", 0.8, None)
        ax.add_patch(Circle((tab.hole_x, tab.hole_y), tab.hole_d / 2.0, facecolor="#ffffff", edgecolor="#3d6b4f"))
    for magnet in layout.magnets:
        ax.add_patch(Circle((magnet.cx, magnet.cy), magnet.radius, facecolor="#f0d2d2", edgecolor="#8c3d3d"))
    if layout.lead_notch is not None:
        nx0, ny0, _, nx1, ny1, _ = layout.lead_notch
        _rect(ax, (nx0, ny0, nx1, ny1), "#f3d0c8", "#a24b3a", 0.8, None)
    _dimensions(ax, layout)
    ax.set_xlabel("X (columns)  mm")
    ax.set_ylabel("Y (rows)  mm")
    ax.grid(True, linewidth=0.3, color="#e1e6eb")


def _draw_side(ax, layout: PackLayout) -> None:
    ax.set_title("Side view, looking along +X")
    params = layout.params
    floor = layout.floor
    total_z = layout.case_total_z if layout.wall_outer is not None else floor + params.base_thickness + params.length + params.top_clearance
    if layout.wall_outer is not None:
        _rect(ax, (layout.wall_outer[1], 0.0, layout.wall_outer[3], total_z), "#e7eef3", "#5d7284", 1.0, None)
    if layout.cell_cavity is not None:
        cav = layout.cell_cavity
        _rect(ax, (cav[1], floor, cav[3], total_z), "#ffffff", "#9aa8b5", 0.6, None)
    extends_length = (
        layout.bms_outer is not None
        and layout.wall_outer is not None
        and (
            layout.bms_outer[1] < layout.wall_outer[1] - 1
            or layout.bms_outer[3] > layout.wall_outer[3] + 1
        )
    )
    if extends_length:
        bay = layout.bms_outer
        _rect(ax, (bay[1], 0.0, bay[3], total_z), "#fbf6e8", "#b0892e", 1.0, None)
    if layout.bms_cavity is not None and extends_length:
        bay = layout.bms_cavity
        _rect(ax, (bay[1], floor, bay[3], total_z), "#f6e7b8", "#b0892e", 1.0, "BMS")
    ys = [cell.y for cell in layout.cells]
    radius = params.diameter / 2.0
    cell_z0 = floor + params.base_thickness
    cell_z1 = cell_z0 + params.length
    _rect(ax, (min(ys) - radius, cell_z0, max(ys) + radius, cell_z1), "#f7f7f5", "#1f4b99", 1.0, "Cells")
    hb = layout.holder_bounds
    _rect(ax, (hb[1], floor, hb[3], floor + params.holder_height), "#d9e3f5", "#1f4b99", 0.8, None)
    if params.make_top_holder:
        _rect(
            ax,
            (hb[1], cell_z1 - params.top_holder_height, hb[3], cell_z1),
            "#c5d4ef",
            "#1f4b99",
            0.8,
            None,
        )
    lid_top = total_z
    if params.make_lid and layout.wall_outer is not None:
        lid_top = total_z + params.lid_thickness
        _rect(
            ax,
            (layout.wall_outer[1], total_z, layout.wall_outer[3], lid_top),
            "#d5dbe3",
            "#3e4c5a",
            1.0,
            "Lid",
        )
    span_y0 = hb[1]
    span_y1 = hb[3]
    if layout.wall_outer is not None:
        span_y0 = min(span_y0, layout.wall_outer[1])
        span_y1 = max(span_y1, layout.wall_outer[3])
    if extends_length and layout.bms_outer is not None:
        span_y0 = min(span_y0, layout.bms_outer[1])
        span_y1 = max(span_y1, layout.bms_outer[3])
    pad_y = max(6.0, 0.08 * (span_y1 - span_y0))
    pad_z = max(4.0, 0.08 * lid_top)
    ax.set_xlim(span_y0 - pad_y, span_y1 + pad_y)
    ax.set_ylim(-pad_z, lid_top + pad_z)
    ax.set_xlabel("Y (rows)  mm")
    ax.set_ylabel("Z  mm")
    ax.grid(True, linewidth=0.3, color="#e1e6eb")


def _rect(ax, box: tuple[float, float, float, float], face: str, edge: str, width: float, label: str | None) -> None:
    x0, y0, x1, y1 = box
    patch = Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=face, edgecolor=edge, linewidth=width)
    ax.add_patch(patch)
    if label:
        ax.text((x0 + x1) / 2.0, (y0 + y1) / 2.0, label, ha="center", va="center", fontsize=8, color="#243140")


def _dimensions(ax, layout: PackLayout) -> None:
    """Draw overall size marks with plain lines.

    Fancy arrow annotations make Matplotlib's tight bounding-box pass redraw
    forever, which is what Streamlit uses when it saves the figure.
    """
    bounds = layout.case_extent or layout.holder_bounds
    x0, y0, x1, y1 = bounds
    pad = max(8.0, 0.08 * max(x1 - x0, y1 - y0))
    tick = pad * 0.18
    y_dim = y0 - pad
    x_dim = x1 + pad
    color = "#243140"
    ax.plot([x0, x1], [y_dim, y_dim], color=color, linewidth=0.8, solid_capstyle="butt")
    ax.plot([x0, x0], [y_dim - tick, y_dim + tick], color=color, linewidth=0.8)
    ax.plot([x1, x1], [y_dim - tick, y_dim + tick], color=color, linewidth=0.8)
    ax.text((x0 + x1) / 2.0, y_dim - tick * 1.4, f"{x1 - x0:.0f} mm", ha="center", va="top", fontsize=8, color=color)
    ax.plot([x_dim, x_dim], [y0, y1], color=color, linewidth=0.8, solid_capstyle="butt")
    ax.plot([x_dim - tick, x_dim + tick], [y0, y0], color=color, linewidth=0.8)
    ax.plot([x_dim - tick, x_dim + tick], [y1, y1], color=color, linewidth=0.8)
    ax.text(x_dim + tick * 1.6, (y0 + y1) / 2.0, f"{y1 - y0:.0f} mm", ha="left", va="center", fontsize=8, rotation=90, color=color)
    ax.set_xlim(x0 - pad * 2.2, x1 + pad * 2.8)
    ax.set_ylim(y0 - pad * 2.6, y1 + pad * 1.6)


def _binary_stl(data: bytes, stride: int) -> dict[str, Any]:
    if len(data) < 84:
        return _empty_mesh()
    count = struct.unpack_from("<I", data, 80)[0]
    expected = 84 + count * 50
    if count == 0 or len(data) < expected:
        return _empty_mesh()
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    ii: list[int] = []
    jj: list[int] = []
    kk: list[int] = []
    step = max(1, stride)
    vertex_index = 0
    for tri in range(0, count, step):
        offset = 84 + tri * 50 + 12
        coords = struct.unpack_from("<9f", data, offset)
        xs.extend(coords[0::3])
        ys.extend(coords[1::3])
        zs.extend(coords[2::3])
        ii.append(vertex_index)
        jj.append(vertex_index + 1)
        kk.append(vertex_index + 2)
        vertex_index += 3
    return {"x": xs, "y": ys, "z": zs, "i": ii, "j": jj, "k": kk}


def _ascii_stl(text: str, stride: int) -> dict[str, Any]:
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    ii: list[int] = []
    jj: list[int] = []
    kk: list[int] = []
    verts: list[tuple[float, float, float]] = []
    tri_index = 0
    kept = 0
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0] == "vertex":
            verts.append((float(parts[1]), float(parts[2]), float(parts[3])))
            if len(verts) == 3:
                if tri_index % max(1, stride) == 0:
                    base = kept * 3
                    for x_pos, y_pos, z_pos in verts:
                        xs.append(x_pos)
                        ys.append(y_pos)
                        zs.append(z_pos)
                    ii.append(base)
                    jj.append(base + 1)
                    kk.append(base + 2)
                    kept += 1
                verts = []
                tri_index += 1
    return {"x": xs, "y": ys, "z": zs, "i": ii, "j": jj, "k": kk}


def _empty_mesh() -> dict[str, Any]:
    return {"x": [], "y": [], "z": [], "i": [], "j": [], "k": []}
