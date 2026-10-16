# Cylindrical cell pack builder

Parametric holders, cases, and lids for cylindrical lithium cells. It is aimed at custom e-bike and scooter packs: 18650 and 21700 presets, rectangular or staggered grids, a usable BMS bay, and separate STLs for the holder, case, and lid.

This is a mechanical generator. It does not size voltage, current, wire, or nickel. You still have to match cells, fuse the pack, pick a BMS with the right rating, insulate the build, and charge it where you can watch it.

The geometry follows the useful ideas from parametric OpenSCAD battery holders — grid and hex packing, row and column counts, a sleeve plus an optional floor, and a matching case — and rebuilds them in CadQuery. OpenSCAD is not required.

## Setup

Python 3.11 or 3.12 is the comfortable range. CadQuery ships binary wheels for those versions.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run the app

```bash
streamlit run app.py
```

The drawing updates as you move the sliders. **Generate STL files** builds the meshes and enables one download per part, plus a zip. Files are already oriented for the printer:

- Holders: holes facing up
- Case: opening up
- Lid: outer face on the bed, skirt and clips pointing up

## Command line

```bash
python -m packgen.cli --example 4s2p --out dist/4s2p --preview dist/4s2p/layout.png
python -m packgen.cli --example 13s4p --out dist/13s4p --preview dist/13s4p/layout.png
python -m packgen.cli --series 10 --parallel 3 --packing rectangular --out dist/10s3p
python -m pytest
```

`--recommend` prints a row/column split that keeps every part under the bed limit.

## Example: 13S4P staggered 18650 with a side BMS bay

Load **13S4P staggered + side BMS** in the app, or export it with the command above. The same settings are in `examples/13s4p_18650_staggered.json`.

| | |
| --- | --- |
| Cells | 13 series × 4 parallel, staggered, 18.5 × 65.2 mm |
| Pitch | 20.5 mm across a row, 17.8 mm between rows |
| BMS | 70 × 32 × 18 mm pod on the +X side, with a lead notch and a wire window over the divider |
| Lid | Friction skirt plus 6.4 mm magnet pockets, M4 mounting tabs |
| Sections | 2 along the rows |

A single-piece case for that pack is about **190 × 273 × 75 mm**, which is past both a 240 mm warning line and a typical 250 mm desktop bed. Two row sections insert about 5 mm of extra gap so the cut clears the cells, and the longest printed part comes out around **184–190 mm**. The BMS pod is parked on the last row section so the joint does not slice the board pocket. Each holder section has rim tabs; the case and lid sections share a lap joint. A small notch on every holder marks the −X/−Y corner.

## What you can change

- **Cell.** 18650, 21700, or a custom diameter and length. One size is used for the whole pack. Measure the cells you actually have; protected 18650s are often 67–70 mm long.
- **Layout.** Series/parallel (each row is a parallel group by default) or a plain row × column grid. Rectangular packing, or staggered hex packing.
- **Holder.** Rim width, sleeve height, optional floor, and a weld window through that floor. A second open ring is generated for the top of the cells. Wire channels follow each parallel group, and strain-relief slots break the end rims.
- **Case and lid.** Wall, floor, fit clearance, and space above the cells for nickel and the lid skirt. Lid closure is friction, friction plus magnet pockets, or friction plus clip tabs.
- **BMS bay.** Length is how far the pod sticks out, width is across the pod, height is the board thickness you need to clear. Place it on either end or either side. The divider stops short of the lid so balance leads can cross, and the main leads leave through a notch.
- **Sections.** Row and column sections print as separate pieces that nest. The app suggests a split when any part exceeds the bed limit (default 240 mm) and uses stronger wording past 250 mm.

## Print notes

A longer version is shown in the app and follows the settings you picked. The short version:

- 0.2 mm layers, about a 0.45 mm line width. Use enough perimeters that a 2.4 mm wall is mostly solid (4 or more). Holders like 30–40% gyroid; the case can be lighter once the walls are solid.
- PETG is the practical default. ABS or ASA if the pack lives near a hot controller and your printer can hold the corners down. Do not use PLA for an enclosed pack.
- Print one cell hole before the full set. Add about 0.1 mm of hole clearance if it is tight.
- The weld window is for spot-welding through a bottom holder. Set the base to 0 if you want both ends completely open.
- Dry-fit the rim tabs. Glue the case lap if you want one shell; a strap through the mounting tabs is enough for many bike installs.
- Clip tabs want PETG and a test fit. Magnet pockets match the diameter you set (6×3 mm magnets for a 6.4 mm pocket).
- No vents are modeled. Do not build an airtight box around cells that can vent.

## How the code is split

CadQuery is only used to extrude a layout that is already fully dimensioned.

| Module | Role |
| --- | --- |
| `packgen/models.py` | Parameters, presets, validation |
| `packgen/layout.py` | Cell centres, joints, BMS pod, part sizes. No CadQuery |
| `packgen/holder.py` | Holder sleeves, weld windows, rim tabs, channels, slots |
| `packgen/enclosure.py` | Case, lid, lap-joint split |
| `packgen/build.py` | Runs the solids and writes STL bytes |
| `app.py` | Streamlit UI |

To add a feature, decide its dimensions in `layout.py` and only then cut or union it in `holder.py` or `enclosure.py`. Fit numbers that both parts must share (tongue length, skirt height, lap) live in `packgen/constants.py`.

## Limits

- One cell diameter per pack. Mixed rows are not modeled yet.
- Splits are straight cuts between cell groups. A staggered pack needs a wider lane for a vertical (column) split than for a row split; the app inserts that gap and says how large it is.
- Clip geometry is a simple latch. Plan on a test print.
- The tool does not design the electrical pack.

## Tests

```bash
pytest
```

Layout tests do the grid math. Solid tests build a small pack, check that the case is a shell, and check the lap joint used when a case is split.
