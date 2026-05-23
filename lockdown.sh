#!/usr/bin/env bash
# =============================================================================
# lockdown.sh — Matter Bash Security Script
# =============================================================================
# What this does:
#   1. Hardens file permissions on all sensitive Matter files
#   2. Checks for exposed secrets in the codebase (git grep + regex scan)
#   3. Scans for suspicious background processes
#   4. Checks open network ports and flags unexpected listeners
#   5. Verifies .gitignore is protecting secrets
#   6. Optionally sets up UFW firewall rules (Linux only)
#   7. Writes a timestamped security report to security/bash_audit.log
#
# Usage (inside WSL, or on Linux):
#   chmod +x lockdown.sh
#   ./lockdown.sh              # full hardening run
#   ./lockdown.sh --check      # read-only audit (no changes made)
#   ./lockdown.sh --firewall   # also configure UFW firewall rules
#   ./lockdown.sh --reset      # undo permission changes (development mode)
#
# Designed to run inside WSL2 (Ubuntu) alongside the Windows scripts.
# =============================================================================

set -euo pipefail
# set -e  → exit immediately if any command returns non-zero
# set -u  → treat unset variables as errors (catches typos like $MATER_ROOT)
# set -o pipefail → if any command in a pipe fails, the whole pipe fails
#                   without this, `broken_cmd | grep foo` would silently succeed


# ─────────────────────────────────────────────────────────────────
# COLOUR CODES — makes the output readable at a glance
# ─────────────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'


# ─────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────

# Resolve the directory this script lives in, regardless of where you run it from
# $( ... )  → command substitution: runs the command and captures its output
# dirname   → strips the filename, leaving the directory
# realpath  → resolves symlinks and gives the absolute path
MATTER_ROOT="$(realpath "$(dirname "$0")")"

LOG_DIR="${MATTER_ROOT}/security"
LOG_FILE="${LOG_DIR}/bash_audit.log"

# Files that should be owner-readable only (mode 600 = rw-------)
# 600 means: owner can read+write, group can do nothing, others can do nothing
SENSITIVE_FILES=(
    "${MATTER_ROOT}/.env"
    "${MATTER_ROOT}/.env.encrypted"
    "${MATTER_ROOT}/security/audit.log"
    "${MATTER_ROOT}/security/file_hashes.json"
)

# Directories that should be owner-only (mode 700 = rwx------)
SENSITIVE_DIRS=(
    "${MATTER_ROOT}/security"
    "${MATTER_ROOT}/auth"
)

# Regex patterns that indicate a raw API key accidentally left in code
# We scan all .py and .env files for these
SECRET_PATTERNS=(
    'AIza[0-9A-Za-z_-]{35}'           # Google / Gemini API key
    'sk_[a-zA-Z0-9]{32,}'             # ElevenLabs or similar sk_ key
    'AKIA[0-9A-Z]{16}'                # AWS access key
    'ghp_[a-zA-Z0-9]{36}'             # GitHub personal access token
    'xox[baprs]-[0-9A-Za-z]+'        # Slack token
    'Bearer [a-zA-Z0-9._-]{20,}'      # Generic Bearer token
)

# Processes that have no business running alongside a production AI assistant
SUSPICIOUS_PROCS=(
    "wireshark"
    "tcpdump"
    "tshark"
    "mitmproxy"
    "burpsuite"
    "fiddler"
    "strace"
    "ltrace"
)

# Ports Matter legitimately uses
ALLOWED_PORTS=(443 80 8765)


# ─────────────────────────────────────────────────────────────────
# ARG PARSING
# ─────────────────────────────────────────────────────────────────

# Default flags
CHECK_ONLY=false
SETUP_FIREWALL=false
RESET_MODE=false

for arg in "$@"; do
    case "$arg" in
        --check)     CHECK_ONLY=true ;;
        --firewall)  SETUP_FIREWALL=true ;;
        --reset)     RESET_MODE=true ;;
        --help|-h)
            echo "Usage: $0 [--check] [--firewall] [--reset]"
            echo "  --check     Read-only audit, no changes made"
            echo "  --firewall  Also configure UFW rules"
            echo "  --reset     Undo permission hardening (dev mode)"
            exit 0
            ;;
        *)
            echo "Unknown argument: $arg"
            exit 1
            ;;
    esac
done


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

# Create log directory if missing
mkdir -p "${LOG_DIR}"

# log() writes a timestamped line to both the terminal and the log file
# tee -a  → write to stdout AND append to file simultaneously
log() {
    local level="$1"
    local msg="$2"
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    echo -e "${timestamp}  [${level}]  ${msg}" | tee -a "${LOG_FILE}"
}

log_info()    { log "INFO " "${GREEN}${1}${RESET}"; }
log_warn()    { log "WARN " "${YELLOW}⚠️  ${1}${RESET}"; }
log_error()   { log "ERROR" "${RED}🚨  ${1}${RESET}"; }
log_section() { log "----" "${BOLD}${CYAN}${1}${RESET}"; }

# pass/fail counters so we can show a summary at the end
PASS_COUNT=0
FAIL_COUNT=0

mark_pass() { ((PASS_COUNT++)) || true; }
mark_fail() { ((FAIL_COUNT++)) || true; }


# ─────────────────────────────────────────────────────────────────
# LAYER 1 — FILE PERMISSION HARDENING
# ─────────────────────────────────────────────────────────────────

harden_permissions() {
    log_section "LAYER 1: File Permission Hardening"

    if [ "$RESET_MODE" = true ]; then
        log_info "Reset mode: restoring files to 644 / dirs to 755"
        for f in "${SENSITIVE_FILES[@]}"; do
            [ -f "$f" ] && chmod 644 "$f" && log_info "  Restored ${f##*/} → 644"
        done
        for d in "${SENSITIVE_DIRS[@]}"; do
            [ -d "$d" ] && chmod 755 "$d" && log_info "  Restored dir ${d##*/} → 755"
        done
        return
    fi

    # Harden each sensitive file to 600 (owner read/write only)
    for f in "${SENSITIVE_FILES[@]}"; do
        if [ -f "$f" ]; then
            if [ "$CHECK_ONLY" = false ]; then
                chmod 600 "$f"
            fi
            # Check current permissions after potential change
            perms="$(stat -c '%a' "$f" 2>/dev/null || stat -f '%A' "$f" 2>/dev/null)"
            if [ "$perms" = "600" ]; then
                log_info "  ${f##*/}: ✅  mode 600 (owner only)"
                mark_pass
            else
                log_warn "  ${f##*/}: mode is ${perms}, expected 600"
                mark_fail
            fi
        else
            log_info "  ${f##*/}: ⏭️  not found (skipping)"
        fi
    done

    # Harden sensitive directories to 700 (owner rwx only)
    for d in "${SENSITIVE_DIRS[@]}"; do
        if [ -d "$d" ]; then
            if [ "$CHECK_ONLY" = false ]; then
                chmod 700 "$d"
            fi
            perms="$(stat -c '%a' "$d" 2>/dev/null || stat -f '%A' "$d" 2>/dev/null)"
            if [ "$perms" = "700" ]; then
                log_info "  dir ${d##*/}: ✅  mode 700"
                mark_pass
            else
                log_warn "  dir ${d##*/}: mode is ${perms}, expected 700"
                mark_fail
            fi
        fi
    done
}


# ─────────────────────────────────────────────────────────────────
# LAYER 2 — SECRET SCANNING
# ─────────────────────────────────────────────────────────────────

scan_for_secrets() {
    log_section "LAYER 2: Secret / API Key Scan"

    # Find all Python files and .env files to scan
    # -print0 / xargs -0 → null-delimited to handle filenames with spaces
    mapfile -t TARGET_FILES < <(find "${MATTER_ROOT}" \
        -type f \( -name "*.py" -o -name ".env*" \) \
        -not -path "*/\.*" \
        -not -path "*/__pycache__/*" \
        -not -path "*/node_modules/*" \
        2>/dev/null)

    local found_secret=false

    for pattern in "${SECRET_PATTERNS[@]}"; do
        # grep -r with --include vs looping manually — we loop for clarity
        # -E → extended regex
        # -l → only print filename, not the matching line (safer — don't log actual keys)
        # -n → print line number so user knows where to look
        while IFS=: read -r file line_num _; do
            log_error "  Possible key in ${file##*/}:${line_num} (pattern: ${pattern:0:10}...)"
            found_secret=true
            mark_fail
        done < <(grep -EnH "$pattern" "${TARGET_FILES[@]}" 2>/dev/null || true)
    done

    if [ "$found_secret" = false ]; then
        log_info "  Secret scan: ✅  no raw keys found in source files"
        mark_pass
    fi
}


# ─────────────────────────────────────────────────────────────────
# LAYER 3 — .GITIGNORE VERIFICATION
# ─────────────────────────────────────────────────────────────────

check_gitignore() {
    log_section "LAYER 3: .gitignore Verification"

    local gitignore="${MATTER_ROOT}/.gitignore"

    if [ ! -f "$gitignore" ]; then
        log_warn "No .gitignore found — create one immediately!"
        mark_fail
        return
    fi

    # Entries that MUST be in .gitignore
    local required_entries=(".env" ".env.encrypted" "security/" "__pycache__")

    for entry in "${required_entries[@]}"; do
        # grep -qF → quiet, fixed string (not regex)
        if grep -qF "$entry" "$gitignore"; then
            log_info "  .gitignore ✅  contains: ${entry}"
            mark_pass
        else
            log_warn "  .gitignore MISSING: ${entry}"
            mark_fail

            # Auto-add it if not in check-only mode
            if [ "$CHECK_ONLY" = false ]; then
                echo "$entry" >> "$gitignore"
                log_info "    → Added '${entry}' to .gitignore automatically"
            fi
        fi
    done
}


# ─────────────────────────────────────────────────────────────────
# LAYER 4 — PROCESS SCAN
# ─────────────────────────────────────────────────────────────────

check_processes() {
    log_section "LAYER 4: Suspicious Process Scan"

    local found_any=false

    for proc in "${SUSPICIOUS_PROCS[@]}"; do
        # pgrep -x → exact match on process name
        # -i → case insensitive
        # 2>/dev/null → suppress errors (pgrep exits 1 if no match, which is fine)
        if pgrep -xi "$proc" > /dev/null 2>&1; then
            log_warn "  Suspicious process running: ${proc}"
            found_any=true
            mark_fail
        fi
    done

    if [ "$found_any" = false ]; then
        log_info "  Processes: ✅  no suspicious tools detected"
        mark_pass
    fi
}


# ─────────────────────────────────────────────────────────────────
# LAYER 5 — OPEN PORT AUDIT
# ─────────────────────────────────────────────────────────────────

check_open_ports() {
    log_section "LAYER 5: Open Port Audit"

    # ss is the modern replacement for netstat on Linux
    # -tlnp → TCP, listening, numeric (no DNS resolve), show process
    if ! command -v ss &>/dev/null; then
        log_warn "  ss not found — skipping port audit"
        return
    fi

    # Read listening ports into an array
    mapfile -t LISTENING < <(ss -tlnp 2>/dev/null | awk 'NR>1 {print $4}' | grep -oP ':\K[0-9]+$' | sort -un)

    for port in "${LISTENING[@]}"; do
        local allowed=false
        for allowed_port in "${ALLOWED_PORTS[@]}"; do
            if [ "$port" = "$allowed_port" ]; then
                allowed=true
                break
            fi
        done

        if [ "$allowed" = true ]; then
            log_info "  Port ${port}: ✅  whitelisted"
            mark_pass
        else
            log_warn "  Port ${port}: unexpected listener — investigate with: ss -tlnp | grep :${port}"
            mark_fail
        fi
    done

    if [ "${#LISTENING[@]}" -eq 0 ]; then
        log_info "  Ports: ✅  no listening ports detected"
        mark_pass
    fi
}


# ─────────────────────────────────────────────────────────────────
# LAYER 6 — UFW FIREWALL (optional, Linux only)
# ─────────────────────────────────────────────────────────────────

setup_ufw() {
    log_section "LAYER 6: UFW Firewall Configuration"

    if ! command -v ufw &>/dev/null; then
        log_warn "  ufw not installed. Install with: sudo apt install ufw"
        return
    fi

    if [ "$EUID" -ne 0 ]; then
        log_warn "  UFW setup requires root. Re-run with sudo."
        return
    fi

    log_info "  Configuring UFW rules..."

    # Default policy: deny all incoming, allow all outgoing
    ufw default deny incoming  >> /dev/null
    ufw default allow outgoing >> /dev/null
    log_info "  Default: deny inbound, allow outbound ✅"

    # Allow SSH so you don't lock yourself out (if applicable)
    ufw allow ssh >> /dev/null
    log_info "  SSH: allowed ✅"

    # Allow Matter's local pywebview server
    ufw allow 8765/tcp >> /dev/null
    log_info "  Port 8765 (pywebview): allowed ✅"

    # Enable the firewall
    ufw --force enable >> /dev/null
    log_info "  UFW: enabled ✅"

    ufw status verbose | tee -a "${LOG_FILE}"
}


# ─────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────

print_summary() {
    local total=$((PASS_COUNT + FAIL_COUNT))

    echo ""
    log_section "═══════════════ SUMMARY ═══════════════"
    log_info "  Checks passed : ${PASS_COUNT} / ${total}"

    if [ "$FAIL_COUNT" -gt 0 ]; then
        log_error "  Checks failed : ${FAIL_COUNT} / ${total}"
        log_error "  ⚠️  Review warnings above before starting Matter."
    else
        log_info "  ✅  All checks passed. Matter is safe to start."
    fi

    log_info "  Log saved to  : ${LOG_FILE}"
    echo ""
}


# ─────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────

main() {
    echo ""
    log_section "════════════════════════════════════════"
    log_section "  MATTER BASH LOCKDOWN"
    log_section "  $(date '+%A, %d %B %Y  %H:%M:%S')"
    if [ "$CHECK_ONLY" = true ]; then
        log_section "  MODE: Read-only audit (no changes)"
    fi
    log_section "════════════════════════════════════════"
    echo ""

    harden_permissions
    echo ""
    scan_for_secrets
    echo ""
    check_gitignore
    echo ""
    check_processes
    echo ""
    check_open_ports

    if [ "$SETUP_FIREWALL" = true ]; then
        echo ""
        setup_ufw
    fi

    print_summary
}

main "$@"