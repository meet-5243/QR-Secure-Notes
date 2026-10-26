"""
Cryptographic module for QR Secure Notes.
Implements AES-256-GCM authenticated encryption and Argon2id/Scrypt key derivation.
Ensures fresh cryptographically secure salts and nonces per encryption operation.
"""

from __future__ import annotations
import base64
import json
import secrets
from datetime import datetime, timezone
from typing import Dict, Any, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.exceptions import InvalidTag

try:
    import argon2.low_level
    HAS_ARGON2 = True
except ImportError:  # pragma: no cover
    HAS_ARGON2 = False

from config import (
    PAYLOAD_VERSION,
    ENCRYPTION_ALGORITHM,
    KEY_SIZE_BYTES,
    GCM_NONCE_SIZE_BYTES,
    SALT_SIZE_BYTES,
    ARGON2_TIME_COST,
    ARGON2_MEMORY_COST,
    ARGON2_PARALLELISM,
    SCRYPT_N,
    SCRYPT_R,
    SCRYPT_P,
    MAX_TITLE_CHARS,
    MAX_CONTENT_CHARS,
    logger,
)


class CryptoError(Exception):
    """Base exception for cryptographic errors."""
    pass


class PayloadValidationError(CryptoError):
    """Raised when an encrypted payload is structurally invalid or tampered."""
    pass


class DecryptionFailedError(CryptoError):
    """Raised when decryption fails due to wrong password or tampered ciphertext/tag."""
    pass


def derive_key(password: str, salt: bytes, kdf_info: Dict[str, Any]) -> bytes:
    """
    Derives a 256-bit symmetric key from a password and salt using the specified KDF.
    Supports Argon2id with Scrypt fallback.
    """
    if not password:
        raise CryptoError("Password cannot be empty.")
    if not salt or len(salt) < 16:
        raise CryptoError("Salt must be at least 16 bytes.")

    kdf_name = kdf_info.get("name", "Argon2id")
    params = kdf_info.get("params", {})

    password_bytes = password.encode("utf-8")

    if kdf_name == "Argon2id" and HAS_ARGON2:
        time_cost = params.get("time_cost", ARGON2_TIME_COST)
        memory_cost = params.get("memory_cost", ARGON2_MEMORY_COST)
        parallelism = params.get("parallelism", ARGON2_PARALLELISM)
        return argon2.low_level.hash_secret_raw(
            secret=password_bytes,
            salt=salt,
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=KEY_SIZE_BYTES,
            type=argon2.low_level.Type.ID
        )
    elif kdf_name in ("Argon2id", "Scrypt"):
        # Fallback to Scrypt if Argon2 is not available or if specified
        n = params.get("n", SCRYPT_N)
        r = params.get("r", SCRYPT_R)
        p = params.get("p", SCRYPT_P)
        kdf = Scrypt(salt=salt, length=KEY_SIZE_BYTES, n=n, r=r, p=p)
        return kdf.derive(password_bytes)
    else:
        raise CryptoError(f"Unsupported key derivation function: {kdf_name}")


def encrypt_note(
    title: str,
    content: str,
    password: str,
    category: str = "General",
    note_uuid: str | None = None,
    expires_at: str | None = None,
    use_scrypt: bool = False
) -> Tuple[Dict[str, Any], str]:
    """
    Encrypts note title, content, and metadata using AES-256-GCM.
    Returns:
        tuple: (payload_dict, serialized_payload_json)
    """
    if not title or not title.strip():
        title = "Untitled Note"
    if not content or not content.strip():
        raise CryptoError("Note content cannot be empty.")

    if len(title) > MAX_TITLE_CHARS:
        raise CryptoError(f"Title exceeds maximum length of {MAX_TITLE_CHARS} characters.")
    if len(content) > MAX_CONTENT_CHARS:
        raise CryptoError(
            f"Note content is {len(content)} characters, exceeding the QR safe limit of {MAX_CONTENT_CHARS} characters."
        )

    if not password:
        raise CryptoError("A non-empty password is required to encrypt the note.")

    # Generate fresh cryptographically secure salt and nonce
    salt = secrets.token_bytes(SALT_SIZE_BYTES)
    nonce = secrets.token_bytes(GCM_NONCE_SIZE_BYTES)

    # Determine KDF configuration
    if not use_scrypt and HAS_ARGON2:
        kdf_info = {
            "name": "Argon2id",
            "params": {
                "time_cost": ARGON2_TIME_COST,
                "memory_cost": ARGON2_MEMORY_COST,
                "parallelism": ARGON2_PARALLELISM,
            }
        }
    else:
        kdf_info = {
            "name": "Scrypt",
            "params": {
                "n": SCRYPT_N,
                "r": SCRYPT_R,
                "p": SCRYPT_P,
            }
        }

    key = derive_key(password, salt, kdf_info)

    # Construct inner plaintext object
    now_utc = datetime.now(timezone.utc).isoformat()
    if not note_uuid:
        note_uuid = secrets.token_hex(8)

    inner_plaintext_dict = {
        "title": title.strip(),
        "content": content,
        "category": category.strip() if category else "General",
        "created_at": now_utc,
        "uuid": note_uuid,
    }
    if expires_at:
        inner_plaintext_dict["expires_at"] = expires_at

    inner_bytes = json.dumps(inner_plaintext_dict, separators=(",", ":")).encode("utf-8")

    # Perform AES-256-GCM authenticated encryption
    aesgcm = AESGCM(key)
    # The returned ciphertext includes the 16-byte authentication tag appended at the end
    ciphertext_with_tag = aesgcm.encrypt(nonce, inner_bytes, associated_data=None)

    raw_ciphertext = ciphertext_with_tag[:-16]
    raw_tag = ciphertext_with_tag[-16:]

    # Construct outer versioned payload
    payload = {
        "v": PAYLOAD_VERSION,
        "alg": ENCRYPTION_ALGORITHM,
        "uuid": note_uuid,
        "created_at": now_utc,
        "kdf": kdf_info,
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(raw_ciphertext).decode("ascii"),
        "tag": base64.b64encode(raw_tag).decode("ascii"),
    }

    serialized = json.dumps(payload, separators=(",", ":"))
    logger.info("Successfully encrypted note payload with UUID: %s", note_uuid)
    return payload, serialized


def validate_payload_structure(payload: Dict[str, Any]) -> None:
    """Validates the structure, types, and limits of an encrypted payload."""
    if not isinstance(payload, dict):
        raise PayloadValidationError("Payload must be a valid JSON dictionary.")

    version = payload.get("v")
    if version != PAYLOAD_VERSION:
        raise PayloadValidationError(
            f"Unsupported payload version '{version}'. Expected version {PAYLOAD_VERSION}."
        )

    alg = payload.get("alg")
    if alg != ENCRYPTION_ALGORITHM:
        raise PayloadValidationError(f"Unsupported algorithm '{alg}'. Expected {ENCRYPTION_ALGORITHM}.")

    required_keys = ("salt", "nonce", "ciphertext", "tag", "kdf")
    for key in required_keys:
        if key not in payload:
            raise PayloadValidationError(f"Payload missing required security field: '{key}'.")

    kdf = payload.get("kdf")
    if not isinstance(kdf, dict) or "name" not in kdf:
        raise PayloadValidationError("Invalid KDF descriptor in payload.")

    # Validate Base64 fields
    for b64_field in ("salt", "nonce", "ciphertext", "tag"):
        val = payload.get(b64_field)
        if not isinstance(val, str) or not val:
            raise PayloadValidationError(f"Field '{b64_field}' must be a non-empty base64 string.")
        try:
            decoded = base64.b64decode(val.encode("ascii"), validate=True)
            if b64_field == "nonce" and len(decoded) != GCM_NONCE_SIZE_BYTES:
                raise PayloadValidationError(
                    f"Invalid nonce length: expected {GCM_NONCE_SIZE_BYTES} bytes, got {len(decoded)}."
                )
            if b64_field == "tag" and len(decoded) != 16:
                raise PayloadValidationError(
                    f"Invalid authentication tag length: expected 16 bytes, got {len(decoded)}."
                )
            if b64_field == "salt" and len(decoded) < 16:
                raise PayloadValidationError("Salt must be at least 16 bytes.")
        except Exception as e:
            if isinstance(e, PayloadValidationError):
                raise
            raise PayloadValidationError(f"Invalid Base64 encoding in field '{b64_field}'.")


def decrypt_note(payload_or_json: Dict[str, Any] | str, password: str) -> Dict[str, Any]:
    """
    Authenticates and decrypts an encrypted payload using the provided password.
    Returns:
        dict: The decrypted inner dictionary (title, content, category, created_at, uuid, etc.)
    Raises:
        PayloadValidationError: If payload is malformed or invalid version.
        DecryptionFailedError: If password is wrong or ciphertext/tag was tampered with.
    """
    if not password:
        raise DecryptionFailedError("Password cannot be empty.")

    if isinstance(payload_or_json, str):
        try:
            payload = json.loads(payload_or_json)
        except Exception:
            raise PayloadValidationError("Corrupted QR payload: Not valid JSON.")
    else:
        payload = payload_or_json

    validate_payload_structure(payload)

    salt = base64.b64decode(payload["salt"].encode("ascii"))
    nonce = base64.b64decode(payload["nonce"].encode("ascii"))
    ciphertext = base64.b64decode(payload["ciphertext"].encode("ascii"))
    tag = base64.b64decode(payload["tag"].encode("ascii"))
    kdf_info = payload["kdf"]

    try:
        key = derive_key(password, salt, kdf_info)
    except Exception as e:
        logger.warning("Key derivation failed: %s", str(e))
        raise DecryptionFailedError("Unable to derive decryption key.")

    ciphertext_with_tag = ciphertext + tag
    aesgcm = AESGCM(key)

    try:
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext_with_tag, associated_data=None)
    except InvalidTag:
        logger.warning("Authentication tag mismatch during decryption.")
        raise DecryptionFailedError(
            "Unable to unlock this note. The password may be incorrect or the QR code payload has been tampered with."
        )
    except Exception as e:
        logger.warning("Unexpected decryption failure: %s", type(e).__name__)
        raise DecryptionFailedError("Unable to unlock this note. Check the password or QR code.")

    try:
        inner_dict = json.loads(decrypted_bytes.decode("utf-8"))
        if not isinstance(inner_dict, dict) or "content" not in inner_dict:
            raise ValueError("Inner structure missing content")
        return inner_dict
    except Exception:
        raise DecryptionFailedError("Decrypted data is corrupted.")
