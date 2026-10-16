"""CadQuery solids for small packs, plus the lap joint used on large cases."""

import struct

from packgen.build import build_parts
from packgen.cqutil import make_box, split_along_planes, volume
from packgen.examples import example_4s2p
from packgen.layout import build_layout
from packgen.models import PackParams


def _triangle_count(data: bytes) -> int:
    assert len(data) >= 84
    count = struct.unpack_from("<I", data, 80)[0]
    assert count > 0
    assert len(data) >= 84 + count * 50
    return count


def test_lap_joint_parts_meet_without_overlapping():
    solid = make_box(-40, -15, 0, 40, 15, 20)
    left, right = split_along_planes(solid, [0.0], "x", lap=3.0, clearance=0.2)
    assert volume(left) > 1000
    assert volume(right) > 1000
    overlap = volume(left.intersect(right))
    assert overlap < 1.0
    # Clearance removes a little material, but the pair still fills the blank.
    assert volume(left) + volume(right) > volume(solid) * 0.9


def test_small_pack_exports_valid_stls_close_to_the_plan():
    layout = build_layout(example_4s2p())
    result = build_parts(layout, export=True, tolerance=0.2)
    assert result.errors == []
    plans = {plan.name: plan for plan in layout.part_plans}
    assert {part.name for part in result.parts} == set(plans)
    for part in result.parts:
        assert part.error is None
        assert part.stl is not None
        _triangle_count(part.stl)
        plan = plans[part.name]
        for actual, expected in zip(part.size, (plan.sx, plan.sy, plan.sz)):
            assert abs(actual - expected) < 3.0, (part.name, part.size, (plan.sx, plan.sy, plan.sz))
    # The case has to be a shell. A missed cavity cut would leave nearly the full block.
    case = next(part for part in result.parts if part.role == "case")
    outer = make_box(
        layout.case_extent[0],
        layout.case_extent[1],
        0.0,
        layout.case_extent[2],
        layout.case_extent[3],
        layout.case_total_z,
    )
    assert case.stl is not None
    shell = build_parts(layout, export=False).parts
    case_solid = next(part for part in shell if part.role == "case")
    assert volume(case_solid.solid) < volume(outer) * 0.55


def test_split_staggered_pack_with_clips_and_side_bms():
    params = PackParams(
        layout_mode="grid",
        rows=3,
        cols=2,
        packing="staggered",
        row_sections=2,
        col_sections=1,
        bms_enabled=True,
        bms_side="pos_x",
        bms_length=50,
        bms_width=24,
        bms_height=16,
        lid_style="clips",
        mounting_tabs=True,
        make_top_holder=True,
        wire_channels=True,
        strain_relief=True,
    )
    layout = build_layout(params)
    result = build_parts(layout, export=True, tolerance=0.25)
    assert result.errors == []
    holders = [part for part in result.parts if part.role == "holder_bottom"]
    cases = [part for part in result.parts if part.role == "case"]
    lids = [part for part in result.parts if part.role == "lid"]
    assert len(holders) == 2
    assert len(cases) == 2
    assert len(lids) == 2
    # The two holder sections share the column axis and split the row axis.
    full_y = layout.holder_bounds[3] - layout.holder_bounds[1]
    assert holders[0].size[1] < full_y - 5
    assert holders[1].size[1] < full_y - 5
    # Odd staggered rows stick out by half a pitch, so the X spans are not equal.
    assert abs(holders[0].size[0] - holders[1].size[0]) < layout.pitch_x


def test_magnet_lid_and_through_holes_remove_material():
    params = example_4s2p()
    params = PackParams.from_dict({**params.to_dict(), "lid_style": "magnets", "bms_enabled": False})
    layout = build_layout(params)
    result = build_parts(layout, export=False)
    assert result.errors == []
    holder = next(part for part in result.parts if part.role == "holder_bottom")
    # export=False keeps the solid for inspection
    assert holder.solid is not None
    solid_box = make_box(
        layout.holder_bounds[0],
        layout.holder_bounds[1],
        0,
        layout.holder_bounds[2],
        layout.holder_bounds[3],
        params.holder_height,
    )
    assert volume(holder.solid) < volume(solid_box) * 0.85
