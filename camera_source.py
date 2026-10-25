"""Picamera2 source matching the experiment camera setup."""

import cv2
from libcamera import controls
from picamera2 import Picamera2


class PicameraSource:
    def __init__(
        self,
        lens_position: float = 2.0,
        warmup_frames: int = 10,
        capture_size: tuple[int, int] | None = None,
    ) -> None:
        self.camera = Picamera2()
        use_preview = capture_size is not None and capture_size[0] <= 1920 and capture_size[1] <= 1080
        self.returns_rgb = use_preview
        if not use_preview:
            self.camera.configure(camera_config="still")
        else:
            full_res = self.camera.sensor_resolution  # e.g. (4608, 2592) for imx708

            self.camera.configure(
                self.camera.create_preview_configuration(
                    main={"size": capture_size, "format": "RGB888"},
                    raw={"size": full_res},
                )
            )
        self.camera.set_controls(
            {
                "AfMode": controls.AfModeEnum.Manual,
                "LensPosition": lens_position,
            }
        )
        self.camera.start()
        for _ in range(warmup_frames):
            self.camera.capture_array("main")

    def read(self):
        frame = self.camera.capture_array("main")
        if self.returns_rgb:
            return frame
        return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    def close(self) -> None:
        self.camera.stop()

