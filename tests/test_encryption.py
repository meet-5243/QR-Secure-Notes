"""
Unit tests for the encryption module.
Verifies authenticated encryption, key derivation, tampering detection, and payload validation.
"""

import pytest
import json
import base64
from encryption import (
    encrypt_note,
    decrypt_note,
    derive_key,
    CryptoError,
    PayloadValidationError,
    DecryptionFailedError,
)

def test_encrypt_decrypt_success():
    title = "Top Secret Meeting"
    content = "Meeting location is room 402 at 10:00 AM."
    password = "SuperSecurePassword123!"
    category = "Confidential"

    payload, serialized = encrypt_note(
        title=title,
        content=content,
        password=password,
        category=category
    )

    assert payload["v"] == 1
    assert payload["alg"] == "AES-256-GCM"
    assert "salt" in payload
    assert "nonce" in payload
    assert "ciphertext" in payload
    assert "tag" in payload
    # Plaintext should never appear in payload or serialized JSON
    assert title not in serialized
    assert content not in serialized
    assert password not in serialized

    # Decrypt with correct password
    decrypted = decrypt_note(serialized, password)
    assert decrypted["title"] == title
    assert decrypted["content"] == content
    assert decrypted["category"] == category


def test_decrypt_incorrect_password():
    title = "Secret"
    content = "Sensitive content"
    password = "CorrectPassword123"

    _, serialized = encrypt_note(title, content, password)

    with pytest.raises(DecryptionFailedError):
        decrypt_note(serialized, "WrongPassword456")


def test_tampered_ciphertext_fails():
    title = "Banking Pin"
    content = "PIN: 9876"
    password = "MySafePassword"

    payload, _ = encrypt_note(title, content, password)

    # Tamper with ciphertext by flipping bits in base64
    raw_cipher = bytearray(base64.b64decode(payload["ciphertext"]))
    raw_cipher[0] ^= 0xFF
    payload["ciphertext"] = base64.b64encode(raw_cipher).decode("ascii")

    with pytest.raises(DecryptionFailedError):
        decrypt_note(payload, password)


def test_tampered_tag_fails():
    title = "Medical Record"
    content = "Diagnosis data"
    password = "DocPassword"

    payload, _ = encrypt_note(title, content, password)

    raw_tag = bytearray(base64.b64decode(payload["tag"]))
    raw_tag[0] ^= 0xFF
    payload["tag"] = base64.b64encode(raw_tag).decode("ascii")

    with pytest.raises(DecryptionFailedError):
        decrypt_note(payload, password)


def test_unique_salts_and_nonces_per_encryption():
    title = "Constant Note"
    content = "Same note content"
    password = "IdenticalPassword"

    payload1, _ = encrypt_note(title, content, password)
    payload2, _ = encrypt_note(title, content, password)

    assert payload1["salt"] != payload2["salt"]
    assert payload1["nonce"] != payload2["nonce"]
    assert payload1["ciphertext"] != payload2["ciphertext"]


def test_malformed_payload_rejected():
    with pytest.raises(PayloadValidationError):
        decrypt_note("not json at all", "somepass")

    invalid_version = {"v": 99, "alg": "AES-256-GCM", "salt": "abc", "nonce": "def", "ciphertext": "ghi", "tag": "jkl", "kdf": {"name": "Argon2id"}}
    with pytest.raises(PayloadValidationError):
        decrypt_note(invalid_version, "somepass")

    missing_field = {"v": 1, "alg": "AES-256-GCM", "salt": "abc", "nonce": "def"}
    with pytest.raises(PayloadValidationError):
        decrypt_note(missing_field, "somepass")


def test_empty_content_validation():
    with pytest.raises(CryptoError):
        encrypt_note("Title", "", "password")


def test_scrypt_fallback():
    title = "Scrypt Test"
    content = "Testing explicit scrypt derivation"
    password = "ScryptPassword"

    payload, serialized = encrypt_note(title, content, password, use_scrypt=True)
    assert payload["kdf"]["name"] == "Scrypt"

    decrypted = decrypt_note(serialized, password)
    assert decrypted["content"] == content
