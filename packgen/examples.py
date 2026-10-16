"""Named configurations shared by the CLI, tests, and Streamlit presets."""

from __future__ import annotations

from packgen.models import PackParams

def example_4s2p() -> PackParams:
    """Small rectangular pack used as the app default and the fast demo."""
    return PackParams(
        cell_preset="18650",
        diameter=18.5,
        length=65.2,
        layout_mode="series_parallel",
        series=4,
        parallel=2,
        series_along="rows",
        packing="rectangular",
        bms_enabled=True,
        bms_length=60.0,
        bms_width=28.0,
        bms_height=16.0,
        bms_side="pos_y",
        lid_style="friction",
        row_sections=1,
        col_sections=1,
    )


def example_13s4p() -> PackParams:
    """Staggered 13S4P 18650 holder with a side BMS bay.

    Two row sections keep each printed part inside a 240 mm bed. A single
    section is near or over that limit; the app will say so if you set row
    sections back to 1.
    """
    return PackParams(
        cell_preset="18650",
        diameter=18.5,
        length=65.2,
        layout_mode="series_parallel",
        series=13,
        parallel=4,
        rows=13,
        cols=4,
        series_along="rows",
        packing="staggered",
        cell_spacing=2.0,
        hole_clearance=0.4,
        holder_margin=4.0,
        holder_height=15.0,
        base_thickness=1.6,
        weld_window=10.0,
        make_top_holder=True,
        top_holder_height=12.0,
        wire_channels=True,
        strain_relief=True,
        make_case=True,
        make_lid=True,
        case_wall=2.4,
        floor_thickness=2.4,
        case_fit=0.4,
        top_clearance=6.0,
        lid_thickness=3.4,
        lid_style="magnets",
        magnet_diameter=6.4,
        magnet_depth=2.2,
        mounting_tabs=True,
        screw="M4",
        bms_enabled=True,
        bms_length=70.0,
        bms_width=32.0,
        bms_height=18.0,
        bms_side="pos_x",
        wire_access=12.0,
        row_sections=2,
        col_sections=1,
        max_print_mm=240.0,
    )


EXAMPLES: dict[str, PackParams] = {
    "4s2p": example_4s2p(),
    "13s4p": example_13s4p(),
}
