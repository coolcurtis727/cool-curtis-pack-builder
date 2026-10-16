"""Layout math that does not need CadQuery."""

import io
import math
import struct

from packgen.constants import MIN_LAND_MM
from packgen.examples import example_13s4p, example_4s2p
from packgen.layout import build_layout, recommend_sections
from packgen.models import PackParams, validate
from packgen.preview import draw_layout


def test_series_parallel_grid_and_count():
    layout = build_layout(example_13s4p())
    assert layout.rows == 13
    assert layout.cols == 4
    assert layout.cell_count == 52
    assert layout.staggered
    assert layout.pitch_y == layout.pitch_x * math.sqrt(3) / 2


def test_swap_series_direction():
    params = PackParams(layout_mode="series_parallel", series=10, parallel=3, series_along="columns")
    layout = build_layout(params)
    assert (layout.rows, layout.cols) == (3, 10)


def test_rectangular_pitch_and_centred_pack():
    layout = build_layout(example_4s2p())
    xs = sorted({round(cell.x, 4) for cell in layout.cells})
    assert len(xs) == 2
    assert abs((xs[1] - xs[0]) - layout.pitch_x) < 1e-6
    assert abs(min(cell.x for cell in layout.cells) + max(cell.x for cell in layout.cells)) < 1e-6
    assert abs(min(cell.y for cell in layout.cells) + max(cell.y for cell in layout.cells)) < 1e-6


def test_staggered_neighbours_keep_equal_pitch():
    layout = build_layout(example_13s4p())
    by_row = {}
    for cell in layout.cells:
        by_row.setdefault(cell.row, []).append(cell)
    row0 = sorted(by_row[0], key=lambda cell: cell.x)
    row1 = sorted(by_row[1], key=lambda cell: cell.x)
    distance = math.hypot(row1[0].x - row0[0].x, row1[0].y - row0[0].y)
    assert abs(distance - layout.pitch_x) < 0.05


def test_split_keeps_a_land_around_every_hole():
    params = PackParams(
        layout_mode="grid",
        rows=5,
        cols=4,
        packing="staggered",
        row_sections=2,
        col_sections=2,
        cell_spacing=2.0,
        hole_clearance=0.4,
        diameter=18.5,
    )
    layout = build_layout(params)
    assert layout.extra_x > 8.0
    assert layout.extra_y > 3.0
    for cell in layout.cells:
        for plane in layout.x_planes:
            assert abs(cell.x - plane) >= layout.hole_radius + MIN_LAND_MM - 0.05
        for plane in layout.y_planes:
            assert abs(cell.y - plane) >= layout.hole_radius + MIN_LAND_MM - 0.05


def test_tongues_stay_out_of_the_cell_holes():
    params = PackParams(
        layout_mode="grid",
        rows=4,
        cols=4,
        packing="rectangular",
        row_sections=2,
        col_sections=2,
    )
    layout = build_layout(params)
    tongues = [tongue for section in layout.sections for tongue in section.tongues if not tongue.pocket]
    assert tongues
    for tongue in tongues:
        for cell in layout.cells:
            # Distance from the cell centre to the tongue rectangle.
            dx = max(tongue.x0 - cell.x, 0.0, cell.x - tongue.x1)
            dy = max(tongue.y0 - cell.y, 0.0, cell.y - tongue.y1)
            assert math.hypot(dx, dy) >= layout.hole_radius - 0.05


def test_case_cavity_contains_the_holder_and_bms_gap_matches_the_wall():
    layout = build_layout(example_4s2p())
    hx0, hy0, hx1, hy1 = layout.holder_bounds
    cx0, cy0, cx1, cy1 = layout.cell_cavity
    assert cx0 < hx0 and cy0 < hy0 and cx1 > hx1 and cy1 > hy1
    assert layout.bms_cavity is not None
    gap = layout.bms_cavity[1] - cy1
    assert abs(gap - example_4s2p().case_wall) < 1e-6


def test_side_bms_grows_x():
    end = build_layout(example_13s4p())
    assert end.params.bms_side == "pos_x"
    assert end.bms_cavity is not None
    assert end.bms_cavity[0] > end.cell_cavity[2]


def test_oversized_pack_warns_and_recommends_a_split():
    params = PackParams(
        layout_mode="series_parallel",
        series=13,
        parallel=4,
        packing="staggered",
        bms_enabled=True,
        bms_side="pos_x",
        bms_length=70,
        bms_width=32,
        row_sections=1,
        col_sections=1,
        max_print_mm=240,
    )
    errors = validate(params)
    assert errors == []
    layout = build_layout(params)
    assert not layout.fits_bed
    assert any("printer limit" in warning or "desktop bed" in warning for warning in layout.warnings)
    rows, cols = recommend_sections(params)
    fitted = build_layout(PackParams.from_dict({**params.to_dict(), "row_sections": rows, "col_sections": cols}))
    assert fitted.fits_bed
    assert rows > 1 or cols > 1


def test_default_13s4p_example_fits_a_240_mm_bed():
    layout = build_layout(example_13s4p())
    assert layout.fits_bed
    assert layout.part_plans
    names = [plan.name for plan in layout.part_plans]
    assert len(names) == len(set(names))
    assert any(name.startswith("holder_bottom") for name in names)
    assert any(name.startswith("case_") for name in names)
    assert any(name.startswith("lid_") for name in names)


def test_validation_rejects_overlapping_holes():
    params = PackParams(cell_spacing=0.5, hole_clearance=0.4)
    errors = validate(params)
    assert any("Holes would nearly touch" in error for error in errors)


def test_layout_drawing_stays_a_normal_image():
    """Streamlit saves with a tight crop. An unset axis limit turns that into a multi-gigabyte bitmap."""
    for params in (example_4s2p(), example_13s4p()):
        figure = draw_layout(build_layout(params))
        buffer = io.BytesIO()
        figure.savefig(buffer, format="png", dpi=100, bbox_inches="tight")
        data = buffer.getvalue()
        width, height = struct.unpack(">II", data[16:24])
        assert width < 2000
        assert height < 1600
        assert len(data) < 1_500_000
