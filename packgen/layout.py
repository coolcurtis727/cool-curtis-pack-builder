"""Pure-Python pack layout.

CadQuery is intentionally not imported here. Every printable dimension is
decided in this module so holder, case, and lid code only extrude the result.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from packgen.constants import (
    BUTT_GAP_MM,
    CASE_LAP_MM,
    CLIP_RIB_BELOW_TOP_MM,
    CLIP_RIB_HEIGHT_MM,
    CLIP_RIB_PROTRUSION_MM,
    CLIP_TAB_GAP_MM,
    CLIP_TAB_THICKNESS_MM,
    CLIP_WIDTH_MM,
    LEAD_NOTCH_DEPTH_MM,
    LEAD_NOTCH_WIDTH_MM,
    MAGNET_PAD_EXTRA_MM,
    MAGNET_PAD_OVERLAP_MM,
    MIN_INTERCELL_WALL_MM,
    MIN_LAND_MM,
    POCKET_CLEARANCE_MM,
    SKIRT_HEIGHT_MM,
    STRAIN_SLOT_WIDTH_MM,
    STRAIN_SLOT_Z0_FRACTION,
    TAB_ALONG_MM,
    TAB_MIN_THICKNESS_MM,
    TAB_OUT_MM,
    TONGUE_LENGTH_MM,
    TONGUE_SIDE_INSET_MM,
    TONGUE_Z_FRACTION,
    TYPICAL_BED_HARD_MM,
    WIRE_CHANNEL_DEPTH_MM,
    WIRE_CHANNEL_WIDTH_MM,
)
from packgen.models import PackParams, screw_hole_diameter


@dataclass(frozen=True)
class CellCenter:
    x: float
    y: float
    row: int
    col: int
    row_group: int
    col_group: int


@dataclass(frozen=True)
class TongueSpec:
    """Male tab (pocket=False) or the matching female pocket (pocket=True)."""

    x0: float
    y0: float
    x1: float
    y1: float
    z_fraction: float
    pocket: bool


@dataclass(frozen=True)
class ChannelSpec:
    x0: float
    y0: float
    x1: float
    y1: float
    depth: float


@dataclass(frozen=True)
class SlotSpec:
    x0: float
    y0: float
    x1: float
    y1: float
    z0_fraction: float


@dataclass(frozen=True)
class SectionSpec:
    row_group: int
    col_group: int
    n_row_groups: int
    n_col_groups: int
    cells: tuple[CellCenter, ...]
    x0: float
    y0: float
    x1: float
    y1: float
    joint_nx: bool
    joint_px: bool
    joint_ny: bool
    joint_py: bool
    tongues: tuple[TongueSpec, ...]
    channels: tuple[ChannelSpec, ...]
    slots: tuple[SlotSpec, ...]

    @property
    def suffix(self) -> str:
        if self.n_row_groups == 1 and self.n_col_groups == 1:
            return ""
        return f"_r{self.row_group + 1}of{self.n_row_groups}_c{self.col_group + 1}of{self.n_col_groups}"


@dataclass(frozen=True)
class MagnetSpec:
    x0: float
    y0: float
    x1: float
    y1: float
    cx: float
    cy: float
    radius: float
    depth: float


@dataclass(frozen=True)
class TabSpec:
    x0: float
    y0: float
    x1: float
    y1: float
    thickness: float
    hole_d: float
    hole_x: float
    hole_y: float


@dataclass(frozen=True)
class ClipSpec:
    side: str
    rib_x0: float
    rib_y0: float
    rib_x1: float
    rib_y1: float
    rib_z0: float
    rib_z1: float
    tab_x0: float
    tab_y0: float
    tab_x1: float
    tab_y1: float
    hook_x0: float
    hook_y0: float
    hook_x1: float
    hook_y1: float
    hook_z0: float
    hook_z1: float
    drop: float


@dataclass(frozen=True)
class PartPlan:
    name: str
    role: str
    sx: float
    sy: float
    sz: float

    @property
    def max_dim(self) -> float:
        return max(self.sx, self.sy, self.sz)


@dataclass(frozen=True)
class PackLayout:
    params: PackParams
    rows: int
    cols: int
    pitch_x: float
    pitch_y: float
    staggered: bool
    hole_radius: float
    cells: tuple[CellCenter, ...]
    sections: tuple[SectionSpec, ...]
    extra_x: float
    extra_y: float
    x_planes: tuple[float, ...]
    y_planes: tuple[float, ...]
    holder_bounds: tuple[float, float, float, float]
    wall_outer: tuple[float, float, float, float] | None
    bms_outer: tuple[float, float, float, float] | None
    case_extent: tuple[float, float, float, float] | None
    lid_extent: tuple[float, float, float, float] | None
    case_total_z: float
    floor: float
    internal_h: float
    cell_cavity: tuple[float, float, float, float] | None
    bms_cavity: tuple[float, float, float, float] | None
    top_opening: tuple[float, float, float, float] | None
    top_zone: float
    magnets: tuple[MagnetSpec, ...]
    tabs: tuple[TabSpec, ...]
    clips: tuple[ClipSpec, ...]
    lead_notch: tuple[float, float, float, float, float, float] | None
    part_plans: tuple[PartPlan, ...]
    warnings: tuple[str, ...]
    notes: tuple[str, ...]

    @property
    def cell_count(self) -> int:
        return len(self.cells)

    @property
    def max_part_mm(self) -> float:
        if not self.part_plans:
            return 0.0
        return max(part.max_dim for part in self.part_plans)

    @property
    def fits_bed(self) -> bool:
        return self.max_part_mm <= self.params.max_print_mm + 0.05


def partition(count: int, sections: int) -> list[int]:
    """Split `count` items into `sections` contiguous groups, as evenly as possible."""
    sections = max(1, min(int(sections), count))
    base, rem = divmod(count, sections)
    return [base + (1 if index < rem else 0) for index in range(sections)]


def _axis_positions(pitch: float, groups: list[int], extra: float) -> list[float]:
    positions: list[float] = []
    cursor = 0.0
    started = False
    for size in groups:
        for index in range(size):
            if started:
                cursor += pitch + (extra if index == 0 else 0.0)
            started = True
            positions.append(cursor)
    return positions


def _group_ids(groups: list[int]) -> list[int]:
    ids: list[int] = []
    for group_index, size in enumerate(groups):
        ids.extend([group_index] * size)
    return ids


def _span_extra(pitch: float, hole_radius: float, stagger_penalty: float = 0.0) -> float:
    """Extra centre distance so a straight joint clears every hole by MIN_LAND_MM."""
    return max(0.0, 2.0 * (hole_radius + MIN_LAND_MM) - pitch + stagger_penalty)


def _bbox_xy(boxes: list[tuple[float, float, float, float]]) -> tuple[float, float, float, float]:
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _size_of(bounds: tuple[float, float, float, float], z: float) -> tuple[float, float, float]:
    return (bounds[2] - bounds[0], bounds[3] - bounds[1], z)


def build_layout(params: PackParams) -> PackLayout:
    """Compute cell centres, section joints, and the case/lid envelope."""
    rows, cols = params.resolved_rows_cols()
    staggered = params.packing == "staggered" and rows >= 2 and cols >= 2
    pitch_x = params.diameter + params.cell_spacing
    pitch_y = pitch_x * (3.0 ** 0.5) / 2.0 if staggered else pitch_x
    hole_radius = (params.diameter + params.hole_clearance) / 2.0
    row_groups = partition(rows, params.row_sections)
    col_groups = partition(cols, params.col_sections)
    n_row_groups = len(row_groups)
    n_col_groups = len(col_groups)

    extra_y = _span_extra(pitch_y, hole_radius) if n_row_groups > 1 else 0.0
    if n_col_groups > 1:
        # Odd staggered rows sit half a pitch into a vertical gap, so the lane
        # has to be wider before a straight cut clears every hole.
        stagger_penalty = pitch_x / 2.0 if staggered else 0.0
        extra_x = _span_extra(pitch_x, hole_radius, stagger_penalty)
    else:
        extra_x = 0.0

    raw_xs = _axis_positions(pitch_x, col_groups, extra_x)
    raw_ys = _axis_positions(pitch_y, row_groups, extra_y)
    row_group_of = _group_ids(row_groups)
    col_group_of = _group_ids(col_groups)
    shift = pitch_x / 2.0 if staggered else 0.0

    raw_cells: list[tuple[float, float, int, int]] = []
    for row, y_pos in enumerate(raw_ys):
        x_shift = shift if row % 2 == 1 else 0.0
        for col, x_pos in enumerate(raw_xs):
            raw_cells.append((x_pos + x_shift, y_pos, row, col))

    dx = (min(cell[0] for cell in raw_cells) + max(cell[0] for cell in raw_cells)) / 2.0
    dy = (min(cell[1] for cell in raw_cells) + max(cell[1] for cell in raw_cells)) / 2.0
    cells = tuple(
        CellCenter(
            x=x_pos - dx,
            y=y_pos - dy,
            row=row,
            col=col,
            row_group=row_group_of[row],
            col_group=col_group_of[col],
        )
        for x_pos, y_pos, row, col in raw_cells
    )

    x_planes = _joint_planes(cells, hole_radius, axis="x", n_groups=n_col_groups)
    y_planes = _joint_planes(cells, hole_radius, axis="y", n_groups=n_row_groups)

    margin = params.holder_margin
    sections = _build_sections(
        cells,
        params,
        hole_radius,
        margin,
        x_planes,
        y_planes,
        n_row_groups,
        n_col_groups,
    )
    holder_bounds = _bbox_xy([(section.x0, section.y0, section.x1, section.y1) for section in sections])

    warnings: list[str] = []
    notes: list[str] = []
    wall_gap = params.cell_spacing - params.hole_clearance
    if wall_gap < MIN_INTERCELL_WALL_MM + 0.4:
        warnings.append(
            f"Plastic between neighbouring holes is only {wall_gap:.2f} mm. "
            "Add spacing if the slicer merges the walls."
        )
    if extra_y > 0.05:
        notes.append(
            f"Row sections are separated by an extra {extra_y:.1f} mm so a straight joint clears the cells."
        )
    if extra_x > 0.05:
        message = (
            f"Column sections are separated by an extra {extra_x:.1f} mm so a straight joint clears the cells."
        )
        if extra_x > 8.0:
            message += " Staggered packs need a wider lane for a vertical split. Splitting along rows is usually tighter."
        notes.append(message)
    if params.base_thickness > 0 and params.weld_window <= 0:
        notes.append(
            "The bottom holder has a solid floor, so the lower cell ends are covered. "
            "Open a weld window or set the base to 0 if you need to spot-weld that end."
        )
    elif params.base_thickness > 0 and params.weld_window > 0:
        ledge = (params.diameter + params.hole_clearance - params.weld_window) / 2.0
        if ledge < 2.2:
            warnings.append(
                f"The weld window leaves only a {ledge:.1f} mm ledge under each cell. "
                "Reduce the window if cells punch through the floor."
            )
    tongue_width = margin - 2.0 * TONGUE_SIDE_INSET_MM
    if (n_row_groups > 1 or n_col_groups > 1) and tongue_width < 1.4:
        warnings.append(
            "Holder margin is too small for interlocking tabs, so sections meet on a butt joint. "
            "Use at least 3.2 mm of margin for tabs."
        )

    enclosure = _build_enclosure(params, holder_bounds, sections, warnings, notes)
    part_plans = _part_plans(params, sections, enclosure)
    warnings.extend(_oversize_warnings(part_plans, params.max_print_mm))

    return PackLayout(
        params=params,
        rows=rows,
        cols=cols,
        pitch_x=pitch_x,
        pitch_y=pitch_y,
        staggered=staggered,
        hole_radius=hole_radius,
        cells=cells,
        sections=sections,
        extra_x=extra_x,
        extra_y=extra_y,
        x_planes=tuple(x_planes),
        y_planes=tuple(y_planes),
        holder_bounds=holder_bounds,
        wall_outer=enclosure["wall_outer"],
        bms_outer=enclosure["bms_outer"],
        case_extent=enclosure["case_extent"],
        lid_extent=enclosure["lid_extent"],
        case_total_z=enclosure["total_z"],
        floor=enclosure["floor"],
        internal_h=enclosure["internal_h"],
        cell_cavity=enclosure["cell_cavity"],
        bms_cavity=enclosure["bms_cavity"],
        top_opening=enclosure["top_opening"],
        top_zone=enclosure["top_zone"],
        magnets=enclosure["magnets"],
        tabs=enclosure["tabs"],
        clips=enclosure["clips"],
        lead_notch=enclosure["lead_notch"],
        part_plans=tuple(part_plans),
        warnings=tuple(warnings),
        notes=tuple(notes),
    )


def recommend_sections(params: PackParams) -> tuple[int, int]:
    """Smallest row/column split that brings every part under the printer limit.

    A single piece is preferred when it already fits. The search is exhaustive
    across section counts because the layout itself does no CAD.
    """
    rows, cols = params.resolved_rows_cols()
    best: tuple[tuple[float, float, float], int, int] | None = None
    row_choices = range(1, rows + 1)
    col_choices = range(1, cols + 1)
    if rows * cols > 80:
        # Keep the slider response snappy on big grids by splitting only the long side.
        if rows >= cols:
            col_choices = range(1, min(cols, 3) + 1)
        else:
            row_choices = range(1, min(rows, 3) + 1)
    for row_sections in row_choices:
        for col_sections in col_choices:
            trial = replace(params, row_sections=row_sections, col_sections=col_sections)
            layout = build_layout(trial)
            over = 0.0 if layout.fits_bed else 1.0
            score = (over, float(row_sections + col_sections), layout.max_part_mm)
            if best is None or score < best[0]:
                best = (score, row_sections, col_sections)
    assert best is not None
    return best[1], best[2]


def _joint_planes(
    cells: tuple[CellCenter, ...],
    hole_radius: float,
    axis: str,
    n_groups: int,
) -> list[float]:
    if n_groups <= 1:
        return []
    planes: list[float] = []
    for group_index in range(n_groups - 1):
        if axis == "x":
            left = [cell.x + hole_radius for cell in cells if cell.col_group == group_index]
            right = [cell.x - hole_radius for cell in cells if cell.col_group == group_index + 1]
        else:
            left = [cell.y + hole_radius for cell in cells if cell.row_group == group_index]
            right = [cell.y - hole_radius for cell in cells if cell.row_group == group_index + 1]
        left_edge = max(left)
        right_edge = min(right)
        planes.append((left_edge + right_edge) / 2.0)
    return planes


def _build_sections(
    cells: tuple[CellCenter, ...],
    params: PackParams,
    hole_radius: float,
    margin: float,
    x_planes: list[float],
    y_planes: list[float],
    n_row_groups: int,
    n_col_groups: int,
) -> tuple[SectionSpec, ...]:
    grouped: dict[tuple[int, int], list[CellCenter]] = {}
    for cell in cells:
        grouped.setdefault((cell.row_group, cell.col_group), []).append(cell)

    drafts: dict[tuple[int, int], dict] = {}
    for row_group in range(n_row_groups):
        for col_group in range(n_col_groups):
            members = grouped[(row_group, col_group)]
            min_x = min(cell.x for cell in members) - hole_radius
            max_x = max(cell.x for cell in members) + hole_radius
            min_y = min(cell.y for cell in members) - hole_radius
            max_y = max(cell.y for cell in members) + hole_radius
            joint_nx = col_group > 0
            joint_px = col_group < n_col_groups - 1
            joint_ny = row_group > 0
            joint_py = row_group < n_row_groups - 1
            x0 = x_planes[col_group - 1] if joint_nx else min_x - margin
            x1 = x_planes[col_group] if joint_px else max_x + margin
            y0 = y_planes[row_group - 1] if joint_ny else min_y - margin
            y1 = y_planes[row_group] if joint_py else max_y + margin
            drafts[(row_group, col_group)] = {
                "cells": tuple(members),
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "joint_nx": joint_nx,
                "joint_px": joint_px,
                "joint_ny": joint_ny,
                "joint_py": joint_py,
                "tongues": [],
            }

    tongues_enabled = margin - 2.0 * TONGUE_SIDE_INSET_MM >= 1.4
    if tongues_enabled:
        _add_tongues(drafts, n_row_groups, n_col_groups, margin)

    parallel_along_x = not (params.layout_mode == "series_parallel" and params.series_along == "columns")
    sections: list[SectionSpec] = []
    for row_group, col_group in sorted(drafts):
        draft = drafts[(row_group, col_group)]
        channels: tuple[ChannelSpec, ...] = ()
        slots: tuple[SlotSpec, ...] = ()
        if params.wire_channels:
            channels = tuple(_channels(draft, parallel_along_x))
        if params.strain_relief:
            slots = tuple(_slots(draft, parallel_along_x))
        sections.append(
            SectionSpec(
                row_group=row_group,
                col_group=col_group,
                n_row_groups=n_row_groups,
                n_col_groups=n_col_groups,
                cells=draft["cells"],
                x0=draft["x0"],
                y0=draft["y0"],
                x1=draft["x1"],
                y1=draft["y1"],
                joint_nx=draft["joint_nx"],
                joint_px=draft["joint_px"],
                joint_ny=draft["joint_ny"],
                joint_py=draft["joint_py"],
                tongues=tuple(draft["tongues"]),
                channels=channels,
                slots=slots,
            )
        )
    return tuple(sections)


def _add_tongues(
    drafts: dict[tuple[int, int], dict],
    n_row_groups: int,
    n_col_groups: int,
    margin: float,
) -> None:
    inset = TONGUE_SIDE_INSET_MM
    half_gap = BUTT_GAP_MM / 2.0
    for row_group in range(n_row_groups):
        for col_group in range(n_col_groups - 1):
            male = drafts[(row_group, col_group)]
            female = drafts[(row_group, col_group + 1)]
            plane = male["x1"]
            if not male["joint_py"]:
                _pair_tongue(
                    male,
                    female,
                    x0=plane - half_gap - 0.4,
                    x1=plane + TONGUE_LENGTH_MM,
                    y0=male["y1"] - margin + inset,
                    y1=male["y1"] - inset,
                    pocket_x0=plane + half_gap - 0.1,
                    pocket_y_grow=True,
                )
            if not male["joint_ny"]:
                _pair_tongue(
                    male,
                    female,
                    x0=plane - half_gap - 0.4,
                    x1=plane + TONGUE_LENGTH_MM,
                    y0=male["y0"] + inset,
                    y1=male["y0"] + margin - inset,
                    pocket_x0=plane + half_gap - 0.1,
                    pocket_y_grow=True,
                )
    for col_group in range(n_col_groups):
        for row_group in range(n_row_groups - 1):
            male = drafts[(row_group, col_group)]
            female = drafts[(row_group + 1, col_group)]
            plane = male["y1"]
            if not male["joint_px"]:
                _pair_tongue(
                    male,
                    female,
                    x0=male["x1"] - margin + inset,
                    x1=male["x1"] - inset,
                    y0=plane - half_gap - 0.4,
                    y1=plane + TONGUE_LENGTH_MM,
                    pocket_x0=plane + half_gap - 0.1,
                    pocket_y_grow=False,
                )
            if not male["joint_nx"]:
                _pair_tongue(
                    male,
                    female,
                    x0=male["x0"] + inset,
                    x1=male["x0"] + margin - inset,
                    y0=plane - half_gap - 0.4,
                    y1=plane + TONGUE_LENGTH_MM,
                    pocket_x0=plane + half_gap - 0.1,
                    pocket_y_grow=False,
                )


def _pair_tongue(
    male: dict,
    female: dict,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    pocket_x0: float,
    pocket_y_grow: bool,
) -> None:
    if x1 - x0 < 1.0 or y1 - y0 < 1.0:
        return
    male["tongues"].append(
        TongueSpec(x0=x0, y0=y0, x1=x1, y1=y1, z_fraction=TONGUE_Z_FRACTION, pocket=False)
    )
    grow = POCKET_CLEARANCE_MM
    if pocket_y_grow:
        female["tongues"].append(
            TongueSpec(
                x0=pocket_x0,
                y0=y0 - grow,
                x1=x1 + grow,
                y1=y1 + grow,
                z_fraction=TONGUE_Z_FRACTION,
                pocket=True,
            )
        )
    else:
        female["tongues"].append(
            TongueSpec(
                x0=x0 - grow,
                y0=pocket_x0,
                x1=x1 + grow,
                y1=y1 + grow,
                z_fraction=TONGUE_Z_FRACTION,
                pocket=True,
            )
        )


def _channels(draft: dict, along_x: bool) -> list[ChannelSpec]:
    grouped: dict[int, list[CellCenter]] = {}
    for cell in draft["cells"]:
        key = cell.row if along_x else cell.col
        grouped.setdefault(key, []).append(cell)
    channels: list[ChannelSpec] = []
    half = WIRE_CHANNEL_WIDTH_MM / 2.0
    for members in grouped.values():
        if len(members) < 2:
            continue
        if along_x:
            y_pos = members[0].y
            x0 = min(cell.x for cell in members)
            x1 = max(cell.x for cell in members)
            channels.append(
                ChannelSpec(x0=x0, y0=y_pos - half, x1=x1, y1=y_pos + half, depth=WIRE_CHANNEL_DEPTH_MM)
            )
        else:
            x_pos = members[0].x
            y0 = min(cell.y for cell in members)
            y1 = max(cell.y for cell in members)
            channels.append(
                ChannelSpec(x0=x_pos - half, y0=y0, x1=x_pos + half, y1=y1, depth=WIRE_CHANNEL_DEPTH_MM)
            )
    return channels


def _slots(draft: dict, along_x: bool) -> list[SlotSpec]:
    grouped: dict[int, list[CellCenter]] = {}
    for cell in draft["cells"]:
        key = cell.row if along_x else cell.col
        grouped.setdefault(key, []).append(cell)
    half = STRAIN_SLOT_WIDTH_MM / 2.0
    slots: list[SlotSpec] = []
    for members in grouped.values():
        if along_x:
            y_pos = members[0].y
            if not draft["joint_nx"]:
                x_hole = min(cell.x for cell in members)
                slots.append(
                    SlotSpec(
                        x0=draft["x0"] - 0.2,
                        y0=y_pos - half,
                        x1=x_hole,
                        y1=y_pos + half,
                        z0_fraction=STRAIN_SLOT_Z0_FRACTION,
                    )
                )
            if not draft["joint_px"]:
                x_hole = max(cell.x for cell in members)
                slots.append(
                    SlotSpec(
                        x0=x_hole,
                        y0=y_pos - half,
                        x1=draft["x1"] + 0.2,
                        y1=y_pos + half,
                        z0_fraction=STRAIN_SLOT_Z0_FRACTION,
                    )
                )
        else:
            x_pos = members[0].x
            if not draft["joint_ny"]:
                y_hole = min(cell.y for cell in members)
                slots.append(
                    SlotSpec(
                        x0=x_pos - half,
                        y0=draft["y0"] - 0.2,
                        x1=x_pos + half,
                        y1=y_hole,
                        z0_fraction=STRAIN_SLOT_Z0_FRACTION,
                    )
                )
            if not draft["joint_py"]:
                y_hole = max(cell.y for cell in members)
                slots.append(
                    SlotSpec(
                        x0=x_pos - half,
                        y0=y_hole,
                        x1=x_pos + half,
                        y1=draft["y1"] + 0.2,
                        z0_fraction=STRAIN_SLOT_Z0_FRACTION,
                    )
                )
    return slots


def _build_enclosure(
    params: PackParams,
    holder_bounds: tuple[float, float, float, float],
    sections: tuple[SectionSpec, ...],
    warnings: list[str],
    notes: list[str],
) -> dict:
    empty = {
        "wall_outer": None,
        "bms_outer": None,
        "case_boxes": [],
        "lid_boxes": [],
        "case_extent": None,
        "lid_extent": None,
        "total_z": 0.0,
        "floor": 0.0,
        "internal_h": 0.0,
        "cell_cavity": None,
        "bms_cavity": None,
        "top_opening": None,
        "top_zone": 0.0,
        "magnets": (),
        "tabs": (),
        "clips": (),
        "lead_notch": None,
    }
    hx0, hy0, hx1, hy1 = holder_bounds
    fit = params.case_fit
    cell_cavity = (hx0 - fit, hy0 - fit, hx1 + fit, hy1 + fit)
    stack = params.base_thickness + params.length + params.top_clearance
    if params.top_clearance < SKIRT_HEIGHT_MM + 1.0 and params.make_lid:
        warnings.append(
            f"Top clearance is {params.top_clearance:.1f} mm and the lid skirt hangs "
            f"{SKIRT_HEIGHT_MM:.1f} mm into the case. Raise top clearance so the skirt clears the cells."
        )

    bms_cavity = None
    lead_notch = None
    if params.bms_enabled:
        if params.bms_length < 50 or params.bms_width < 22 or params.bms_height < 12:
            warnings.append(
                "BMS bay is tight for a common e-bike board. Many boards need about "
                "60–80 mm by 20–35 mm and 12 mm of height, plus room for leads."
            )
        elif params.bms_length < 60 or params.bms_width < 26:
            notes.append(
                "Check the BMS bay against your board. Leave room for the balance-lead plug, not just the PCB."
            )
        anchor = _section_anchor(sections, params, fit)
        if anchor is not None:
            notes.append(
                "The BMS bay sits on the last split section so the joint does not cut through the board pocket."
            )
            if params.bms_width > (anchor[1] - anchor[0]):
                warnings.append(
                    "The BMS bay is wider than the end section, so the case split still cuts through it."
                )
        bms_cavity = _place_bms(cell_cavity, params, anchor)
        internal_h = max(stack, params.bms_height)
    else:
        internal_h = stack

    floor = params.floor_thickness if params.make_case else 0.0
    total_z = floor + internal_h if params.make_case else internal_h
    top_zone = params.wire_access if params.make_case and params.bms_enabled else 0.0
    # The skirt hangs into the cell bay. The wire window is the opened top of the divider.
    top_opening = cell_cavity

    if not params.make_case:
        empty["internal_h"] = internal_h
        empty["cell_cavity"] = cell_cavity
        empty["bms_cavity"] = bms_cavity
        empty["top_opening"] = top_opening
        empty["top_zone"] = top_zone
        return empty

    wall = params.case_wall
    cx0, cy0, cx1, cy1 = cell_cavity
    wall_outer = (cx0 - wall, cy0 - wall, cx1 + wall, cy1 + wall)
    bms_outer = _bms_shell(bms_cavity, params.bms_side, wall) if bms_cavity is not None else None

    magnets: tuple[MagnetSpec, ...] = ()
    if params.make_lid and params.lid_style == "magnets":
        magnets = tuple(_magnet_pads(wall_outer, params.magnet_diameter, params.magnet_depth))

    tabs: tuple[TabSpec, ...] = ()
    if params.mounting_tabs:
        tabs = tuple(_mounting_tabs(wall_outer, params, magnets))

    if bms_outer is not None and bms_cavity is not None:
        lead_notch = _lead_notch(bms_outer, bms_cavity, params.bms_side, total_z)
        tabs = tuple(
            tab for tab in tabs if not _rect_overlap((tab.x0, tab.y0, tab.x1, tab.y1), bms_outer, margin=0.4)
        )
    if params.mounting_tabs and not tabs:
        notes.append("No mounting tabs were added. The outline is too small to clear the corners and the lead notch.")

    clips: tuple[ClipSpec, ...] = ()
    if params.make_lid and params.lid_style == "clips":
        clips = tuple(_clips(wall_outer, total_z, lead_notch, params.bms_side if params.bms_enabled else None))
        if bms_outer is not None:
            clips = tuple(
                clip
                for clip in clips
                if not _rect_overlap((clip.rib_x0, clip.rib_y0, clip.rib_x1, clip.rib_y1), bms_outer, margin=0.4)
            )
        if clips:
            notes.append("Clip tabs are sized for PETG. Test the latch on a single clip before printing a full lid.")
        else:
            warnings.append("No room for clip tabs on this outline. Use a friction lid or magnets.")

    case_boxes = [wall_outer]
    if bms_outer is not None:
        case_boxes.append(bms_outer)
    case_boxes.extend((magnet.x0, magnet.y0, magnet.x1, magnet.y1) for magnet in magnets)
    case_boxes.extend((tab.x0, tab.y0, tab.x1, tab.y1) for tab in tabs)
    case_boxes.extend((clip.rib_x0, clip.rib_y0, clip.rib_x1, clip.rib_y1) for clip in clips)
    case_extent = _bbox_xy(case_boxes)

    lid_boxes = [wall_outer]
    if bms_outer is not None:
        lid_boxes.append(bms_outer)
    lid_boxes.extend((magnet.x0, magnet.y0, magnet.x1, magnet.y1) for magnet in magnets)
    lid_boxes.extend((clip.tab_x0, clip.tab_y0, clip.tab_x1, clip.tab_y1) for clip in clips)
    lid_boxes.extend((clip.hook_x0, clip.hook_y0, clip.hook_x1, clip.hook_y1) for clip in clips)
    lid_extent = _bbox_xy(lid_boxes) if params.make_lid else None

    return {
        "wall_outer": wall_outer,
        "bms_outer": bms_outer,
        "case_boxes": case_boxes,
        "lid_boxes": lid_boxes,
        "case_extent": case_extent,
        "lid_extent": lid_extent,
        "total_z": total_z,
        "floor": floor,
        "internal_h": internal_h,
        "cell_cavity": cell_cavity,
        "bms_cavity": bms_cavity,
        "top_opening": top_opening,
        "top_zone": top_zone,
        "magnets": magnets,
        "tabs": tabs,
        "clips": clips,
        "lead_notch": lead_notch,
    }


def _section_anchor(
    sections: tuple[SectionSpec, ...],
    params: PackParams,
    fit: float,
) -> tuple[float, float] | None:
    """Span the BMS width should occupy so a split does not slice the bay."""
    if params.bms_side in ("pos_x", "neg_x"):
        if sections[0].n_row_groups == 1:
            return None
        last = max(section.row_group for section in sections)
        group = [section for section in sections if section.row_group == last]
        return (min(section.y0 for section in group) - fit, max(section.y1 for section in group) + fit)
    if sections[0].n_col_groups == 1:
        return None
    last = max(section.col_group for section in sections)
    group = [section for section in sections if section.col_group == last]
    return (min(section.x0 for section in group) - fit, max(section.x1 for section in group) + fit)


def _bms_shell(
    cavity: tuple[float, float, float, float],
    side: str,
    wall: float,
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = cavity
    if side == "pos_x":
        return (x0, y0 - wall, x1 + wall, y1 + wall)
    if side == "neg_x":
        return (x0 - wall, y0 - wall, x1, y1 + wall)
    if side == "pos_y":
        return (x0 - wall, y0, x1 + wall, y1 + wall)
    return (x0 - wall, y0 - wall, x1 + wall, y1)


def _rect_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
    margin: float = 0.0,
) -> bool:
    return not (
        first[2] < second[0] - margin
        or first[0] > second[2] + margin
        or first[3] < second[1] - margin
        or first[1] > second[3] + margin
    )


def _place_bms(
    cell_cavity: tuple[float, float, float, float],
    params: PackParams,
    anchor: tuple[float, float] | None,
) -> tuple[float, float, float, float]:
    cx0, cy0, cx1, cy1 = cell_cavity
    divider = params.case_wall
    length = params.bms_length
    width = params.bms_width
    if params.bms_side == "pos_y":
        x0, x1 = _fit_span(cx0, cx1, width, anchor)
        y0 = cy1 + divider
        return (x0, y0, x1, y0 + length)
    if params.bms_side == "neg_y":
        x0, x1 = _fit_span(cx0, cx1, width, anchor)
        y1 = cy0 - divider
        return (x0, y1 - length, x1, y1)
    if params.bms_side == "pos_x":
        y0, y1 = _fit_span(cy0, cy1, width, anchor)
        x0 = cx1 + divider
        return (x0, y0, x0 + length, y1)
    y0, y1 = _fit_span(cy0, cy1, width, anchor)
    x1 = cx0 - divider
    return (x1 - length, y0, x1, y1)


def _fit_span(
    full0: float,
    full1: float,
    size: float,
    anchor: tuple[float, float] | None,
) -> tuple[float, float]:
    if anchor is None:
        return _centered(full0, full1, size)
    return _centered(anchor[0], anchor[1], size)


def _centered(a0: float, a1: float, size: float) -> tuple[float, float]:
    mid = (a0 + a1) / 2.0
    return (mid - size / 2.0, mid + size / 2.0)


def _magnet_pads(
    wall_outer: tuple[float, float, float, float],
    diameter: float,
    depth: float,
) -> list[MagnetSpec]:
    ox0, oy0, ox1, oy1 = wall_outer
    pad = diameter + MAGNET_PAD_EXTRA_MM
    overlap = MAGNET_PAD_OVERLAP_MM
    radius = diameter / 2.0
    specs: list[MagnetSpec] = []
    corners = ((ox0, oy0, -1, -1), (ox1, oy0, 1, -1), (ox0, oy1, -1, 1), (ox1, oy1, 1, 1))
    for corner_x, corner_y, sign_x, sign_y in corners:
        if sign_x > 0:
            x0 = corner_x - overlap
            x1 = x0 + pad
        else:
            x1 = corner_x + overlap
            x0 = x1 - pad
        if sign_y > 0:
            y0 = corner_y - overlap
            y1 = y0 + pad
        else:
            y1 = corner_y + overlap
            y0 = y1 - pad
        specs.append(_magnet(x0, y0, x1, y1, radius, depth))
    long_x = (ox1 - ox0) >= (oy1 - oy0)
    long_span = (ox1 - ox0) if long_x else (oy1 - oy0)
    if long_span > 170.0:
        if long_x:
            for y_edge, sign_y in ((oy0, -1), (oy1, 1)):
                x0 = (ox0 + ox1) / 2.0 - pad / 2.0
                x1 = x0 + pad
                if sign_y > 0:
                    y0 = y_edge - overlap
                    y1 = y0 + pad
                else:
                    y1 = y_edge + overlap
                    y0 = y1 - pad
                specs.append(_magnet(x0, y0, x1, y1, radius, depth))
        else:
            for x_edge, sign_x in ((ox0, -1), (ox1, 1)):
                y0 = (oy0 + oy1) / 2.0 - pad / 2.0
                y1 = y0 + pad
                if sign_x > 0:
                    x0 = x_edge - overlap
                    x1 = x0 + pad
                else:
                    x1 = x_edge + overlap
                    x0 = x1 - pad
                specs.append(_magnet(x0, y0, x1, y1, radius, depth))
    return specs


def _magnet(x0: float, y0: float, x1: float, y1: float, radius: float, depth: float) -> MagnetSpec:
    return MagnetSpec(
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        cx=(x0 + x1) / 2.0,
        cy=(y0 + y1) / 2.0,
        radius=radius,
        depth=depth,
    )


def _mounting_tabs(
    wall_outer: tuple[float, float, float, float],
    params: PackParams,
    magnets: tuple[MagnetSpec, ...],
) -> list[TabSpec]:
    ox0, oy0, ox1, oy1 = wall_outer
    hole_d = screw_hole_diameter(params.screw)
    thickness = max(params.floor_thickness, TAB_MIN_THICKNESS_MM)
    keepout = max((magnet.x1 - magnet.x0) for magnet in magnets) if magnets else 8.0
    tabs: list[TabSpec] = []
    candidates = (
        ("pos_x", oy1 - oy0),
        ("neg_x", oy1 - oy0),
        ("pos_y", ox1 - ox0),
        ("neg_y", ox1 - ox0),
    )
    for side, span in candidates:
        if span < TAB_ALONG_MM + 2.0 * keepout + 4.0:
            continue
        center = _side_center(side, wall_outer)
        if params.bms_enabled and _notch_on_side(side, params.bms_side):
            shift = LEAD_NOTCH_WIDTH_MM / 2.0 + TAB_ALONG_MM / 2.0 + 3.0
            center += shift if center <= _side_mid(side, wall_outer) else -shift
        if not _tab_fits(side, center, span, keepout, wall_outer):
            continue
        tabs.append(_make_tab(side, center, wall_outer, thickness, hole_d))
    return tabs


def _side_mid(side: str, wall_outer: tuple[float, float, float, float]) -> float:
    ox0, oy0, ox1, oy1 = wall_outer
    if side in ("pos_x", "neg_x"):
        return (oy0 + oy1) / 2.0
    return (ox0 + ox1) / 2.0


def _side_center(side: str, wall_outer: tuple[float, float, float, float]) -> float:
    return _side_mid(side, wall_outer)


def _notch_on_side(side: str, bms_side: str) -> bool:
    return side == bms_side


def _tab_fits(
    side: str,
    center: float,
    span: float,
    keepout: float,
    wall_outer: tuple[float, float, float, float],
) -> bool:
    ox0, oy0, ox1, oy1 = wall_outer
    half = TAB_ALONG_MM / 2.0
    if side in ("pos_x", "neg_x"):
        return oy0 + keepout + 1.0 <= center - half and center + half <= oy1 - keepout - 1.0
    return ox0 + keepout + 1.0 <= center - half and center + half <= ox1 - keepout - 1.0


def _make_tab(
    side: str,
    center: float,
    wall_outer: tuple[float, float, float, float],
    thickness: float,
    hole_d: float,
) -> TabSpec:
    ox0, oy0, ox1, oy1 = wall_outer
    half = TAB_ALONG_MM / 2.0
    outward = TAB_OUT_MM
    embed = 0.3
    if side == "pos_x":
        x0, x1 = ox1 - embed, ox1 - embed + outward
        y0, y1 = center - half, center + half
        hole_x, hole_y = ox1 + outward * 0.58, center
    elif side == "neg_x":
        x0, x1 = ox0 + embed - outward, ox0 + embed
        y0, y1 = center - half, center + half
        hole_x, hole_y = ox0 - outward * 0.58, center
    elif side == "pos_y":
        x0, x1 = center - half, center + half
        y0, y1 = oy1 - embed, oy1 - embed + outward
        hole_x, hole_y = center, oy1 + outward * 0.58
    else:
        x0, x1 = center - half, center + half
        y0, y1 = oy0 + embed - outward, oy0 + embed
        hole_x, hole_y = center, oy0 - outward * 0.58
    return TabSpec(
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        thickness=thickness,
        hole_d=hole_d,
        hole_x=hole_x,
        hole_y=hole_y,
    )


def _lead_notch(
    wall_outer: tuple[float, float, float, float],
    bms_cavity: tuple[float, float, float, float],
    side: str,
    total_z: float,
) -> tuple[float, float, float, float, float, float]:
    """Notch through the outer wall on the BMS side, open toward the lid.

    Returns (x0, y0, z0, x1, y1, z1).
    """
    ox0, oy0, ox1, oy1 = wall_outer
    bx0, by0, bx1, by1 = bms_cavity
    z0 = total_z - LEAD_NOTCH_DEPTH_MM
    z1 = total_z + 0.2
    if side == "pos_y":
        x0, x1 = _centered(bx0, bx1, LEAD_NOTCH_WIDTH_MM)
        return (x0, by1 - 0.6, z0, x1, oy1 + 0.6, z1)
    if side == "neg_y":
        x0, x1 = _centered(bx0, bx1, LEAD_NOTCH_WIDTH_MM)
        return (x0, oy0 - 0.6, z0, x1, by0 + 0.6, z1)
    if side == "pos_x":
        y0, y1 = _centered(by0, by1, LEAD_NOTCH_WIDTH_MM)
        return (bx1 - 0.6, y0, z0, ox1 + 0.6, y1, z1)
    y0, y1 = _centered(by0, by1, LEAD_NOTCH_WIDTH_MM)
    return (ox0 - 0.6, y0, z0, bx0 + 0.6, y1, z1)


def _clips(
    wall_outer: tuple[float, float, float, float],
    total_z: float,
    lead_notch: tuple[float, float, float, float, float, float] | None,
    bms_side: str | None,
) -> list[ClipSpec]:
    ox0, oy0, ox1, oy1 = wall_outer
    spans = {
        "pos_x": oy1 - oy0,
        "neg_x": oy1 - oy0,
        "pos_y": ox1 - ox0,
        "neg_y": ox1 - ox0,
    }
    clips: list[ClipSpec] = []
    for side, span in spans.items():
        blocked = bms_side == side and lead_notch is not None
        if span < CLIP_WIDTH_MM + 16.0:
            continue
        if blocked and span < CLIP_WIDTH_MM * 2 + LEAD_NOTCH_WIDTH_MM + 20.0:
            continue
        centers = [_side_mid(side, wall_outer)]
        if blocked:
            shift = LEAD_NOTCH_WIDTH_MM / 2.0 + CLIP_WIDTH_MM / 2.0 + 4.0
            mid = centers[0]
            centers = [mid - shift, mid + shift]
        for center in centers:
            if not _clip_center_fits(side, center, wall_outer):
                continue
            clips.append(_make_clip(side, center, wall_outer, total_z))
    return clips


def _clip_center_fits(
    side: str,
    center: float,
    wall_outer: tuple[float, float, float, float],
) -> bool:
    ox0, oy0, ox1, oy1 = wall_outer
    half = CLIP_WIDTH_MM / 2.0 + 2.0
    if side in ("pos_x", "neg_x"):
        return oy0 + half <= center <= oy1 - half
    return ox0 + half <= center <= ox1 - half


def _make_clip(
    side: str,
    center: float,
    wall_outer: tuple[float, float, float, float],
    total_z: float,
) -> ClipSpec:
    ox0, oy0, ox1, oy1 = wall_outer
    half = CLIP_WIDTH_MM / 2.0
    tab_half = half - 0.6
    protrusion = CLIP_RIB_PROTRUSION_MM
    gap = CLIP_TAB_GAP_MM
    tab_t = CLIP_TAB_THICKNESS_MM
    rib_z1 = total_z - CLIP_RIB_BELOW_TOP_MM
    rib_z0 = rib_z1 - CLIP_RIB_HEIGHT_MM
    hook_z0 = CLIP_RIB_BELOW_TOP_MM + CLIP_RIB_HEIGHT_MM + 0.35
    hook_z1 = hook_z0 + 1.8
    drop = hook_z1 + 0.3
    if side == "pos_y":
        rib = (center - half, oy1, center + half, oy1 + protrusion)
        tab = (center - tab_half, rib[3] + gap, center + tab_half, rib[3] + gap + tab_t)
        hook = (tab[0], oy1 + 0.45, tab[2], tab[1])
    elif side == "neg_y":
        rib = (center - half, oy0 - protrusion, center + half, oy0)
        tab = (center - tab_half, rib[1] - gap - tab_t, center + tab_half, rib[1] - gap)
        hook = (tab[0], tab[3], tab[2], oy0 - 0.45)
    elif side == "pos_x":
        rib = (ox1, center - half, ox1 + protrusion, center + half)
        tab = (rib[2] + gap, center - tab_half, rib[2] + gap + tab_t, center + tab_half)
        hook = (ox1 + 0.45, tab[1], tab[0], tab[3])
    else:
        rib = (ox0 - protrusion, center - half, ox0, center + half)
        tab = (rib[0] - gap - tab_t, center - tab_half, rib[0] - gap, center + tab_half)
        hook = (tab[2], tab[1], ox0 - 0.45, tab[3])
    return ClipSpec(
        side=side,
        rib_x0=rib[0],
        rib_y0=rib[1],
        rib_x1=rib[2],
        rib_y1=rib[3],
        rib_z0=rib_z0,
        rib_z1=rib_z1,
        tab_x0=tab[0],
        tab_y0=tab[1],
        tab_x1=tab[2],
        tab_y1=tab[3],
        hook_x0=hook[0],
        hook_y0=hook[1],
        hook_x1=hook[2],
        hook_y1=hook[3],
        hook_z0=hook_z0,
        hook_z1=hook_z1,
        drop=drop,
    )


def _part_plans(params: PackParams, sections: tuple[SectionSpec, ...], enclosure: dict) -> list[PartPlan]:
    plans: list[PartPlan] = []
    for section in sections:
        bounds = _section_print_bounds(section)
        sx, sy = bounds[2] - bounds[0], bounds[3] - bounds[1]
        plans.append(PartPlan(f"holder_bottom{section.suffix}.stl", "holder_bottom", sx, sy, params.holder_height))
        if params.make_top_holder:
            plans.append(
                PartPlan(
                    f"holder_top{section.suffix}.stl",
                    "holder_top",
                    sx,
                    sy,
                    params.top_holder_height,
                )
            )
    if params.make_case and enclosure["case_boxes"]:
        plans.extend(
            _split_plans(
                "case",
                "case",
                enclosure["case_boxes"],
                enclosure["total_z"],
                sections,
            )
        )
    if params.make_lid and enclosure["lid_boxes"]:
        lid_z = params.lid_thickness + SKIRT_HEIGHT_MM
        if params.lid_style == "clips" and enclosure["clips"]:
            lid_z = params.lid_thickness + max(clip.drop for clip in enclosure["clips"])
        plans.extend(
            _split_plans(
                "lid",
                "lid",
                enclosure["lid_boxes"],
                lid_z,
                sections,
            )
        )
    return plans


def _section_print_bounds(section: SectionSpec) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = section.x0, section.y0, section.x1, section.y1
    for tongue in section.tongues:
        if tongue.pocket:
            continue
        x0 = min(x0, tongue.x0)
        y0 = min(y0, tongue.y0)
        x1 = max(x1, tongue.x1)
        y1 = max(y1, tongue.y1)
    return (x0, y0, x1, y1)


def _split_plans(
    stem: str,
    role: str,
    boxes: list[tuple[float, float, float, float]],
    z_size: float,
    sections: tuple[SectionSpec, ...],
) -> list[PartPlan]:
    if not boxes:
        return []
    if sections[0].n_row_groups == 1 and sections[0].n_col_groups == 1:
        sx, sy, _ = _size_of(_bbox_xy(boxes), z_size)
        return [PartPlan(f"{stem}.stl", role, sx, sy, z_size)]
    extent = _bbox_xy(boxes)
    x_planes = sorted({section.x1 for section in sections if section.joint_px})
    y_planes = sorted({section.y1 for section in sections if section.joint_py})
    plans: list[PartPlan] = []
    for section in sections:
        window = _section_window(section, extent, x_planes, y_planes)
        clipped = [hit for box in boxes if (hit := _clip_box(box, window)) is not None]
        bounds = _bbox_xy(clipped) if clipped else window
        plans.append(
            PartPlan(
                f"{stem}{section.suffix}.stl",
                role,
                bounds[2] - bounds[0],
                bounds[3] - bounds[1],
                z_size,
            )
        )
    return plans


def _section_window(
    section: SectionSpec,
    extent: tuple[float, float, float, float],
    x_planes: list[float],
    y_planes: list[float],
) -> tuple[float, float, float, float]:
    ex0, ey0, ex1, ey1 = extent
    pad = 1.0
    if section.n_col_groups == 1:
        x0, x1 = ex0 - pad, ex1 + pad
    else:
        xs = [ex0 - pad, *x_planes, ex1 + pad]
        x0 = xs[section.col_group]
        x1 = xs[section.col_group + 1]
        if section.joint_nx:
            x0 -= CASE_LAP_MM
        if section.joint_px:
            x1 += CASE_LAP_MM
    if section.n_row_groups == 1:
        y0, y1 = ey0 - pad, ey1 + pad
    else:
        ys = [ey0 - pad, *y_planes, ey1 + pad]
        y0 = ys[section.row_group]
        y1 = ys[section.row_group + 1]
        if section.joint_ny:
            y0 -= CASE_LAP_MM
        if section.joint_py:
            y1 += CASE_LAP_MM
    return (x0, y0, x1, y1)


def _clip_box(
    box: tuple[float, float, float, float],
    window: tuple[float, float, float, float],
) -> tuple[float, float, float, float] | None:
    x0 = max(box[0], window[0])
    y0 = max(box[1], window[1])
    x1 = min(box[2], window[2])
    y1 = min(box[3], window[3])
    if x1 - x0 < 0.2 or y1 - y0 < 0.2:
        return None
    return (x0, y0, x1, y1)


def _oversize_warnings(plans: list[PartPlan], limit: float) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()
    for plan in plans:
        over = []
        for axis, value in (("X", plan.sx), ("Y", plan.sy), ("Z", plan.sz)):
            if value > limit:
                over.append(f"{axis} {value:.0f} mm")
        if not over or plan.name in seen:
            continue
        seen.add(plan.name)
        hard = plan.max_dim > TYPICAL_BED_HARD_MM
        limit_text = (
            f"over a typical {TYPICAL_BED_HARD_MM:.0f} mm desktop bed"
            if hard
            else f"over the {limit:.0f} mm printer limit"
        )
        warnings.append(
            f"{plan.name} is {plan.sx:.0f} × {plan.sy:.0f} × {plan.sz:.0f} mm, {limit_text} "
            f"({', '.join(over)}). Split the pack into more row or column sections."
        )
    return warnings
