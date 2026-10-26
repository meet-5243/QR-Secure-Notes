"""
Unit tests for QR code generation and decoding module.
Verifies generation, image round-trip decoding, oversize payload rejection, and error handling.
"""

import pytest
from pathlib import Path
from PIL import Image
import qr_manager

def test_qr_generation_and_decode():
    secret_text = '{"v":1,"alg":"AES-256-GCM","data":"encrypted_sample"}'
    img = qr_manager.generate_qr_image(secret_text)

    assert isinstance(img, Image.Image)
    assert img.size[0] > 100
    assert img.size[1] > 100

    # Test decoding from PIL Image directly
    decoded = qr_manager.decode_qr_from_image(img)
    assert decoded == secret_text


def test_qr_save_and_decode_from_file(tmp_path: Path):
    secret_payload = '{"test":"payload_content"}'
    img = qr_manager.generate_qr_image(secret_payload)

    export_path = tmp_path / "test_qr.png"
    saved_path = qr_manager.save_qr_image(img, export_path)
    assert saved_path.exists()

    # Decode from file path
    decoded = qr_manager.decode_qr_from_image(saved_path)
    assert decoded == secret_payload


def test_oversized_payload_rejected():
    huge_payload = "A" * 3500
    with pytest.raises(qr_manager.QRCodeSizeError):
        qr_manager.generate_qr_image(huge_payload)


def test_decode_invalid_image(tmp_path: Path):
    blank_img = Image.new("RGB", (200, 200), color="white")
    blank_path = tmp_path / "blank.png"
    blank_img.save(blank_path)

    with pytest.raises(qr_manager.QRDecodeError):
        qr_manager.decode_qr_from_image(blank_path)


def test_default_export_filename():
    fn = qr_manager.get_default_export_filename("a1b2c3d4e5f6")
    assert fn == "secure_note_a1b2c3d4.png"
