"""
lockdown.py — Matter Runtime Security Layer
============================================
What this script does:
  1. Verifies .env and encrypted secrets haven't been tampered with (hash check)
  2. Monitors active network connections and flags anything outside the whitelist
  3. Watches for suspicious processes that shouldn't be running alongside Matter
  4. Checks .env isn't accidentally exposed via git
  5. Writes every event to security/audit.log with timestamps

Usage:
    python lockdown.py              # full security check (run before starting Matter)
    python lockdown.py --snapshot   # create initial hash baseline (run once on clean files)
    python lockdown.py --monitor    # continuous live network monitor
    python lockdown.py --status     # quick status only
    python lockdown.py --clean      # wipe security artefacts and reset
"""

import os
import sys
import json
import time
import socket
import hashlib
import logging
import datetime
import platform
import subprocess
import threading
import argparse
from pathlib import Path


# ─────────────────────────────────────────────────────────────────
# CONFIGURATION — edit these to match your setup
# ─────────────────────────────────────────────────────────────────

MATTER_ROOT = Path(__file__).parent.resolve()

# Files whose contents must never change between runs without your knowledge
SENSITIVE_FILES = [
    MATTER_ROOT / ".env",
    MATTER_ROOT / ".env.encrypted",
    MATTER_ROOT / "security" / "audit.log",
    MATTER_ROOT / "core" / "config.py",
    MATTER_ROOT / "auth" / "auth.py",
]

# Hostnames Matter is legitimately allowed to connect to
ALLOWED_OUTBOUND_HOSTS = [
    "generativelanguage.googleapis.com",  # Gemini 2.0 Flash
    "api.elevenlabs.io",                  # ElevenLabs TTS
    "en.wikipedia.org",                   # Wikipedia
    "newsapi.org",                        # News API
    "www.google.com",                     # Web search fallback
    "api.openweathermap.org",             # Weather
]

# Tools that should NOT be running while Matter is active in production
# These are packet sniffers, debuggers, reverse engineering tools
SUSPICIOUS_PROCESSES = [
    "wireshark", "fiddler", "charles", "burpsuite",
    "mitmproxy", "procmon", "processhacker",
    "x64dbg", "ollydbg", "ida", "ghidra",
]

# How often (seconds) the live monitor rescans the network
NETWORK_SCAN_INTERVAL = 15

# Where the hash baseline is stored
HASH_STORE     = MATTER_ROOT / "security" / "file_hashes.json"
AUDIT_LOG      = MATTER_ROOT / "security" / "audit.log"


# ─────────────────────────────────────────────────────────────────
# LOGGING — everything goes to audit.log AND the terminal
# ─────────────────────────────────────────────────────────────────

AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(AUDIT_LOG, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("matter.lockdown")


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

def is_windows() -> bool:
    return platform.system() == "Windows"


def run_cmd(command: list[str], timeout: int = 15) -> tuple[int, str]:
    """
    Run a shell command safely and return (exit_code, output).
    capture_output=True means stdout and stderr are captured as strings,
    not printed to the terminal directly. We combine them into one string.
    Every failure mode is caught so one broken command doesn't crash the script.
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return -1, "timeout"
    except FileNotFoundError:
        return -1, f"not found: {command[0]}"
    except Exception as e:
        return -1, str(e)


def file_sha256(path: Path) -> str | None:
    """
    Compute SHA-256 hash of a file.

    Why SHA-256?
    - Collision resistant: two different files can't produce the same hash
    - Deterministic: same file always gives same hash
    - If even one byte changes, the hash is completely different

    We read in 64KB chunks so large files don't consume all RAM at once.
    Returns None if the file doesn't exist (expected for some entries).
    """
    if not path.exists():
        return None

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)

    return h.hexdigest()


def resolve_hostname(ip: str) -> str:
    """
    Reverse DNS: turn an IP address back into a readable hostname.
    Makes network logs human-readable instead of just raw IPs.
    Falls back to the raw IP string if lookup fails.
    """
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror):
        return ip


# ─────────────────────────────────────────────────────────────────
# LAYER 1 — FILE INTEGRITY
# ─────────────────────────────────────────────────────────────────

def snapshot_files() -> None:
    """
    Hash every sensitive file and save results to security/file_hashes.json.

    Run this ONCE after setting up Matter (when all files are known-clean).
    Every future run of lockdown.py compares against this baseline.
    If you intentionally change a listed file, re-run --snapshot to update.
    """
    HASH_STORE.parent.mkdir(parents=True, exist_ok=True)
    hashes: dict[str, str | None] = {}

    log.info("📸  Creating file integrity snapshot...")
    for path in SENSITIVE_FILES:
        h = file_sha256(path)
        hashes[str(path)] = h
        display = f"SHA256={h[:20]}..." if h else "not found (recorded as absent)"
        log.info(f"    {path.name:30s}  {display}")

    with open(HASH_STORE, "w") as f:
        json.dump(hashes, f, indent=2)

    log.info(f"✅  Snapshot saved → {HASH_STORE.relative_to(MATTER_ROOT)}")


def verify_integrity() -> bool:
    """
    Compare current file hashes against the saved snapshot.
    Returns True if everything matches, False if anything has changed.

    Why? If malware or someone with access modifies config.py or auth.py
    between runs, this catches it before Matter ever starts.
    """
    if not HASH_STORE.exists():
        log.warning("⚠️  No snapshot found. Run: python lockdown.py --snapshot")
        return True  # Can't verify yet — don't block startup, but warn

    with open(HASH_STORE) as f:
        stored: dict[str, str | None] = json.load(f)

    log.info("🔍  Verifying file integrity...")
    all_clean = True

    for path_str, expected in stored.items():
        path = Path(path_str)
        current = file_sha256(path)

        if current is None and expected is None:
            log.info(f"    {path.name:30s}  ⏭️  absent (expected)")
        elif current != expected:
            log.error(
                f"    {path.name:30s}  🚨  TAMPERED or MODIFIED\n"
                f"         Stored  : {expected}\n"
                f"         Current : {current}"
            )
            all_clean = False
        else:
            log.info(f"    {path.name:30s}  ✅  clean")

    return all_clean


# ─────────────────────────────────────────────────────────────────
# LAYER 2 — NETWORK CONNECTION MONITOR
# ─────────────────────────────────────────────────────────────────

def get_established_connections() -> list[dict]:
    """
    Get all currently ESTABLISHED TCP connections via netstat.

    netstat -ano output format:
        TCP  192.168.1.5:49201  142.250.80.46:443  ESTABLISHED  4512
              ↑ local addr       ↑ remote addr        ↑ state    ↑ PID

    We only care about ESTABLISHED (active data flow), not LISTENING or CLOSE_WAIT.
    rsplit(":", 1) splits from the RIGHT once — handles IPv6 addresses correctly
    since they contain multiple colons (e.g. [::1]:443).
    """
    code, output = run_cmd(["netstat", "-ano"])
    if code != 0:
        return []

    connections = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) == 5 and parts[0] == "TCP" and parts[3] == "ESTABLISHED":
            remote_raw = parts[2]
            # Strip IPv6 brackets if present, then split off the port
            remote_ip = remote_raw.rsplit(":", 1)[0].strip("[]")
            connections.append({
                "local":      parts[1],
                "remote_raw": remote_raw,
                "remote_ip":  remote_ip,
                "pid":        parts[4],
            })

    return connections


def is_ip_allowed(ip: str) -> bool:
    """
    Check whether a remote IP is on our whitelist.
    We resolve each allowed hostname to its current IP and compare.

    We also allow loopback (127.x) and private LAN ranges (192.168.x, 10.x)
    since those are local and not going out to the internet.
    """
    # Local / private ranges are always fine
    if (
        ip.startswith("127.")
        or ip.startswith("192.168.")
        or ip.startswith("10.")
        or ip == "::1"
    ):
        return True

    # Check against whitelisted hostnames
    for host in ALLOWED_OUTBOUND_HOSTS:
        try:
            if socket.gethostbyname(host) == ip:
                return True
        except socket.gaierror:
            pass

    return False


def scan_network_once() -> list[dict]:
    """
    One-pass network scan. Returns a list of suspicious connections.
    Attaches a hostname to each suspicious entry for readable logs.
    """
    suspicious = []
    for conn in get_established_connections():
        if not is_ip_allowed(conn["remote_ip"]):
            conn["hostname"] = resolve_hostname(conn["remote_ip"])
            suspicious.append(conn)
    return suspicious


def monitor_network_loop() -> None:
    """
    Background thread: continuously scan every NETWORK_SCAN_INTERVAL seconds.
    Logs suspicious connections as warnings.
    """
    log.info(f"👁️  Live network monitor active (interval: {NETWORK_SCAN_INTERVAL}s)")
    while True:
        suspicious = scan_network_once()
        if suspicious:
            for conn in suspicious:
                log.warning(
                    f"🚨  UNEXPECTED CONNECTION → "
                    f"{conn['remote_ip']} ({conn.get('hostname', '?')})  "
                    f"PID {conn['pid']}"
                )
        else:
            log.info("    Network ✅  all connections whitelisted")
        time.sleep(NETWORK_SCAN_INTERVAL)


# ─────────────────────────────────────────────────────────────────
# LAYER 3 — SUSPICIOUS PROCESS DETECTION
# ─────────────────────────────────────────────────────────────────

def check_processes() -> bool:
    """
    Scan the running process list for known packet sniffers / debuggers.

    Why? If Wireshark is open while Matter runs, someone could be capturing
    your Gemini API key or ElevenLabs key from the outbound HTTPS traffic
    before it gets encrypted (at the app layer, before TLS kicks in).

    tasklist /fo csv /nh → CSV output with no header, easy to parse.
    """
    log.info("🔎  Scanning running processes...")

    if not is_windows():
        log.info("    ⏭️  Process scan skipped (Windows only)")
        return True

    code, output = run_cmd(["tasklist", "/fo", "csv", "/nh"])
    if code != 0:
        log.warning("    ⚠️  Could not run tasklist")
        return True

    output_lower = output.lower()
    found = [p for p in SUSPICIOUS_PROCESSES if p.lower() in output_lower]

    if found:
        for p in found:
            log.warning(f"    ⚠️  Suspicious process running: {p}")
        return False

    log.info("    Processes ✅  no suspicious tools detected")
    return True


# ─────────────────────────────────────────────────────────────────
# LAYER 4 — .ENV EXPOSURE CHECK
# ─────────────────────────────────────────────────────────────────

def check_env_exposure() -> bool:
    """
    Two checks:
    1. Is .env listed in .gitignore? If not, a `git push` could expose your API keys.
    2. Does .env exist and have content? An empty .env means keys may have been lost.
    """
    log.info("🔑  Checking .env exposure...")
    clean = True

    gitignore = MATTER_ROOT / ".gitignore"
    env_file  = MATTER_ROOT / ".env"

    if gitignore.exists():
        content = gitignore.read_text(encoding="utf-8", errors="ignore")
        if ".env" in content:
            log.info("    .gitignore ✅  .env is listed")
        else:
            log.warning("    ⚠️  .env is NOT in .gitignore — git push would expose your keys!")
            clean = False
    else:
        log.warning("    ⚠️  No .gitignore found — create one and add .env to it immediately")
        clean = False

    if env_file.exists():
        size = env_file.stat().st_size
        if size == 0:
            log.warning("    ⚠️  .env is empty — did you lose your API keys?")
            clean = False
        else:
            log.info(f"    .env ✅  present ({size} bytes)")
    else:
        log.info("    .env ⏭️  not present (likely using .env.encrypted — that's fine)")

    return clean


# ─────────────────────────────────────────────────────────────────
# FULL CHECK — runs all layers in sequence
# ─────────────────────────────────────────────────────────────────

def run_full_check() -> bool:
    log.info("=" * 62)
    log.info("  MATTER LOCKDOWN — FULL SECURITY CHECK")
    log.info(f"  {datetime.datetime.now().strftime('%A, %d %B %Y  %H:%M:%S')}")
    log.info("=" * 62)

    results = {
        "File Integrity": verify_integrity(),
        "Processes":      check_processes(),
        "Env Exposure":   check_env_exposure(),
    }

    log.info("🌐  Running one-pass network scan...")
    suspicious = scan_network_once()
    results["Network"] = len(suspicious) == 0
    if suspicious:
        for c in suspicious:
            log.warning(f"    🚨  {c['remote_ip']} ({c.get('hostname','?')})  PID {c['pid']}")
    else:
        log.info("    Network ✅  clean")

    log.info("")
    log.info("─" * 62)
    log.info("  RESULTS")
    log.info("─" * 62)

    all_clear = True
    for name, passed in results.items():
        icon = "✅" if passed else "🚨"
        status = "PASSED" if passed else "FAILED"
        log.info(f"  {icon}  {name:20s}  {status}")
        if not passed:
            all_clear = False

    log.info("")
    if all_clear:
        log.info("  ✅  ALL CLEAR — safe to start Matter.")
    else:
        log.error("  🚨  ISSUES DETECTED — check warnings above.")

    log.info("=" * 62)
    return all_clear


# ─────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Matter Lockdown Security Suite")
    parser.add_argument("--snapshot", action="store_true", help="Create file hash baseline (run once)")
    parser.add_argument("--monitor",  action="store_true", help="Full check + continuous network monitor")
    parser.add_argument("--status",   action="store_true", help="Quick full status check")
    parser.add_argument("--clean",    action="store_true", help="Remove generated security files")
    args = parser.parse_args()

    if args.snapshot:
        snapshot_files()

    elif args.monitor:
        run_full_check()
        t = threading.Thread(target=monitor_network_loop, daemon=True)
        t.start()
        log.info("Monitoring... press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            log.info("Monitor stopped.")

    elif args.clean:
        for f in [HASH_STORE]:
            if f.exists():
                f.unlink()
                log.info(f"🗑️  Removed {f.name}")
        log.info("✅  Reset complete.")

    else:
        # Default and --status both run the full check
        run_full_check()


if __name__ == "__main__":
    main()