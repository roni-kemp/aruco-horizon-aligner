#!/usr/bin/env python3
"""Generate printable A4 pages with four ArUco markers in a vertical strip."""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


DICTIONARY_NAME = "DICT_4X4_250"
ROWS = "ABCDEF"
COLUMNS = range(1, 6)


def millimetres_to_pixels(value: float, dpi: int) -> int:
    return round(value / 25.4 * dpi)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("wall_marker_a4"))
    parser.add_argument("--mapping", type=Path, default=Path("wall_marker_mapping.json"))
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--marker-size-mm", type=float, default=20.0)
    parser.add_argument("--marker-gap-mm", type=float, default=2.0)
    parser.add_argument("--box-width-mm", type=float, default=45.0)
    parser.add_argument("--box-height-mm", type=float, default=92.0)
    parser.add_argument("--box-gap-x-mm", type=float, default=5.0)
    parser.add_argument("--box-gap-y-mm", type=float, default=5.0)
    parser.add_argument("--page-margin-mm", type=float, default=5.0)
    parser.add_argument("--strip-margin-y-mm", type=float, default=3.0)
    parser.add_argument("--label-gap-mm", type=float, default=8.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    marker_size = millimetres_to_pixels(args.marker_size_mm, args.dpi)
    marker_gap = millimetres_to_pixels(args.marker_gap_mm, args.dpi)
    box_width = millimetres_to_pixels(args.box_width_mm, args.dpi)
    box_height = millimetres_to_pixels(args.box_height_mm, args.dpi)
    box_gap_x = millimetres_to_pixels(args.box_gap_x_mm, args.dpi)
    box_gap_y = millimetres_to_pixels(args.box_gap_y_mm, args.dpi)
    page_margin = millimetres_to_pixels(args.page_margin_mm, args.dpi)
    strip_margin_y = millimetres_to_pixels(args.strip_margin_y_mm, args.dpi)
    label_gap = millimetres_to_pixels(args.label_gap_mm, args.dpi)
    page_width = millimetres_to_pixels(297.0, args.dpi)
    page_height = millimetres_to_pixels(210.0, args.dpi)

    strip_width = marker_size
    strip_height = 4 * marker_size + 3 * marker_gap
    if strip_width + millimetres_to_pixels(5, args.dpi) > box_width or strip_height + 2 * strip_margin_y > box_height:
        raise ValueError("Markers and label do not fit inside the configured box")
    ten_boxes_width = 5 * box_width + 4 * box_gap_x
    ten_boxes_height = 2 * box_height + box_gap_y
    if ten_boxes_width + 2 * page_margin > page_width or ten_boxes_height + 2 * page_margin > page_height:
        raise ValueError("Ten boxes do not fit on a landscape A4 page")

    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_250)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    marker_locations = {}
    box_markers = {}
    page_locations = {}
    marker_id = 0
    box_ids = [f"{row}{column}" for row in ROWS for column in COLUMNS]

    for page_index in range(0, len(box_ids), 10):
        page_box_ids = box_ids[page_index : page_index + 10]
        page = np.full((page_height, page_width, 3), 255, dtype=np.uint8)
        first_box_x = (page_width - ten_boxes_width) // 2
        first_box_y = (page_height - ten_boxes_height) // 2
        page_name = f"page_{page_index // 10 + 1:02d}_{'_'.join(page_box_ids)}.png"

        for box_index, box_id in enumerate(page_box_ids):
            box_column = box_index % 5
            box_row = box_index // 5
            box_x = first_box_x + box_column * (box_width + box_gap_x)
            box_y = first_box_y + box_row * (box_height + box_gap_y)
            border_thickness = max(3, round(args.dpi / 100))
            cv2.rectangle(
                page,
                (box_x, box_y),
                (box_x + box_width, box_y + box_height),
                (0, 0, 0),
                border_thickness,
            )
            label_scale = args.dpi / 180
            label_text = box_id
            (label_width, label_height), label_baseline = cv2.getTextSize(
                label_text,
                cv2.FONT_HERSHEY_SIMPLEX,
                label_scale,
                max(3, round(args.dpi / 100)),
            )
            label_x = box_x + millimetres_to_pixels(5, args.dpi) + marker_size + label_gap
            label_y = box_y + (box_height + label_height) // 2
            if label_x + label_width > box_x + box_width - millimetres_to_pixels(2, args.dpi):
                raise ValueError("Box label does not fit beside the marker strip")
            cv2.putText(
                page,
                label_text,
                (label_x, label_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                label_scale,
                (0, 0, 0),
                max(3, round(args.dpi / 100)),
                cv2.LINE_AA,
            )

            strip_x = box_x + millimetres_to_pixels(5, args.dpi)
            strip_y = box_y + strip_margin_y
            box_markers[box_id] = []
            for position in range(4):
                marker_image = cv2.aruco.generateImageMarker(
                    dictionary,
                    marker_id,
                    marker_size,
                    borderBits=1,
                )
                marker_x = strip_x
                marker_y = strip_y + position * (marker_size + marker_gap)
                page[marker_y : marker_y + marker_size, marker_x : marker_x + marker_size] = cv2.cvtColor(
                    marker_image,
                    cv2.COLOR_GRAY2BGR,
                )
                marker_locations[str(marker_id)] = {
                    "box_id": box_id,
                    "position": position,
                    "page": page_name,
                    "center_mm": [
                        round((marker_x + marker_size / 2) / args.dpi * 25.4, 2),
                        round((marker_y + marker_size / 2) / args.dpi * 25.4, 2),
                    ],
                }
                box_markers[box_id].append(marker_id)
                marker_id += 1
            page_locations[box_id] = page_name

        page_path = args.output_dir / page_name
        Image.fromarray(cv2.cvtColor(page, cv2.COLOR_BGR2RGB)).save(
            page_path,
            dpi=(args.dpi, args.dpi),
        )

    args.mapping.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "dictionary": DICTIONARY_NAME,
        "marker_count": marker_id,
        "markers_per_box": 4,
        "marker_size_mm": args.marker_size_mm,
        "strip_margin_y_mm": args.strip_margin_y_mm,
        "label_gap_mm": args.label_gap_mm,
        "layout": "vertical_strip",
        "dpi": args.dpi,
        "page_size": "A4",
        "orientation": "landscape",
        "page_size_mm": [297.0, 210.0],
        "page_margin_mm": args.page_margin_mm,
        "box_gap_x_mm": args.box_gap_x_mm,
        "box_gap_y_mm": args.box_gap_y_mm,
        "box_size_mm": [args.box_width_mm, args.box_height_mm],
        "pages": page_locations,
        "boxes": box_markers,
        "markers": marker_locations,
    }
    args.mapping.write_text(json.dumps(metadata, indent=2) + "\n", encoding="ascii")
    print(f"Saved {(len(box_ids) + 9) // 10} A4 pages in {args.output_dir}")
    print(f"Saved {args.mapping} with {marker_id} marker assignments")
    print("Print at 100% scale; do not fit to page.")


if __name__ == "__main__":
    main()
