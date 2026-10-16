"""Streamlit UI for the cylindrical-cell pack builder."""

from __future__ import annotations

import io
import json
import zipfile

import streamlit as st

from packgen.build import build_parts
from packgen.examples import EXAMPLES, example_4s2p
from packgen.layout import build_layout, recommend_sections
from packgen.models import BMS_SIDE_LABELS, CELL_PRESETS, LID_STYLES, PackParams, validate
from packgen.notes import print_notes
from packgen.preview import draw_layout, stl_mesh

st.set_page_config(page_title="Cylindrical cell pack builder", layout="wide")


def main() -> None:
    _init_state()
    st.title("Cylindrical cell pack builder")
    st.caption(
        "Parametric holders, cases, and lids for 18650 and 21700 e-bike or scooter packs. "
        "Mechanical generator only — you still own cell matching, fusing, the BMS rating, insulation, and charging."
    )
    controls, preview = st.columns([1.05, 1.25], gap="large")
    with controls:
        _presets()
        _cell_controls()
        _layout_controls()
        _holder_controls()
        _case_controls()
        _bms_controls()
        _printer_controls()
    params = _params_from_state()
    errors = validate(params)
    with preview:
        if errors:
            for error in errors:
                st.error(error)
            layout = None
        else:
            layout = build_layout(params)
            _summary(layout)
            figure = draw_layout(layout)
            st.pyplot(figure, clear_figure=True)
            _messages(layout)
    st.markdown(print_notes(params, layout if not errors else None))
    if errors or layout is None:
        return
    _exports(params, layout)


def _init_state() -> None:
    defaults = example_4s2p().to_dict()
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if "layout_mode_label" not in st.session_state:
        _sync_labels(st.session_state)


def _presets() -> None:
    st.subheader("Start from")
    picked = st.radio(
        "Configuration",
        ["4S2P rectangular", "13S4P staggered + side BMS", "Custom"],
        horizontal=True,
        label_visibility="collapsed",
    )
    if st.button("Load this configuration", width="stretch"):
        if picked.startswith("4S2P"):
            _apply(EXAMPLES["4s2p"])
        elif picked.startswith("13S4P"):
            _apply(EXAMPLES["13s4p"])
        st.rerun()


def _apply(params: PackParams) -> None:
    for key, value in params.to_dict().items():
        st.session_state[key] = value
    _sync_labels(st.session_state)
    st.session_state["exports"] = None


def _sync_labels(state) -> None:
    state["layout_mode_label"] = (
        "Series / parallel" if state["layout_mode"] == "series_parallel" else "Rows × columns"
    )
    state["series_along_label"] = (
        "Along rows (each row is a parallel group)"
        if state["series_along"] == "rows"
        else "Along columns (each column is a parallel group)"
    )
    state["packing_label"] = "Rectangular" if state["packing"] == "rectangular" else "Staggered (hex)"


def _cell_controls() -> None:
    with st.expander("Cell", expanded=True):
        st.selectbox("Preset", list(CELL_PRESETS), key="cell_preset", on_change=_sync_preset)
        note = str(CELL_PRESETS[st.session_state.cell_preset]["note"])
        st.caption(note)
        disabled = st.session_state.cell_preset != "Custom"
        st.slider("Diameter (mm)", 10.0, 28.0, step=0.1, key="diameter", disabled=disabled)
        st.slider("Length (mm)", 40.0, 90.0, step=0.1, key="length", disabled=disabled)
        if disabled:
            st.caption("Switch the preset to Custom to type your own measurements.")


def _sync_preset() -> None:
    preset = CELL_PRESETS[st.session_state.cell_preset]
    if st.session_state.cell_preset != "Custom":
        st.session_state.diameter = float(preset["diameter"])
        st.session_state.length = float(preset["length"])


def _layout_controls() -> None:
    with st.expander("Layout", expanded=True):
        st.radio("Entry", ["Series / parallel", "Rows × columns"], key="layout_mode_label", horizontal=True)
        st.session_state.layout_mode = (
            "series_parallel" if st.session_state.layout_mode_label.startswith("Series") else "grid"
        )
        if st.session_state.layout_mode == "series_parallel":
            left, right = st.columns(2)
            left.number_input("Series groups", min_value=1, max_value=24, step=1, key="series")
            right.number_input("Parallel cells", min_value=1, max_value=12, step=1, key="parallel")
            st.selectbox(
                "Series direction",
                ["Along rows (each row is a parallel group)", "Along columns (each column is a parallel group)"],
                key="series_along_label",
            )
            st.session_state.series_along = (
                "rows" if st.session_state.series_along_label.startswith("Along rows") else "columns"
            )
        else:
            left, right = st.columns(2)
            left.number_input("Rows", min_value=1, max_value=24, step=1, key="rows")
            right.number_input("Columns", min_value=1, max_value=12, step=1, key="cols")
        st.radio("Packing", ["Rectangular", "Staggered (hex)"], key="packing_label", horizontal=True)
        st.session_state.packing = "rectangular" if st.session_state.packing_label.startswith("Rect") else "staggered"
        st.slider("Cell spacing (mm)", 0.8, 6.0, step=0.1, key="cell_spacing")
        st.slider("Hole clearance (mm)", 0.0, 1.2, step=0.05, key="hole_clearance")
        rows, cols = _preview_grid()
        st.session_state.row_sections = min(int(st.session_state.row_sections), rows)
        st.session_state.col_sections = min(int(st.session_state.col_sections), cols)
        left, right = st.columns(2)
        left.number_input("Row sections", min_value=1, max_value=rows, step=1, key="row_sections")
        right.number_input("Column sections", min_value=1, max_value=cols, step=1, key="col_sections")
        st.caption("Sections are printed separately and nest with rim tabs. Use them when a part exceeds the bed.")


def _preview_grid() -> tuple[int, int]:
    if st.session_state.layout_mode == "grid":
        return int(st.session_state.rows), int(st.session_state.cols)
    if st.session_state.get("series_along", "rows") == "columns":
        return int(st.session_state.parallel), int(st.session_state.series)
    return int(st.session_state.series), int(st.session_state.parallel)


def _holder_controls() -> None:
    with st.expander("Holder", expanded=False):
        st.slider("Rim margin (mm)", 2.4, 8.0, step=0.1, key="holder_margin")
        st.slider("Bottom holder height (mm)", 8.0, 30.0, step=0.5, key="holder_height")
        st.slider("Base thickness (mm)", 0.0, 4.0, step=0.1, key="base_thickness")
        window_max = max(1.0, float(st.session_state.diameter) - 1.0)
        st.session_state.weld_window = min(float(st.session_state.weld_window), window_max)
        st.slider("Weld window (mm)", 0.0, window_max, step=0.5, key="weld_window")
        st.checkbox("Top holder ring", key="make_top_holder")
        if st.session_state.make_top_holder:
            st.slider("Top holder height (mm)", 8.0, 25.0, step=0.5, key="top_holder_height")
        st.checkbox("Wire channels along each parallel group", key="wire_channels")
        st.checkbox("Strain-relief slots in the end rims", key="strain_relief")


def _case_controls() -> None:
    with st.expander("Case and lid", expanded=False):
        st.checkbox("Generate case", key="make_case")
        if not st.session_state.make_case:
            st.session_state.make_lid = False
        st.checkbox("Generate lid", key="make_lid", disabled=not st.session_state.make_case)
        st.slider("Wall thickness (mm)", 1.6, 5.0, step=0.1, key="case_wall")
        st.slider("Floor thickness (mm)", 1.6, 5.0, step=0.1, key="floor_thickness")
        st.slider("Holder fit in the case (mm)", 0.2, 1.2, step=0.05, key="case_fit")
        st.slider("Clearance above the cells (mm)", 3.0, 12.0, step=0.5, key="top_clearance")
        st.slider("Outer corner radius (mm)", 0.0, 5.0, step=0.5, key="corner_radius")
        st.selectbox("Lid closure", list(LID_STYLES), key="lid_style", format_func=_lid_label)
        st.slider("Lid thickness (mm)", 2.2, 6.0, step=0.1, key="lid_thickness")
        if st.session_state.lid_style == "magnets":
            st.slider("Magnet pocket diameter (mm)", 4.0, 10.0, step=0.1, key="magnet_diameter")
            depth_max = max(1.0, float(st.session_state.lid_thickness) - 0.8)
            st.session_state.magnet_depth = min(float(st.session_state.magnet_depth), depth_max)
            st.slider("Magnet pocket depth (mm)", 0.8, depth_max, step=0.1, key="magnet_depth")
        st.checkbox("Mounting tabs", key="mounting_tabs")
        if st.session_state.mounting_tabs:
            st.radio("Screw clearance", ["M3", "M4"], key="screw", horizontal=True)


def _bms_controls() -> None:
    with st.expander("BMS compartment", expanded=False):
        st.checkbox("Add a BMS bay", key="bms_enabled")
        if not st.session_state.bms_enabled:
            return
        st.slider("Bay length, outward (mm)", 30.0, 120.0, step=1.0, key="bms_length")
        st.slider("Bay width (mm)", 16.0, 80.0, step=1.0, key="bms_width")
        st.slider("Board height to allow (mm)", 8.0, 30.0, step=1.0, key="bms_height")
        st.selectbox(
            "Position",
            list(BMS_SIDE_LABELS),
            key="bms_side",
            format_func=lambda key: BMS_SIDE_LABELS[key],
        )
        st.slider("Open height over the divider (mm)", 8.0, 20.0, step=1.0, key="wire_access")
        st.caption("The divider stops short of the lid so balance leads can cross. Main leads leave through a top notch.")


def _printer_controls() -> None:
    with st.expander("Printer", expanded=False):
        st.slider("Bed limit to warn at (mm)", 180.0, 350.0, step=5.0, key="max_print_mm")
        st.caption("A Kobra-class bed is about 220–250 mm. Parts over 250 mm get a stronger warning.")


def _params_from_state() -> PackParams:
    base = PackParams().to_dict()
    data = {key: st.session_state.get(key, value) for key, value in base.items()}
    return PackParams.from_dict(data)


def _summary(layout) -> None:
    cols = st.columns(4)
    cols[0].metric("Cells", f"{layout.cell_count}")
    cols[1].metric("Grid", f"{layout.rows} × {layout.cols}")
    longest = max(layout.part_plans, key=lambda plan: plan.max_dim)
    cols[2].metric("Longest part", f"{layout.max_part_mm:.0f} mm", longest.name)
    cols[3].metric("STL files", f"{len(layout.part_plans)}")
    hx0, hy0, hx1, hy1 = layout.holder_bounds
    holder = f"Holder footprint {hx1 - hx0:.0f} × {hy1 - hy0:.0f} mm"
    if layout.case_extent is not None:
        ex0, ey0, ex1, ey1 = layout.case_extent
        holder += f" · case {ex1 - ex0:.0f} × {ey1 - ey0:.0f} × {layout.case_total_z:.0f} mm"
    st.caption(holder + f" · pitch {layout.pitch_x:.1f} × {layout.pitch_y:.1f} mm")


def _apply_suggested_split(row_sections: int, col_sections: int) -> None:
    """Update the section widgets before the next run draws them."""
    st.session_state.row_sections = int(row_sections)
    st.session_state.col_sections = int(col_sections)
    st.session_state.exports = None


def _messages(layout) -> None:
    for note in layout.notes:
        st.info(note)
    for warning in layout.warnings:
        st.warning(warning)
    if not layout.fits_bed:
        rows, cols = recommend_sections(layout.params)
        st.warning(
            f"Suggested split so each part stays under {layout.params.max_print_mm:.0f} mm: "
            f"{rows} row section(s) × {cols} column section(s)."
        )
        st.button(
            "Apply suggested split",
            on_click=_apply_suggested_split,
            args=(rows, cols),
        )


def _exports(params: PackParams, layout) -> None:
    st.subheader("STL files")
    st.caption("The drawing updates immediately. Generating the meshes takes longer, especially on a full 13S pack.")
    if st.button("Generate STL files", type="primary"):
        with st.spinner("Building holders, case, and lid…"):
            result = build_parts(layout)
        st.session_state.exports = _export_payload(params, layout, result)
    payload = st.session_state.get("exports")
    if not payload:
        return
    if payload["key"] != _key(params):
        st.warning("These files match the previous settings. Generate again before printing.")
    for error in payload["errors"]:
        st.error(error)
    for warning in payload["warnings"]:
        st.warning(warning)
    files = payload["files"]
    if not files:
        return
    left, right = st.columns([1, 1])
    with left:
        for item in files:
            sx, sy, sz = item["size"]
            st.download_button(
                f"{item['name']}   {sx:.0f} × {sy:.0f} × {sz:.0f} mm",
                data=item["stl"],
                file_name=item["name"],
                mime="model/stl",
                key=f"dl-{payload['key'][:12]}-{item['name']}",
                width="stretch",
            )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for item in files:
                archive.writestr(item["name"], item["stl"])
            archive.writestr("pack_spec.json", payload["spec"])
        st.download_button(
            "Download all (zip)",
            data=buffer.getvalue(),
            file_name="pack.zip",
            mime="application/zip",
            width="stretch",
        )
    with right:
        names = [item["name"] for item in files]
        chosen = st.selectbox("3D preview", names)
        item = next(file for file in files if file["name"] == chosen)
        count = _triangle_count(item["stl"])
        stride = 2 if count > 40000 else 1
        mesh = stl_mesh(item["stl"], stride=stride)
        if mesh["x"]:
            import plotly.graph_objects as go

            figure = go.Figure(
                data=[
                    go.Mesh3d(
                        x=mesh["x"],
                        y=mesh["y"],
                        z=mesh["z"],
                        i=mesh["i"],
                        j=mesh["j"],
                        k=mesh["k"],
                        color="#1f4b99",
                        flatshading=True,
                        lighting={"ambient": 0.55, "diffuse": 0.8, "specular": 0.15},
                    )
                ]
            )
            figure.update_layout(
                scene_aspectmode="data",
                margin={"l": 0, "r": 0, "t": 0, "b": 0},
                height=520,
                paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(figure, width="stretch")
        else:
            st.info("This STL could not be previewed. The download is still available.")


def _export_payload(params: PackParams, layout, result) -> dict:
    files = []
    for part in result.parts:
        if not part.stl:
            continue
        files.append({"name": part.name, "role": part.role, "size": part.size, "stl": part.stl})
    spec = {
        "params": params.to_dict(),
        "cells": layout.cell_count,
        "warnings": result.warnings,
        "notes": result.notes,
        "errors": result.errors,
        "parts": [{"name": part.name, "size_mm": part.size, "error": part.error} for part in result.parts],
    }
    return {
        "key": _key(params),
        "files": files,
        "warnings": result.warnings,
        "errors": result.errors,
        "spec": json.dumps(spec, indent=2),
    }


def _key(params: PackParams) -> str:
    return json.dumps(params.to_dict(), sort_keys=True)


def _triangle_count(data: bytes) -> int:
    if len(data) < 84 or data[:5].lower() == b"solid":
        return 0
    import struct

    return struct.unpack_from("<I", data, 80)[0]


def _lid_label(style: str) -> str:
    return {"friction": "Friction fit", "magnets": "Friction + magnet pockets", "clips": "Friction + clip tabs"}[style]


if __name__ == "__main__":
    main()
