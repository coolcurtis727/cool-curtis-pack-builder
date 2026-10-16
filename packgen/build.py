"""Turn a layout into printable solids and STL bytes."""

from __future__ import annotations

from dataclasses import dataclass, field

from packgen.constants import TYPICAL_BED_HARD_MM
from packgen.cqutil import bounding_size, export_stl_bytes, volume
from packgen.enclosure import make_case, make_lid, split_for_sections
from packgen.holder import make_holder
from packgen.layout import PackLayout, SectionSpec


@dataclass
class BuiltPart:
    name: str
    role: str
    size: tuple[float, float, float]
    stl: bytes | None = None
    error: str | None = None
    solid: object | None = field(default=None, repr=False)


@dataclass
class BuildResult:
    parts: list[BuiltPart]
    warnings: list[str]
    notes: list[str]
    errors: list[str]


def build_parts(layout: PackLayout, export: bool = True, tolerance: float = 0.12) -> BuildResult:
    """Create every holder, case section, and lid section for a layout."""
    built: list[BuiltPart] = []
    errors: list[str] = []
    for section in layout.sections:
        built.append(_holder_part(layout, section, top=False, export=export, tolerance=tolerance, errors=errors))
        if layout.params.make_top_holder:
            built.append(_holder_part(layout, section, top=True, export=export, tolerance=tolerance, errors=errors))
    if layout.params.make_case and layout.wall_outer is not None:
        built.extend(_enclosure_parts(layout, kind="case", export=export, tolerance=tolerance, errors=errors))
    if layout.params.make_lid and layout.wall_outer is not None and layout.params.make_case:
        built.extend(_enclosure_parts(layout, kind="lid", export=export, tolerance=tolerance, errors=errors))
    elif layout.params.make_lid and not layout.params.make_case:
        errors.append("A lid is only generated together with a case.")

    warnings = [note for note in layout.warnings if not _is_size_warning(note)]
    warnings.extend(_measured_warnings(built, layout.params.max_print_mm))
    return BuildResult(parts=built, warnings=warnings, notes=list(layout.notes), errors=errors)


def _holder_part(
    layout: PackLayout,
    section: SectionSpec,
    top: bool,
    export: bool,
    tolerance: float,
    errors: list[str],
) -> BuiltPart:
    role = "holder_top" if top else "holder_bottom"
    name = f"{role}{section.suffix}.stl"
    height = layout.params.top_holder_height if top else layout.params.holder_height
    base = 0.0 if top else layout.params.base_thickness
    window = 0.0 if top else layout.params.weld_window
    try:
        solid = make_holder(
            section,
            height=height,
            base_thickness=base,
            weld_window=window,
            hole_radius=layout.hole_radius,
            corner_radius=layout.params.corner_radius,
        )
        return _pack(name, role, solid, export, tolerance)
    except Exception as exc:
        errors.append(f"{name} failed: {exc}")
        return BuiltPart(name=name, role=role, size=(0.0, 0.0, 0.0), error=str(exc))


def _enclosure_parts(
    layout: PackLayout,
    kind: str,
    export: bool,
    tolerance: float,
    errors: list[str],
) -> list[BuiltPart]:
    try:
        solid = make_case(layout) if kind == "case" else make_lid(layout)
        pieces = split_for_sections(solid, layout.sections)
    except Exception as exc:
        errors.append(f"{kind} failed: {exc}")
        return [BuiltPart(name=f"{kind}.stl", role=kind, size=(0.0, 0.0, 0.0), error=str(exc))]
    parts: list[BuiltPart] = []
    if len(pieces) != len(layout.sections):
        errors.append(f"{kind} split into {len(pieces)} pieces, expected {len(layout.sections)}.")
        return parts
    for section, piece in zip(layout.sections, pieces):
        name = f"{kind}{section.suffix}.stl"
        try:
            if volume(piece) < 1.0:
                raise RuntimeError("split piece has no volume")
            parts.append(_pack(name, kind, piece, export, tolerance))
        except Exception as exc:
            errors.append(f"{name} failed: {exc}")
            parts.append(BuiltPart(name=name, role=kind, size=(0.0, 0.0, 0.0), error=str(exc)))
    return parts


def _pack(name: str, role: str, solid, export: bool, tolerance: float) -> BuiltPart:
    size = bounding_size(solid)
    stl = export_stl_bytes(solid, tolerance=tolerance) if export else None
    return BuiltPart(name=name, role=role, size=size, stl=stl, solid=None if export else solid)


def _is_size_warning(text: str) -> bool:
    return "printer limit" in text or "desktop bed" in text


def _measured_warnings(parts: list[BuiltPart], limit: float) -> list[str]:
    warnings: list[str] = []
    for part in parts:
        if part.error or part.size == (0.0, 0.0, 0.0):
            continue
        sx, sy, sz = part.size
        over = [f"{axis} {value:.0f} mm" for axis, value in (("X", sx), ("Y", sy), ("Z", sz)) if value > limit]
        if not over:
            continue
        hard = max(sx, sy, sz) > TYPICAL_BED_HARD_MM
        limit_text = (
            f"over a typical {TYPICAL_BED_HARD_MM:.0f} mm desktop bed"
            if hard
            else f"over the {limit:.0f} mm printer limit"
        )
        warnings.append(
            f"Measured {part.name} is {sx:.0f} × {sy:.0f} × {sz:.0f} mm, {limit_text} "
            f"({', '.join(over)}). Split the pack into more row or column sections."
        )
    return warnings
