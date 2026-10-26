"""
QR Code Management module for QR Secure Notes.
Handles high-resolution QR generation, image export, multi-pass decoding,
and optional live webcam scanning with OpenCV.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple, Generator
import numpy as np
from PIL import Image
import qrcode
from qrcode.constants import ERROR_CORRECT_M
import cv2

from config import (
    QR_BOX_SIZE,
    QR_BORDER,
    EXPORTS_DIR,
    logger,
)


class QRError(Exception):
    """Base exception for QR operations."""
    pass


class QRCodeSizeError(QRError):
    """Raised when the payload exceeds maximum QR code storage capacity."""
    pass


class QRDecodeError(QRError):
    """Raised when an image does not contain a valid QR code or cannot be read."""
    pass


def generate_qr_image(
    payload_str: str,
    box_size: int = QR_BOX_SIZE,
    border: int = QR_BORDER,
    fill_color: str = "black",
    back_color: str = "white"
) -> Image.Image:
    """
    Generates a high-resolution PIL Image QR code from the serialized payload string.
    """
    if not payload_str or not payload_str.strip():
        raise QRError("Cannot generate QR code from empty payload.")

    # QR version 40 binary limit is ~2953 bytes. Practically 2300 is the safe upper bound.
    if len(payload_str) > 2600:
        raise QRCodeSizeError(
            f"Note payload ({len(payload_str)} characters) is too large for a reliable QR code. "
            "Please shorten the note content to ensure it fits."
        )

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )

    try:
        qr.add_data(payload_str)
        qr.make(fit=True)
        img = qr.make_image(fill_color=fill_color, back_color=back_color).convert("RGB")
        return img
    except qrcode.exceptions.DataOverflowError:
        raise QRCodeSizeError(
            "The encrypted note exceeds maximum QR code density. Please reduce the note length."
        )
    except Exception as e:
        logger.error("QR generation error: %s", str(e))
        raise QRError(f"Failed to generate QR code: {str(e)}")


def save_qr_image(img: Image.Image, output_path: Path | str) -> Path:
    """
    Saves a generated QR code image to a user-specified or default path.
    """
    path = Path(output_path).resolve()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(path), format="PNG")
        logger.info("Exported QR code image to: %s", str(path))
        return path
    except PermissionError:
        raise QRError(f"Permission denied when saving QR image to: {path}")
    except Exception as e:
        logger.error("QR save error: %s", str(e))
        raise QRError(f"Could not save QR image: {str(e)}")


def get_default_export_filename(note_uuid: str) -> str:
    """Returns a safe export filename derived from note UUID, not secret contents."""
    short_id = note_uuid[:8] if note_uuid else "note"
    return f"secure_note_{short_id}.png"


def decode_qr_from_image(image_input: Path | str | Image.Image) -> str:
    """
    Decodes the QR code text from an image path or PIL Image object.
    Employs multi-detector passes and image preprocessing for high reliability.
    """
    # 1. Convert input to numpy BGR array for OpenCV
    if isinstance(image_input, (str, Path)):
        file_path = Path(image_input)
        if not file_path.exists():
            raise QRDecodeError(f"Selected file does not exist: {file_path}")
        try:
            with open(file_path, "rb") as f:
                bytes_data = np.frombuffer(f.read(), np.uint8)
                cv_img = cv2.imdecode(bytes_data, cv2.IMREAD_COLOR)
        except Exception as e:
            raise QRDecodeError(f"Unable to read image file: {str(e)}")

        if cv_img is None:
            raise QRDecodeError("The selected file is not a valid or supported image format.")
    elif isinstance(image_input, Image.Image):
        cv_img = cv2.cvtColor(np.array(image_input.convert("RGB")), cv2.COLOR_RGB2BGR)
    else:
        raise QRDecodeError("Unsupported image input type.")

    # Add a white border to ensure quiet zone is sufficient for OpenCV
    cv_img_bordered = cv2.copyMakeBorder(
        cv_img, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=[255, 255, 255]
    )

    detectors = []
    if hasattr(cv2, "QRCodeDetectorAruco"):
        try:
            detectors.append(cv2.QRCodeDetectorAruco())
        except Exception:
            pass
    detectors.append(cv2.QRCodeDetector())

    # Preprocessed variants to try
    gray = cv2.cvtColor(cv_img_bordered, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )

    image_variants = [cv_img_bordered, cv_img, gray, thresh]

    for detector in detectors:
        for img_variant in image_variants:
            try:
                val, pts, _ = detector.detectAndDecode(img_variant)
                if val and val.strip():
                    return val.strip()
            except Exception:
                continue

    raise QRDecodeError(
        "No readable QR code found in the image. "
        "Please ensure the image is clear, well-lit, and not heavily cropped."
    )


class WebcamScanner:
    """
    Handles live camera capture and QR detection for Tkinter GUI.
    Safely releases system camera resources on stop.
    """

    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.cap: Optional[cv2.VideoCapture] = None
        self.detector = cv2.QRCodeDetector()
        self.is_running = False

    @staticmethod
    def is_camera_available(camera_index: int = 0) -> bool:
        """Checks if a webcam is accessible."""
        try:
            test_cap = cv2.VideoCapture(camera_index)
            if not test_cap or not test_cap.isOpened():
                if test_cap:
                    test_cap.release()
                return False
            ret, _ = test_cap.read()
            test_cap.release()
            return ret
        except Exception:
            return False

    def start(self) -> bool:
        """Starts the video capture stream."""
        if self.is_running and self.cap and self.cap.isOpened():
            return True

        self.cap = cv2.VideoCapture(self.camera_index)
        if not self.cap or not self.cap.isOpened():
            self.stop()
            return False

        self.is_running = True
        return True

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray], Optional[str]]:
        """
        Reads one frame from the webcam.
        Returns:
            (success: bool, frame_bgr: np.ndarray, decoded_payload: str or None)
        """
        if not self.is_running or not self.cap or not self.cap.isOpened():
            return False, None, None

        ret, frame = self.cap.read()
        if not ret or frame is None:
            return False, None, None

        decoded_payload = None
        try:
            val, pts, _ = self.detector.detectAndDecode(frame)
            if val and val.strip():
                decoded_payload = val.strip()
                # Draw green bounding box around detected QR
                if pts is not None and len(pts) > 0:
                    pts = pts.astype(int).reshape(-1, 2)
                    for i in range(len(pts)):
                        pt1 = tuple(pts[i])
                        pt2 = tuple(pts[(i + 1) % len(pts)])
                        cv2.line(frame, pt1, pt2, (0, 255, 0), 3)
        except Exception:
            pass

        return True, frame, decoded_payload

    def stop(self) -> None:
        """Stops the camera stream and releases all camera resources."""
        self.is_running = False
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None
