#!/usr/bin/env python3
"""Browser-based ArUco wall-marker roll alignment tool."""

import argparse
from collections import deque
from itertools import combinations
import json
import threading
import time
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template_string

from camera_source import PicameraSource


MIN_MARKERS = 2
OUTLIER_THRESHOLD_DEGREES = 5.0
ANGLE_HISTORY_FRAMES = 10
MIN_DISPLAY_CHANGE_DEGREES = 0.2
DEFAULT_LOCK_THRESHOLD_DEGREES = 0.3
LOCKED_LINE_COLOR = (0, 220, 0)
NEGATIVE_ROLL_LINE_COLOR = (0, 150, 255)
POSITIVE_ROLL_LINE_COLOR = (0, 90, 190)
INVALID_LINE_COLOR = (0, 0, 130)
INLIER_COLOR = (0, 220, 0)
OUTLIER_COLOR = (0, 80, 255)
UNKNOWN_COLOR = (140, 140, 140)

PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Wall marker roll alignment</title>
  <style>
    body { background: #182026; color: #f4f7f8; font: 16px sans-serif; margin: 0; }
    main { max-width: 1100px; margin: auto; padding: 20px; }
    h1 { font-size: 28px; margin: 0 0 12px; }
    img { background: #000; display: block; max-width: 100%; height: auto; }
    .controls { align-items: center; display: flex; flex-wrap: wrap; gap: 12px; margin: 16px 0; }
    label, #status { color: #c4ced3; }
  </style>
</head>
<body>
<main>
  <h1>Wall marker roll alignment</h1>
    <img src="/video_feed" alt="Live camera feed">
  <div class="controls">
        <label>Stream width: <input id="streamWidth" type="range" min="320" max="1280" step="80" value="800" onchange="setStreamWidth(this.value)"></label>
    <span id="streamWidthValue">800 px</span>
        <label>Lock threshold: <input id="lockThreshold" type="range" min="0.1" max="2.0" step="0.1" value="0.3" onchange="setLockThreshold(this.value)"></label>
        <span id="lockThresholdValue">0.3 deg</span>
    <span id="status">Starting camera...</span>
  </div>
</main>
<script>
  async function setStreamWidth(width) {
    document.getElementById('streamWidthValue').textContent = width + ' px';
    const response = await fetch('/settings', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({stream_width: Number(width)})
    });
    const result = await response.json();
        document.getElementById('status').textContent = result.message;
    }
    async function setLockThreshold(threshold) {
        document.getElementById('lockThresholdValue').textContent = Number(threshold).toFixed(1) + ' deg';
        const response = await fetch('/settings', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({lock_threshold: Number(threshold)})
        });
        const result = await response.json();
        document.getElementById('status').textContent = result.message;
    }
  setInterval(async () => {
    const result = await fetch('/status').then(response => response.json());
    document.getElementById('status').textContent = result.message;
  }, 1000);
</script>
</body>
</html>
"""


def circular_mean(angles: list[float]) -> float:
    radians = np.radians(angles)
    return float(np.degrees(np.arctan2(np.mean(np.sin(radians)), np.mean(np.cos(radians)))))


def circular_difference(first: float, second: float) -> float:
    return float((first - second + 180.0) % 360.0 - 180.0)


def select_inliers(angles: list[float]) -> list[int]:
    """Find the largest group whose members agree within the angle threshold."""
    for group_size in range(len(angles), MIN_MARKERS - 1, -1):
        candidates = []
        for indexes in combinations(range(len(angles)), group_size):
            mean_angle = circular_mean([angles[index] for index in indexes])
            deviations = [
                abs(circular_difference(angles[index], mean_angle))
                for index in indexes
            ]
            if max(deviations) <= OUTLIER_THRESHOLD_DEGREES:
                candidates.append((sum(deviations), list(indexes)))
        if candidates:
            candidates.sort(key=lambda candidate: candidate[0])
            return candidates[0][1]
    return []


def marker_roll(corners: np.ndarray) -> float:
    points = np.asarray(corners).reshape(4, 2)
    top_angle = np.degrees(np.arctan2(points[1, 1] - points[0, 1], points[1, 0] - points[0, 0]))
    bottom_angle = np.degrees(np.arctan2(points[2, 1] - points[3, 1], points[2, 0] - points[3, 0]))
    return circular_mean([float(top_angle), float(bottom_angle)])


def group_rolls(marker_ids: np.ndarray, corners: list[np.ndarray], marker_to_box: dict[int, str]):
    groups: dict[str, list[tuple[int, float, int]]] = {}
    for index, (marker_id, marker_corners) in enumerate(zip(marker_ids.flatten(), corners)):
        box_id = marker_to_box.get(int(marker_id))
        if box_id is not None:
            groups.setdefault(box_id, []).append((int(marker_id), marker_roll(marker_corners), index))

    results = {}
    for box_id, observations in groups.items():
        if len(observations) < MIN_MARKERS:
            results[box_id] = {"valid": False, "observations": observations, "inliers": [], "outliers": []}
            continue
        inlier_indexes = select_inliers([observation[1] for observation in observations])
        outlier_indexes = [index for index in range(len(observations)) if index not in inlier_indexes]
        valid = len(inlier_indexes) >= MIN_MARKERS
        angle = circular_mean([observations[index][1] for index in inlier_indexes]) if valid else None
        results[box_id] = {
            "valid": valid,
            "angle": angle,
            "observations": observations,
            "inliers": inlier_indexes,
            "outliers": outlier_indexes,
        }
    return results


def draw_line(frame: np.ndarray, angle: float, color: tuple[int, int, int], thickness: int = 5) -> None:
    height, width = frame.shape[:2]
    center = np.array([width // 2, height // 2], dtype=float)
    half_length = width * 0.48
    vector = np.array([np.cos(np.radians(angle)), np.sin(np.radians(angle))]) * half_length
    start = tuple(np.round(center - vector).astype(int))
    end = tuple(np.round(center + vector).astype(int))
    cv2.line(frame, start, end, color, thickness, cv2.LINE_AA)


def roll_line_color(angle: float, lock_threshold: float) -> tuple[int, int, int]:
    if abs(angle) < lock_threshold:
        return LOCKED_LINE_COLOR
    if angle < 0:
        return NEGATIVE_ROLL_LINE_COLOR
    return POSITIVE_ROLL_LINE_COLOR


class AlignmentSession:
    def __init__(self, args: argparse.Namespace) -> None:
        mapping = json.loads(args.mapping.read_text(encoding="ascii"))
        self.marker_to_box = {
            int(marker_id): box_id
            for box_id, marker_ids in mapping["boxes"].items()
            for marker_id in marker_ids
        }
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_250)
        self.detector = cv2.aruco.ArucoDetector(dictionary)
        self.camera = PicameraSource(
            lens_position=args.lens_position,
            capture_size=(args.camera_width, args.camera_height),
        )
        self.detect_width = args.detect_width
        self.stream_width = args.stream_width
        self.lock_threshold = args.lock_threshold
        self.last_valid_angles: dict[str, float] = {}
        self.angle_history: dict[str, deque[float]] = {}
        self.latest_jpeg = None
        self.message = "Camera started. Point it at one wall-marker strip."
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self.capture_loop, daemon=True)
        self.thread.start()

    def capture_loop(self) -> None:
        while self.running:
            frame_rgb = self.camera.read()
            full_height, full_width = frame_rgb.shape[:2]
            detect_scale = 1.0
            detect_frame = frame_rgb
            if full_width > self.detect_width:
                detect_scale = self.detect_width / full_width
                detect_frame = cv2.resize(
                    frame_rgb,
                    (self.detect_width, round(full_height * detect_scale)),
                    interpolation=cv2.INTER_AREA,
                )
            corners, ids, _ = self.detector.detectMarkers(detect_frame)
            if detect_scale != 1.0 and corners:
                corners = [corner / detect_scale for corner in corners]
            display = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            results = group_rolls(ids, corners, self.marker_to_box) if ids is not None else {}
            with self.lock:
                lock_threshold = self.lock_threshold

            for marker_index, marker_id in enumerate(ids.flatten() if ids is not None else []):
                box_id = self.marker_to_box.get(int(marker_id))
                color = UNKNOWN_COLOR
                if box_id in results:
                    observation_indexes = [item[2] for item in results[box_id]["observations"]]
                    local_index = observation_indexes.index(marker_index)
                    color = INLIER_COLOR if local_index in results[box_id]["inliers"] else OUTLIER_COLOR
                points = np.asarray(corners[marker_index]).reshape(4, 2).astype(int)
                cv2.polylines(display, [points], True, color, 4, cv2.LINE_AA)
                cv2.putText(display, f"ID {marker_id}", tuple(points[0] + [0, -10]), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2, cv2.LINE_AA)

            draw_line(display, 0.0, (255, 255, 255), 4)
            status_parts = []
            for box_id, result in results.items():
                if result["valid"]:
                    history = self.angle_history.setdefault(box_id, deque(maxlen=ANGLE_HISTORY_FRAMES))
                    history.append(result["angle"])
                    averaged_angle = circular_mean(list(history))
                    displayed_angle = self.last_valid_angles.get(box_id)
                    if displayed_angle is None:
                        displayed_angle = 0.0 if abs(averaged_angle) < MIN_DISPLAY_CHANGE_DEGREES else averaged_angle
                    elif abs(circular_difference(averaged_angle, displayed_angle)) >= MIN_DISPLAY_CHANGE_DEGREES:
                        displayed_angle = averaged_angle
                    self.last_valid_angles[box_id] = displayed_angle
                    draw_line(display, displayed_angle, roll_line_color(displayed_angle, lock_threshold), 6)
                    status_parts.append(f"{box_id}: roll {displayed_angle:+.1f} deg")
                elif box_id in self.last_valid_angles:
                    angle = self.last_valid_angles[box_id]
                    draw_line(display, angle, INVALID_LINE_COLOR, 6)
                    status_parts.append(f"{box_id}: stale, not all markers found")
                else:
                    status_parts.append(f"{box_id}: not all markers found")

            if not status_parts:
                status_parts.append("No mapped wall markers detected")
            with self.lock:
                self.message = " | ".join(status_parts)
                stream_width = self.stream_width
            cv2.putText(display, self.message, (20, 45), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2, cv2.LINE_AA)
            stream_height = round(display.shape[0] * stream_width / display.shape[1])
            stream_frame = cv2.resize(display, (stream_width, stream_height), interpolation=cv2.INTER_AREA)
            success, encoded = cv2.imencode(".jpg", stream_frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
            if success:
                with self.lock:
                    self.latest_jpeg = encoded.tobytes()

    def stream(self):
        while self.running:
            with self.lock:
                jpeg = self.latest_jpeg
            if jpeg is not None:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(0.03)

    def set_stream_width(self, width: int) -> str:
        with self.lock:
            self.stream_width = max(320, min(1280, int(width)))
            return f"Stream width set to {self.stream_width} px."

    def set_lock_threshold(self, threshold: float) -> str:
        with self.lock:
            self.lock_threshold = max(0.1, min(2.0, float(threshold)))
            return f"Lock threshold set to {self.lock_threshold:.1f} degrees."

    def close(self) -> None:
        self.running = False
        self.thread.join(timeout=2)
        self.camera.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5001)
    parser.add_argument("--mapping", type=Path, default=Path("wall_marker_mapping.json"))
    parser.add_argument("--lens-position", type=float, default=2.0)
    parser.add_argument("--camera-width", type=int, default=1280)
    parser.add_argument("--camera-height", type=int, default=720)
    parser.add_argument("--detect-width", type=int, default=960)
    parser.add_argument("--stream-width", type=int, default=800)
    parser.add_argument("--lock-threshold", type=float, default=DEFAULT_LOCK_THRESHOLD_DEGREES)
    args = parser.parse_args()

    session = AlignmentSession(args)
    app = Flask(__name__)
    app.add_url_rule("/", "index", lambda: render_template_string(PAGE))
    app.add_url_rule("/video_feed", "video_feed", lambda: Response(session.stream(), mimetype="multipart/x-mixed-replace; boundary=frame"))
    app.add_url_rule("/status", "status", lambda: jsonify(message=session.message))

    def settings_route():
        from flask import request
        settings = request.get_json(silent=True) or {}
        messages = []
        try:
            if "stream_width" in settings:
                messages.append(session.set_stream_width(settings["stream_width"]))
            if "lock_threshold" in settings:
                messages.append(session.set_lock_threshold(settings["lock_threshold"]))
            if not messages:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify(ok=False, message="Invalid setting."), 400
        return jsonify(ok=True, message=" ".join(messages))

    app.add_url_rule("/settings", "settings", settings_route, methods=["POST"])
    try:
        app.run(host=args.host, port=args.port, threaded=True, debug=False, use_reloader=False)
    finally:
        session.close()


if __name__ == "__main__":
    main()
