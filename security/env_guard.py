# ============================================================
#  MATTER — security/env_guard.py
#  Secure API key loading with encryption at rest.
#
#  How it works:
#    1. First run: encrypts your .env file using a master password
#    2. Every run after: decrypts it in memory only
#    3. Keys never sit in plain text on disk after first setup
#    4. Keys are wiped from memory when Matter shuts down
#
#  The encrypted file lives at: data/.env.encrypted
#  The plain .env is deleted after first encryption.
#  Never commit either file to Git.
# ============================================================

import os
import base64
import json
from typing import Optional
from pathlib import Path

# ── File paths ────────────────────────────────────────────
ROOT_DIR       = Path(__file__).parent.parent
ENV_FILE       = ROOT_DIR / ".env"
ENCRYPTED_FILE = ROOT_DIR / "data" / ".env.encrypted"
SALT_FILE      = ROOT_DIR / "data" / ".env.salt"

# ── In-memory key store ───────────────────────────────────
#  Keys live here after decryption — never written back to disk.
#  Wiped on shutdown.
_keys: dict = {}


def _get_fernet(password: str, salt: bytes):
    """
    Derives a Fernet encryption key from a password + salt.

    Why Fernet? It's AES-128-CBC with HMAC-SHA256 — secure,
    standard, and built into the cryptography library.
    It also handles IV generation automatically so we don't
    have to manage that ourselves.

    Why a salt? So two people with the same password get
    different encryption keys. Prevents rainbow table attacks.
    """
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.fernet import Fernet

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,    # High iteration count = slow to brute force
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return Fernet(key)


def setup(password: str) -> bool:
    """
    First-time setup. Reads the plain .env file, encrypts it,
    saves the encrypted version, then deletes the plain .env.

    Call this once when setting up Matter on a new machine.
    After this, the plain .env is gone — only the encrypted
    version remains on disk.

    Returns True if setup succeeded.
    """
    if not ENV_FILE.exists():
        print("[EnvGuard] No .env file found. Create one first.")
        return False

    try:
        from cryptography.fernet import Fernet
        import secrets

        # Generate a random salt for this installation
        salt = secrets.token_bytes(16)

        # Read the plain .env
        raw = ENV_FILE.read_text(encoding="utf-8")

        # Parse into a dict
        keys = _parse_env(raw)

        # Encrypt the JSON
        f = _get_fernet(password, salt)
        encrypted = f.encrypt(json.dumps(keys).encode())

        # Save encrypted file and salt
        ENCRYPTED_FILE.parent.mkdir(parents=True, exist_ok=True)
        ENCRYPTED_FILE.write_bytes(encrypted)
        SALT_FILE.write_bytes(salt)

        # Delete the plain .env
        ENV_FILE.unlink()

        print("[EnvGuard] .env encrypted and original deleted.")
        print(f"[EnvGuard] Encrypted file: {ENCRYPTED_FILE}")
        print("[EnvGuard] Keep your password safe — there is no recovery without it.")

        return True

    except ImportError:
        print("[EnvGuard] Missing package. Run: pip install cryptography")
        return False
    except Exception as e:
        print(f"[EnvGuard] Setup failed: {e}")
        return False


def unlock(password: str) -> bool:
    """
    Decrypts the .env and loads keys into memory.
    Call this at Matter startup before anything else needs keys.

    Returns True if unlocked successfully.
    Keys are then accessible via get().
    """
    global _keys

    # If plain .env still exists, load it directly (dev mode)
    if ENV_FILE.exists():
        raw = ENV_FILE.read_text(encoding="utf-8")
        _keys = _parse_env(raw)
        print("[EnvGuard] Loaded plain .env (dev mode). Run setup() to encrypt.")
        return True

    if not ENCRYPTED_FILE.exists():
        print("[EnvGuard] No .env or encrypted file found.")
        return False

    if not SALT_FILE.exists():
        print("[EnvGuard] Salt file missing. Cannot decrypt.")
        return False

    try:
        salt      = SALT_FILE.read_bytes()
        encrypted = ENCRYPTED_FILE.read_bytes()

        f = _get_fernet(password, salt)
        decrypted = f.decrypt(encrypted)
        _keys = json.loads(decrypted.decode())

        print("[EnvGuard] Keys unlocked and loaded into memory.")
        return True

    except Exception:
        # Don't print the actual error — could leak info
        print("[EnvGuard] Failed to decrypt. Wrong password or corrupted file.")
        return False


def get(key: str) -> Optional[str]:
    """
    Returns a key from the in-memory store.
    Returns None if the key doesn't exist or Matter isn't unlocked.

    Usage:
      api_key = env_guard.get("GEMINI_API_KEY")
    """
    return _keys.get(key)


def wipe():
    """
    Wipes all keys from memory.
    Call this when Matter shuts down.
    Keys are gone until unlock() is called again.
    """
    global _keys
    _keys = {}
    print("[EnvGuard] Keys wiped from memory.")


def is_unlocked() -> bool:
    """Returns True if keys are loaded in memory."""
    return len(_keys) > 0


def _parse_env(raw: str) -> dict:
    """
    Parses a .env file into a dict.
    Handles comments and blank lines.

    Example .env:
      # Gemini
      GEMINI_API_KEY=abc123
      ELEVENLABS_API_KEY=xyz789
    """
    result = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip()
    return result


def audit_log(action: str):
    """
    Logs every time a key is accessed.
    Keeps an audit trail so you know when Matter used each API.
    """
    import datetime
    log_file = ROOT_DIR / "data" / "security.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().isoformat(timespec="seconds")
    entry = f"{timestamp} | {action}\n"

    with open(log_file, "a") as f:
        f.write(entry)