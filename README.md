# QR SECURE NOTES
### Offline Encrypted Notes Management & Secure QR Distribution System

[![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Encryption](https://img.shields.io/badge/Encryption-AES--256--GCM-green.svg)](https://en.wikipedia.org/wiki/Galois/Counter_Mode)
[![KDF](https://img.shields.io/badge/Key%20Derivation-Argon2id-orange.svg)](https://en.wikipedia.org/wiki/Argon2)
[![GUI](https://img.shields.io/badge/GUI-Tkinter%20%2F%20ttk-navy.svg)](https://docs.python.org/3/library/tkinter.html)
[![Database](https://img.shields.io/badge/Database-SQLite%20(Local)-lightgrey.svg)](https://sqlite.org/)

---

## 1. PROJECT OVERVIEW

**QR Secure Notes** is a native, offline Python desktop application that empowers users to create private notes, encrypt them with **AES-256-GCM authenticated encryption**, derive cryptographic keys via **Argon2id** (with Scrypt fallback), and serialize the encrypted payload into self-contained **QR code images (PNG)**.

The application allows users to store and manage encrypted records in a local **SQLite** database, import QR code image files or scan them live using a computer webcam, and safely decrypt them upon entering the correct password.

### Key Highlights
- **100% Native Desktop Python**: Zero web framework overhead—no Flask, Django, React, or Electron. Built purely with Python 3, Tkinter/ttk, and OpenCV.
- **Zero-Knowledge Architecture**: The database and exported QR codes store strictly ciphertext and security parameters. Plaintext titles, secrets, passwords, and encryption keys are never stored on disk or logged.
- **Authenticated Encryption**: Employs AES-256 in Galois/Counter Mode (GCM). Any tampering or corruption of the QR code graphic fails authentication immediately.
- **Offline & Private**: Functions without internet connectivity or remote servers.

---

## 2. APPLICATION ARCHITECTURE & MODULES

```
QR_Secure_Notes/
│
├── main.py                     # Application entry point & lifecycle manager
├── config.py                   # Global constants, paths, crypto parameters, and styling
├── encryption.py               # AES-256-GCM cipher and Argon2id/Scrypt key derivation
├── database.py                 # SQLite schema, parameterized queries, and backup engine
├── qr_manager.py               # QR code generation, PNG export, multi-pass decode & webcam
├── note_manager.py             # Business logic, password strength, expiration & orchestration
├── ui.py                       # Modern dark navy Tkinter/ttk desktop GUI
├── requirements.txt            # Python dependencies
├── README.md                   # Complete architectural guide & viva preparation
├── .gitignore                  # Git exclusions for environments, caches, and user data
│
├── data/
│   └── secure_notes.db         # Local SQLite database (created automatically on launch)
│
├── exports/                    # Default folder for exported QR images and JSON payloads
│
├── logs/                       # Safe diagnostic logging (no secrets or decrypted content)
│
└── tests/                      # Automated pytest verification suite
    ├── test_encryption.py      # Tests for AES-GCM, Argon2id, bit tampering, and auth tags
    ├── test_database.py        # Tests for SQLite CRUD, unique UUIDs, and live backup
    ├── test_qr_manager.py      # Tests for QR code generation, sizing, and multi-pass decode
    ├── test_note_manager.py    # Tests for password strength, expiration, and unlocking
    └── test_integration.py     # End-to-end full lifecycle integration tests
```

### Module Responsibilities

| Module | Core Responsibility |
|---|---|
| `config.py` | Sets up directory structures (`data/`, `exports/`, `logs/`), crypto constants (salt: 16 bytes, nonce: 12 bytes, key: 32 bytes), Argon2id parameters (2 iterations, 64MB RAM, 2 threads), and dark navy theme colors. |
| `encryption.py` | Handles AES-256-GCM encryption/decryption, Argon2id key derivation (`argon2.low_level.hash_secret_raw`), Scrypt fallback, Base64 payload packaging, and structure validation. |
| `database.py` | Manages `secure_notes.db` with parameterized queries, index creation, auto-expiration updates, and live online database backups using SQLite's backup API. |
| `qr_manager.py` | Wraps `qrcode` to generate PNG images, applies multi-pass OpenCV decoding (direct, grayscale, adaptive Gaussian thresholding), and provides clean webcam scanner capture. |
| `note_manager.py` | Orchestrates operations between UI, database, and encryption. Evaluates password strength (entropy, length, variety), tracks session statistics, and formats dates. |
| `ui.py` | Renders a cybersecurity dark-theme GUI featuring 6 navigation panels, a live character counter, a password strength meter, image previews, and responsive tables. |
| `main.py` | Initializes the database, checks environment prerequisites, creates the Tkinter root window, and launches the desktop app. |

---

## 3. DATABASE SCHEMA

The SQLite database is stored locally at `data/secure_notes.db`.

```sql
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_uuid TEXT UNIQUE NOT NULL,
    encrypted_payload TEXT NOT NULL,
    category TEXT DEFAULT 'General',
    created_at TEXT NOT NULL,
    expires_at TEXT,
    status TEXT DEFAULT 'active' CHECK(status IN ('active', 'expired', 'deleted')),
    updated_at TEXT NOT NULL
);

-- Performance and query optimization indexes:
CREATE INDEX IF NOT EXISTS idx_notes_uuid ON notes (note_uuid);
CREATE INDEX IF NOT EXISTS idx_notes_status ON notes (status);
CREATE INDEX IF NOT EXISTS idx_notes_created_at ON notes (created_at);
CREATE INDEX IF NOT EXISTS idx_notes_category ON notes (category);
```

> **Confidentiality by Design**: Plaintext note titles and contents are **never** stored in separate database columns. Both title and content are encrypted together inside the `encrypted_payload`. Only non-sensitive operational metadata (random UUID, category, and UTC timestamps) are stored in clear database fields.

---

## 4. CRYPTOGRAPHIC WORKFLOW

### The Encrypted QR Payload Format (Version 1)
The data encoded into each QR code is a compact, versioned JSON object:

```json
{
  "v": 1,
  "alg": "AES-256-GCM",
  "uuid": "7a3f89b1c2e4d0f5",
  "created_at": "2026-10-26T16:00:00Z",
  "kdf": {
    "name": "Argon2id",
    "params": {
      "time_cost": 2,
      "memory_cost": 65536,
      "parallelism": 2
    }
  },
  "salt": "dGVzdF9zYWx0XzEyMzQ1Ng==",
  "nonce": "bm9uY2VfOTZiaXRz",
  "ciphertext": "YWJjZGVmZ2hpams=",
  "tag": "MTZieXRlX2F1dGhfdGFn"
}
```

### Encryption Workflow
```
[Plaintext Title + Content + Metadata]
               │
               ▼
   [Generate 16-byte Random Salt] ───┐
   [User Password] ──────────────────┼──> [Argon2id KDF] ──> [256-bit Symmetric Key]
                                                                     │
   [Generate 12-byte Unique Nonce] ──────────────────────────────────┼──> [AES-256-GCM Authenticated Encryption]
                                                                     │                    │
                                                                     ▼                    ▼
                                                        [Base64 Ciphertext]      [16-byte Auth Tag]
                                                                     │                    │
                                                                     └──────────┬─────────┘
                                                                                ▼
                                                                [Versioned JSON Payload]
                                                                                │
                                                                                ▼
                                                                  [QR Code Generator (PNG)]
```

### Decryption Workflow
```
[QR Code Image / Webcam Capture]
               │
               ▼
   [OpenCV QR Detector] ──> [JSON Payload Validation (v=1, AES-256-GCM)]
                                     │
   [User Enters Password] ───────────┼──> [Argon2id KDF with Stored Salt & Params] ──> [256-bit Key]
                                                                                           │
                                                                                           ▼
                                                        [AES-GCM Authenticated Decryption with Nonce & Tag]
                                                                                           │
                                                      ┌────────────────────────────────────┴────────────────────────────────────┐
                                                      ▼                                                                         ▼
                                            [Auth Tag Validated]                                                       [Invalid Tag / Modified]
                                                      │                                                                         │
                                                      ▼                                                                         ▼
                                      [Plaintext Title & Content Displayed]                                        [Generic Rejection Error]
```

---

## 5. INSTALLATION & SETUP

### Prerequisites
- Python 3.11, 3.12, or 3.13 installed on Windows, macOS, or Linux.
- Webcam (optional, only for live camera QR scanning).

### Windows Setup Instructions

Open PowerShell or Command Prompt in the project folder:

```bash
# 1. Create a virtual environment
python -m venv venv

# 2. Activate the virtual environment
venv\Scripts\activate

# 3. Upgrade pip
python -m pip install --upgrade pip

# 4. Install project dependencies
pip install -r requirements.txt

# 5. Launch the application
python main.py
```

### macOS / Linux Setup Instructions

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
python3 main.py
```

---

## 6. RUNNING AUTOMATED TESTS

Automated tests are written with `pytest` covering all cryptographic, database, QR, and workflow operations.

```bash
# Run the entire test suite with verbose output
python -m pytest tests/ -v
```

Expected output:
```
tests/test_database.py::test_init_db_idempotent PASSED                   [  4%]
tests/test_database.py::test_insert_and_retrieve_note PASSED             [  8%]
tests/test_database.py::test_unique_uuid_constraint PASSED               [ 12%]
tests/test_database.py::test_delete_note PASSED                          [ 16%]
tests/test_database.py::test_expiration_status_update PASSED             [ 20%]
tests/test_database.py::test_backup_database PASSED                      [ 24%]
tests/test_encryption.py::test_encrypt_decrypt_success PASSED            [ 28%]
tests/test_encryption.py::test_decrypt_incorrect_password PASSED         [ 32%]
tests/test_encryption.py::test_tampered_ciphertext_fails PASSED          [ 36%]
tests/test_encryption.py::test_tampered_tag_fails PASSED                 [ 40%]
tests/test_encryption.py::test_unique_salts_and_nonces_per_encryption PASSED [ 44%]
tests/test_encryption.py::test_malformed_payload_rejected PASSED         [ 48%]
tests/test_encryption.py::test_empty_content_validation PASSED           [ 52%]
tests/test_encryption.py::test_scrypt_fallback PASSED                    [ 56%]
tests/test_integration.py::test_full_roundtrip_workflow PASSED           [ 60%]
tests/test_note_manager.py::test_password_strength_evaluation PASSED     [ 64%]
tests/test_note_manager.py::test_create_and_unlock_note PASSED           [ 68%]
tests/test_note_manager.py::test_password_mismatch_error PASSED          [ 72%]
tests/test_note_manager.py::test_expiration_calculation PASSED           [ 76%]
tests/test_note_manager.py::test_export_saved_note_qr PASSED             [ 80%]
tests/test_qr_manager.py::test_qr_generation_and_decode PASSED           [ 84%]
tests/test_qr_manager.py::test_qr_save_and_decode_from_file PASSED       [ 88%]
tests/test_qr_manager.py::test_oversized_payload_rejected PASSED         [ 92%]
tests/test_qr_manager.py::test_decode_invalid_image PASSED               [ 96%]
tests/test_qr_manager.py::test_default_export_filename PASSED            [100%]
============================= 25 passed in 5.52s ==============================
```

---

## 7. STEP-BY-STEP PROJECT DEMONSTRATION

Follow these steps to demonstrate the application during a project evaluation or viva:

1. **Launch**: Run `python main.py`. The modern dark-themed dashboard appears with real-time statistics (total notes, active notes, expired notes, and session QR count).
2. **Create a Note**:
   - Navigate to **"Create Secure Note"**.
   - Enter title: `Server Root Credentials`.
   - Enter content: `SSH Key: ed25519-abc12345; Password: super_secret_passphrase; Server: 192.168.1.50`.
   - Type password: `Secur3P@ssw0rd!2026`. Observe the real-time password strength meter indicator turn green ("Strong").
   - Click **"Generate Secure QR"**.
   - The high-resolution QR preview renders on the right side.
   - Click **"Save QR Image (PNG)..."** and save it to `exports/server_credentials.png`.
3. **Verify Database Confidentiality**:
   - Navigate to **"My Notes"**.
   - Observe the new record. Note that only the non-sensitive UUID, Category, and Timestamps are visible.
   - Select the note and click **"Unlock / View Note"**.
   - Enter the password to decrypt and display the note in a modal dialog.
4. **Scan & Decrypt from File**:
   - Navigate to **"Scan QR Code"** -> **"Import QR Image"**.
   - Select `exports/server_credentials.png`.
   - The app verifies the payload structure, displays non-sensitive metadata (UUID, AES-256-GCM, Argon2id), and prompts for the password.
   - Intentionally type the wrong password: the app cleanly alerts `"Unable to unlock this note. The password may be incorrect or the QR code payload has been tampered with."`
   - Enter the correct password: the decrypted title and secret content appear cleanly.
5. **Live Webcam Scanner** (Optional):
   - Switch to the **"Live Webcam"** tab.
   - Click **"Start Camera"**.
   - Hold the exported QR code (on your phone screen or printed paper) up to the webcam.
   - The scanner highlights the QR code with a bounding box, automatically captures the payload, and prompts for decryption.
   - Click **"Stop Camera"** or navigate to any other view; the webcam resource is safely released.
6. **Database Backup**:
   - Navigate to **"Settings"**.
   - View live database size and cryptographic diagnostics.
   - Click **"Create Database Backup (.db)..."** to produce an atomic snapshot using SQLite's online backup API.

---

## 8. COLLEGE VIVA QUESTIONS & ANSWERS (Q&A)

### Q1: Why did you choose AES-256-GCM instead of AES-CBC or AES-ECB?
> **Answer**: AES-ECB (Electronic Codebook) is insecure because identical plaintext blocks produce identical ciphertext blocks, leaking patterns. AES-CBC provides confidentiality, but lacks integrity verification; it is vulnerable to bit-flipping attacks and padding oracle attacks unless combined with a separate HMAC. AES-GCM (Galois/Counter Mode) is an **Authenticated Encryption with Associated Data (AEAD)** cipher. It simultaneously provides confidentiality and produces a 128-bit authentication tag. If an attacker tampers with even a single bit of the QR code ciphertext, the authentication tag verification fails before any plaintext is processed.

### Q2: Why is a Key Derivation Function (KDF) like Argon2id necessary? Why not use SHA-256(password)?
> **Answer**: Plain cryptographic hashes like SHA-256 or MD5 are designed to be fast (computing hundreds of millions of hashes per second on GPUs). Human-chosen passwords have relatively low entropy, making them trivial to crack via dictionary or brute-force attacks if hashed with standard algorithms. **Argon2id** is a memory-hard and compute-hard KDF that requires significant RAM (64 MiB in our app) and computational iterations. This makes GPU, ASIC, and FPGA parallel hardware brute-forcing cost-prohibitive.

### Q3: What is the purpose of the Salt and the Nonce?
> **Answer**: 
> - **Salt**: A cryptographically random value (16 bytes) fed into Argon2id. It ensures that two users with the identical password will derive completely different 256-bit encryption keys. It prevents precomputed Rainbow Table attacks.
> - **Nonce** ("Number used once"): A unique 12-byte random value used in AES-GCM. Reusing a nonce with the same key in GCM mode destroys the cryptographic authenticity guarantees and can lead to key recovery. Our application generates a fresh, cryptographically secure random nonce via `secrets.token_bytes()` for every single encryption.

### Q4: If someone steals the SQLite database file (`secure_notes.db`), can they read the notes?
> **Answer**: No. The database stores strictly the encrypted JSON payloads (ciphertext, base64 salt, nonce, tag, and algorithm descriptor). Plaintext note titles and bodies are never stored in the database. Without the individual user passwords, an attacker holding the `.db` file cannot decrypt any notes.

### Q5: Can an expired note in a QR code be remotely revoked or made unreadable over the air?
> **Answer**: No, and this is an important cybersecurity distinction. A QR code is a static, portable graphic that holds the entire ciphertext mathematically inside its pattern. If a QR code is printed or exported, no offline desktop software can reach into the physical world to erase the graphic. In our application, expiration timestamps are evaluated upon unlocking and in the database, warning the user if the note is expired. True remote revocation requires an online authorization server with a central revocation list, which is outside the scope of an offline tool.

### Q6: How does the application ensure that passwords or keys are not left in persistent logs?
> **Answer**: The application uses a custom Python logging handler in `config.py` configured with strict privacy rules. Log messages only record non-sensitive events (such as `Note payload encrypted with UUID: 7a3f89b1c2e4d0f5` or `Database initialized`). Plaintext passwords, derived encryption keys, and note contents are never passed to the logging module.

### Q7: Why use SQLite's native `Connection.backup()` instead of a file copy (`shutil.copy`) for database backups?
> **Answer**: Performing a raw file copy on an active SQLite database can capture a corrupted file if a write transaction is in progress (a "torn write"). SQLite's `Connection.backup()` method locks the pages cleanly, coordinates with write-ahead logs, and guarantees an atomic, consistent database snapshot.

---

## 9. SECURITY BOUNDARIES & LIMITATIONS

1. **Local Operating System Security**: The application assumes the host operating system is untampered. It cannot defend against active OS-level keyloggers, screen-recording malware, or kernel-level memory dump utilities.
2. **Memory Residue**: Python handles strings as immutable objects managed by an automatic garbage collector. While cryptographic keys are handled as byte arrays and discarded upon function completion, complete in-memory memory wiping cannot be guaranteed in Python.
3. **Physical QR Security**: Exported QR codes must be stored in secure locations. Anyone possessing both the physical QR code and the password can decrypt its contents offline.

---

## 10. LICENSE & CREDITS

Developed as an academic cybersecurity and Python engineering desktop project. Built with standard Python 3.11+, Tkinter, Pillow, OpenCV, and Cryptography.
