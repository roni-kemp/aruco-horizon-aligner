# Wall Marker Generator

`generate_wall_marker.py` creates printable ArUco marker sheets for boxes `A1` through `F5`.

Each box contains four ArUco markers arranged as a vertical strip. The marker IDs identify the box as a group for the roll-alignment tool.

## Generate the Default Set

```bash
source .venv/bin/activate
python generate_wall_marker.py
```

The default command creates:

- 3 landscape A4 PNG pages in `wall_marker_a4/`
- 10 box layouts per page in a 5 x 2 arrangement
- 30 boxes total: `A1` through `F5`
- 4 markers per box
- 120 markers total
- `DICT_4X4_250`
- 20 mm marker sides
- 2 mm spacing between markers in each strip
- 3 mm margin above and below each strip
- 8 mm gap between the marker strip and the box label
- 45 x 92 mm box outlines
- 300 DPI PNGs
- `wall_marker_mapping.json`

The first page contains `A1` through `B5`, the second page contains `C1` through `D5`, and the final page contains `E1` through `F5`.

## Printing

Print the PNG files with:

- Paper: A4
- Orientation: Landscape
- Scale: Actual size / 100%
- Fit to page: Disabled
- Shrink or enlarge: Disabled

After printing, measure the black square of one marker. It should measure 20 mm from edge to edge. Do not measure the surrounding box or page layout.

## Parameters

All dimensions are in millimetres unless stated otherwise.

### Output

```text
--output-dir PATH
```

Directory for generated PNG pages. Default: `wall_marker_a4`.

```text
--mapping PATH
```

JSON file containing marker-to-box assignments and layout metadata. Default: `wall_marker_mapping.json`.

```text
--dpi INTEGER
```

Resolution used to convert physical dimensions to pixels and embedded in PNG metadata. Default: `300`.

### Marker Geometry

```text
--marker-size-mm FLOAT
```

Side length of each black ArUco marker. Default: `20`.

```text
--marker-gap-mm FLOAT
```

Vertical gap between adjacent markers in one strip. Default: `2`.

```text
--strip-margin-y-mm FLOAT
```

Vertical clearance between the top/bottom markers and the box outline. Default: `3`.

```text
--label-gap-mm FLOAT
```

Horizontal clearance between the marker strip and the box label. Default: `8`.

### Box Layout

```text
--box-width-mm FLOAT
```

Width of each printed box region. Default: `45`.

```text
--box-height-mm FLOAT
```

Height of each printed box region. Default: `92`.

The strip height is calculated as:

```text
4 * marker-size-mm + 3 * marker-gap-mm + 2 * strip-margin-y-mm
```

With the defaults:

```text
4 * 20 + 3 * 2 + 2 * 3 = 92 mm
```

```text
--box-gap-x-mm FLOAT
```

Horizontal gap between box columns. Default: `5`.

```text
--box-gap-y-mm FLOAT
```

Vertical gap between box rows. Default: `5`.

```text
--page-margin-mm FLOAT
```

Minimum margin around the complete layout. Default: `5`.

## Page Fit Constraints

The generator uses landscape A4:

```text
297 mm wide x 210 mm high
```

Five boxes across and two boxes down must satisfy:

```text
5 * box-width-mm + 4 * box-gap-x-mm + 2 * page-margin-mm <= 297
2 * box-height-mm + box-gap-y-mm + 2 * page-margin-mm <= 210
```

With the defaults:

```text
5 * 45 + 4 * 5 + 2 * 5 = 255 mm wide
2 * 92 + 5 + 2 * 5 = 199 mm high
```

The generated images are 3508 x 2480 pixels with approximately 300 DPI metadata.

## Example: Smaller Markers

```bash
python generate_wall_marker.py \
  --marker-size-mm 15 \
  --marker-gap-mm 2 \
  --strip-margin-y-mm 3 \
  --box-height-mm 72
```

The printed marker size must match the size used by any downstream pose code. The roll-only tool uses 2D corners and does not require marker size for its angle calculation.

## Example: More Marker Separation

```bash
python generate_wall_marker.py \
  --marker-size-mm 20 \
  --marker-gap-mm 4 \
  --strip-margin-y-mm 3 \
  --box-height-mm 104
```

The new strip height is:

```text
4 * 20 + 3 * 4 + 2 * 3 = 98 mm
```

The example leaves additional room inside the 104 mm box outline.

## Mapping File

The generator preserves consecutive marker IDs for each box:

```json
"boxes": {
  "A1": [0, 1, 2, 3],
  "A2": [4, 5, 6, 7]
}
```

The reverse lookup is also included:

```json
"markers": {
  "0": {
    "box_id": "A1",
    "position": 0
  }
}
```

Positions are numbered from top to bottom: `0` is the top marker and `3` is the bottom marker.

Do not manually renumber IDs after printing. The roll-alignment tool uses this mapping to group detections by box.

## Dictionary

The generator uses `DICT_4X4_250`. The active roll-alignment detector must use the same dictionary.
