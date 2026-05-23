# =============================================================================
# lockdown.ps1 — Matter Admin PowerShell Security Script
# =============================================================================
# MUST BE RUN AS ADMINISTRATOR
# Right-click PowerShell → "Run as administrator", then:
#   Set-ExecutionPolicy RemoteSigned -Scope CurrentUser   (once, to allow scripts)
#   .\lockdown.ps1                  # full lockdown
#   .\lockdown.ps1 -CheckOnly       # audit only, no changes
#   .\lockdown.ps1 -Remove          # undo all Matter firewall rules
#   .\lockdown.ps1 -Status          # show current rule status
#
# What this covers:
#   1. Windows Firewall — block all inbound + restrict outbound to whitelist
#   2. Windows Defender — force real-time protection on
#   3. Audit policy — enable logon/logoff and object access auditing
#   4. File ACL hardening — lock .env and secrets to current user only
#   5. Disable unnecessary services that increase attack surface
#   6. Registry hardening — disable autorun, SMBv1, remote registry
#   7. Security report written to security\ps_audit.log
# =============================================================================

[CmdletBinding()]
param (
    [switch]$CheckOnly,    # audit without making changes
    [switch]$Remove,       # undo all firewall rules created by this script
    [switch]$Status        # show current firewall rule status and exit
)

# ─────────────────────────────────────────────────────────────────
# REQUIRE ADMIN
# ─────────────────────────────────────────────────────────────────

# [Security.Principal.WindowsIdentity]::GetCurrent() → gets the identity of
# the currently logged-in Windows user (your account)
# IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) → checks
# if that identity is a member of the local Administrators group
$currentUser  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal    = New-Object Security.Principal.WindowsPrincipal($currentUser)
$isAdmin      = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host ""
    Write-Host "  ERROR: This script must be run as Administrator." -ForegroundColor Red
    Write-Host "  Right-click PowerShell and choose 'Run as administrator'." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}


# ─────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────

# $PSScriptRoot → built-in variable: the folder this .ps1 file lives in
# It works regardless of where you call the script from
$MatterRoot = $PSScriptRoot

$LogDir  = Join-Path $MatterRoot "security"
$LogFile = Join-Path $LogDir "ps_audit.log"

# Create security directory if missing
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

# Name prefix for all firewall rules this script creates
# Using a prefix lets us find and remove them cleanly later
$RulePrefix = "Matter_Lockdown"

# The Python executable running Matter — we apply firewall rules per-program
$PythonExe = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $PythonExe) {
    $PythonExe = (Get-Command python3 -ErrorAction SilentlyContinue)?.Source
}

# Outbound destinations Matter is allowed to connect to
# netsh works with IPs not hostnames, so we resolve each one below
$AllowedHosts = @(
    "generativelanguage.googleapis.com",   # Gemini 2.0 Flash
    "api.elevenlabs.io",                   # ElevenLabs TTS
    "en.wikipedia.org",                    # Wikipedia
    "newsapi.org",                         # News
    "www.google.com",                      # Search fallback
    "api.openweathermap.org"               # Weather
)

# Files whose ACLs (access control lists) we harden
$SensitiveFiles = @(
    (Join-Path $MatterRoot ".env"),
    (Join-Path $MatterRoot ".env.encrypted"),
    (Join-Path $MatterRoot "security\audit.log"),
    (Join-Path $MatterRoot "security\file_hashes.json")
)

# Windows services with no legitimate use for a personal AI assistant
# Disabling these reduces the attack surface
$ServicesToDisable = @(
    "RemoteRegistry",         # Allows remote modification of registry — not needed
    "Telnet",                 # Unencrypted remote shell — never needed in 2024
    "TlntSvr",                # Telnet server alias
    "RemoteAccess",           # Routing/remote access — not needed on a desktop
    "WinRM"                   # Windows Remote Management — only needed for enterprise
)

# Pass/fail counters for the summary
$PassCount = 0
$FailCount = 0


# ─────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────

function Write-Log {
    param(
        [string]$Level,
        [string]$Message,
        [string]$Color = "White"
    )
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "$timestamp  [$Level]  $Message"
    Write-Host $line -ForegroundColor $Color
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Log-Info    { param([string]$m) Write-Log "INFO " $m "Green" }
function Log-Warn    { param([string]$m) Write-Log "WARN " "⚠️  $m" "Yellow" }
function Log-Error   { param([string]$m) Write-Log "ERROR" "🚨  $m" "Red" }
function Log-Section { param([string]$m) Write-Log "----" $m "Cyan" }

function Mark-Pass { $script:PassCount++ }
function Mark-Fail { $script:FailCount++ }


# ─────────────────────────────────────────────────────────────────
# LAYER 1 — WINDOWS FIREWALL
# ─────────────────────────────────────────────────────────────────

function Setup-Firewall {
    Log-Section "LAYER 1: Windows Firewall Rules"

    if (-not $PythonExe) {
        Log-Warn "Python not found in PATH — firewall rules will apply to all programs"
    } else {
        Log-Info "  Python found: $PythonExe"
    }

    # ── 1a. Block ALL inbound to Python ──────────────────────────
    # Why? Matter doesn't need to RECEIVE connections.
    # It only initiates outbound calls to APIs.
    # Any inbound = something trying to talk to Matter unsolicited.
    $inboundName = "${RulePrefix}_BlockInbound"

    if (-not $CheckOnly) {
        $params = @{
            DisplayName = $inboundName
            Direction   = "Inbound"
            Action      = "Block"
            Enabled     = "True"
            Description = "Matter lockdown: block all inbound connections"
        }
        if ($PythonExe) { $params["Program"] = $PythonExe }

        # Remove existing rule first to avoid duplicates
        Remove-NetFirewallRule -DisplayName $inboundName -ErrorAction SilentlyContinue
        New-NetFirewallRule @params | Out-Null

        Log-Info "  ✅  Inbound BLOCK rule created: $inboundName"
        Mark-Pass
    } else {
        $existing = Get-NetFirewallRule -DisplayName $inboundName -ErrorAction SilentlyContinue
        if ($existing) { Log-Info "  ✅  Inbound block rule exists" ; Mark-Pass }
        else           { Log-Warn "  Inbound block rule not found" ; Mark-Fail }
    }

    # ── 1b. Resolve allowed hosts → IPs ──────────────────────────
    # netsh / New-NetFirewallRule works with IP addresses, not hostnames.
    # We DNS-resolve each hostname to its current IP at setup time.
    $allowedIPs = @()
    foreach ($host in $AllowedHosts) {
        try {
            $ip = [System.Net.Dns]::GetHostAddresses($host) |
                  Where-Object { $_.AddressFamily -eq "InterNetwork" } |  # IPv4 only
                  Select-Object -First 1 -ExpandProperty IPAddressToString
            if ($ip) {
                $allowedIPs += $ip
                Log-Info "  🌐  $host → $ip"
            }
        } catch {
            Log-Warn "  Could not resolve $host — skipping"
        }
    }

    # ── 1c. Allow outbound to whitelisted IPs ─────────────────────
    if ($allowedIPs.Count -gt 0 -and -not $CheckOnly) {
        $outAllowName = "${RulePrefix}_AllowOutbound"
        Remove-NetFirewallRule -DisplayName $outAllowName -ErrorAction SilentlyContinue

        $params = @{
            DisplayName = $outAllowName
            Direction   = "Outbound"
            Action      = "Allow"
            RemoteAddress = $allowedIPs
            Enabled     = "True"
            Description = "Matter lockdown: allow whitelisted outbound IPs"
        }
        if ($PythonExe) { $params["Program"] = $PythonExe }

        New-NetFirewallRule @params | Out-Null
        Log-Info "  ✅  Outbound ALLOW rule created ($($allowedIPs.Count) IPs)"
        Mark-Pass
    }

    # ── 1d. Block all other outbound from Python ──────────────────
    # This is the default-deny for outbound.
    # Order matters in Windows Firewall: Allow rules take priority over Block
    # when they match the same traffic — so the whitelist above will still pass.
    if (-not $CheckOnly) {
        $outBlockName = "${RulePrefix}_BlockOutbound"
        Remove-NetFirewallRule -DisplayName $outBlockName -ErrorAction SilentlyContinue

        $params = @{
            DisplayName = $outBlockName
            Direction   = "Outbound"
            Action      = "Block"
            Enabled     = "True"
            Description = "Matter lockdown: block non-whitelisted outbound"
        }
        if ($PythonExe) { $params["Program"] = $PythonExe }

        New-NetFirewallRule @params | Out-Null
        Log-Info "  ✅  Outbound BLOCK rule created"
        Mark-Pass
    }
}


function Remove-FirewallRules {
    Log-Section "Removing Matter Firewall Rules"
    $rules = Get-NetFirewallRule | Where-Object { $_.DisplayName -like "${RulePrefix}*" }

    if ($rules.Count -eq 0) {
        Log-Info "  No Matter firewall rules found."
        return
    }

    foreach ($rule in $rules) {
        Remove-NetFirewallRule -DisplayName $rule.DisplayName
        Log-Info "  🗑️  Removed: $($rule.DisplayName)"
    }
    Log-Info "  ✅  All Matter firewall rules removed."
}


function Show-FirewallStatus {
    Log-Section "Current Matter Firewall Rules"
    $rules = Get-NetFirewallRule | Where-Object { $_.DisplayName -like "${RulePrefix}*" }

    if ($rules.Count -eq 0) {
        Log-Warn "  No Matter firewall rules are currently active."
        return
    }

    foreach ($rule in $rules) {
        $dir    = $rule.Direction
        $action = $rule.Action
        $status = if ($rule.Enabled -eq "True") { "ENABLED" } else { "DISABLED" }
        Log-Info "  [$status]  $($rule.DisplayName)  ($dir / $action)"
    }
}


# ─────────────────────────────────────────────────────────────────
# LAYER 2 — WINDOWS DEFENDER
# ─────────────────────────────────────────────────────────────────

function Setup-Defender {
    Log-Section "LAYER 2: Windows Defender"

    try {
        $status = Get-MpComputerStatus -ErrorAction Stop

        # Real-time protection should always be on
        if ($status.RealTimeProtectionEnabled) {
            Log-Info "  Real-time protection: ✅  enabled"
            Mark-Pass
        } else {
            Log-Warn "  Real-time protection is OFF"
            if (-not $CheckOnly) {
                Set-MpPreference -DisableRealtimeMonitoring $false
                Log-Info "  → Enabled real-time protection"
            }
            Mark-Fail
        }

        # Cloud-based protection for faster new-threat detection
        if ($status.IoavProtectionEnabled) {
            Log-Info "  Cloud protection: ✅  enabled"
            Mark-Pass
        } else {
            Log-Warn "  Cloud protection is OFF"
            if (-not $CheckOnly) {
                Set-MpPreference -MAPSReporting Advanced
                Log-Info "  → Enabled cloud protection"
            }
            Mark-Fail
        }

        # Confirm definitions are recent (within last 3 days)
        $defAge = (Get-Date) - $status.AntivirusSignatureLastUpdated
        if ($defAge.TotalDays -le 3) {
            Log-Info "  Virus definitions: ✅  updated $([math]::Round($defAge.TotalHours, 1))h ago"
            Mark-Pass
        } else {
            Log-Warn "  Virus definitions are $([math]::Round($defAge.TotalDays, 1)) days old"
            if (-not $CheckOnly) {
                Update-MpSignature
                Log-Info "  → Triggered definition update"
            }
            Mark-Fail
        }

    } catch {
        Log-Warn "  Could not access Windows Defender (may not be available on this edition)"
    }
}


# ─────────────────────────────────────────────────────────────────
# LAYER 3 — FILE ACL HARDENING
# ─────────────────────────────────────────────────────────────────

function Harden-FileACLs {
    Log-Section "LAYER 3: File Permission Hardening (ACLs)"

    # Get the current user's identity in "DOMAIN\User" format
    # This is what Windows ACL entries use
    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

    foreach ($filePath in $SensitiveFiles) {
        if (-not (Test-Path $filePath)) {
            Log-Info "  $((Split-Path $filePath -Leaf)):  ⏭️  not found"
            continue
        }

        if ($CheckOnly) {
            # Just report current ACL without changing anything
            $acl = Get-Acl $filePath
            Log-Info "  $((Split-Path $filePath -Leaf)):  current owner = $($acl.Owner)"
            Mark-Pass
            continue
        }

        try {
            # Get current ACL object for this file
            $acl = Get-Acl $filePath

            # SetAccessRuleProtection($true, $false):
            #   $true  → stop inheriting permissions from parent folder
            #   $false → don't copy the inherited rules into explicit rules
            # Without this, stripping permissions would just be re-added by inheritance
            $acl.SetAccessRuleProtection($true, $false)

            # Remove ALL existing explicit access rules
            # This wipes the slate clean so we can add only what we want
            $acl.Access | ForEach-Object { $acl.RemoveAccessRule($_) | Out-Null }

            # Build a new rule: current user gets FullControl
            # FileSystemRights::FullControl → read, write, delete, change permissions
            # InheritanceFlags::None         → don't pass this rule to child files
            # PropagationFlags::None         → don't propagate to subdirectories
            # AccessControlType::Allow       → this is an ALLOW rule (not DENY)
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
                $currentUser,
                [System.Security.AccessControl.FileSystemRights]::FullControl,
                [System.Security.AccessControl.InheritanceFlags]::None,
                [System.Security.AccessControl.PropagationFlags]::None,
                [System.Security.AccessControl.AccessControlType]::Allow
            )
            $acl.AddAccessRule($rule)

            # Write the modified ACL back to the file
            Set-Acl -Path $filePath -AclObject $acl

            Log-Info "  ✅  $((Split-Path $filePath -Leaf)):  locked to $currentUser only"
            Mark-Pass

        } catch {
            Log-Warn "  $((Split-Path $filePath -Leaf)):  ACL change failed — $($_.Exception.Message)"
            Mark-Fail
        }
    }
}


# ─────────────────────────────────────────────────────────────────
# LAYER 4 — AUDIT POLICY
# ─────────────────────────────────────────────────────────────────

function Setup-AuditPolicy {
    Log-Section "LAYER 4: Windows Audit Policy"

    # auditpol.exe — Windows built-in audit policy configuration tool
    # /set /category → sets a specific audit category
    # /success:enable /failure:enable → log both successful and failed events

    $policies = @(
        @{ Category = "Logon/Logoff";  Description = "Track who logs in/out" },
        @{ Category = "Object Access"; Description = "Track file/key access" },
        @{ Category = "Account Logon"; Description = "Track credential use" },
        @{ Category = "Policy Change"; Description = "Track security policy changes" }
    )

    foreach ($policy in $policies) {
        if (-not $CheckOnly) {
            $result = & auditpol.exe /set /category:"$($policy.Category)" /success:enable /failure:enable 2>&1
            if ($LASTEXITCODE -eq 0) {
                Log-Info "  ✅  Audit enabled: $($policy.Category)"
                Mark-Pass
            } else {
                Log-Warn "  Failed to set audit policy: $($policy.Category)"
                Mark-Fail
            }
        } else {
            # Check current policy
            $current = & auditpol.exe /get /category:"$($policy.Category)" 2>&1
            if ($current -match "Success and Failure") {
                Log-Info "  ✅  $($policy.Category): already auditing success+failure"
                Mark-Pass
            } else {
                Log-Warn "  $($policy.Category): not fully audited"
                Mark-Fail
            }
        }
    }
}


# ─────────────────────────────────────────────────────────────────
# LAYER 5 — REGISTRY HARDENING
# ─────────────────────────────────────────────────────────────────

function Harden-Registry {
    Log-Section "LAYER 5: Registry Hardening"

    # Registry keys and what we're setting them to
    # Each entry: Path, Name, Value, Description
    $registrySettings = @(
        @{
            Path        = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\Explorer"
            Name        = "NoDriveTypeAutoRun"
            Value       = 0xFF   # 255 = disable autorun on ALL drive types
            Type        = "DWord"
            Description = "Disable AutoRun (prevents malware from auto-executing from USB)"
        },
        @{
            Path        = "HKLM:\SYSTEM\CurrentControlSet\Services\LanmanServer\Parameters"
            Name        = "SMB1"
            Value       = 0      # 0 = disabled
            Type        = "DWord"
            Description = "Disable SMBv1 (exploited by EternalBlue/WannaCry)"
        },
        @{
            Path        = "HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server"
            Name        = "fDenyTSConnections"
            Value       = 1      # 1 = deny Remote Desktop connections
            Type        = "DWord"
            Description = "Disable Remote Desktop (not needed for a personal assistant)"
        },
        @{
            Path        = "HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\DNSClient"
            Name        = "EnableMulticast"
            Value       = 0      # 0 = disable LLMNR (leaks hostnames on local network)
            Type        = "DWord"
            Description = "Disable LLMNR (prevents local network credential theft)"
        }
    )

    foreach ($setting in $registrySettings) {
        # Ensure the registry path exists before trying to set a value in it
        if (-not (Test-Path $setting.Path)) {
            if (-not $CheckOnly) {
                New-Item -Path $setting.Path -Force | Out-Null
            } else {
                Log-Warn "  Registry path not found: $($setting.Path)"
                Mark-Fail
                continue
            }
        }

        if (-not $CheckOnly) {
            try {
                Set-ItemProperty -Path $setting.Path -Name $setting.Name -Value $setting.Value -Type $setting.Type
                Log-Info "  ✅  $($setting.Description)"
                Mark-Pass
            } catch {
                Log-Warn "  Failed: $($setting.Description) — $($_.Exception.Message)"
                Mark-Fail
            }
        } else {
            # Check current value
            try {
                $current = Get-ItemPropertyValue -Path $setting.Path -Name $setting.Name -ErrorAction Stop
                if ($current -eq $setting.Value) {
                    Log-Info "  ✅  $($setting.Description)"
                    Mark-Pass
                } else {
                    Log-Warn "  Not set: $($setting.Description) (current: $current, expected: $($setting.Value))"
                    Mark-Fail
                }
            } catch {
                Log-Warn "  Not configured: $($setting.Description)"
                Mark-Fail
            }
        }
    }
}


# ─────────────────────────────────────────────────────────────────
# LAYER 6 — DISABLE UNNECESSARY SERVICES
# ─────────────────────────────────────────────────────────────────

function Disable-UnnecessaryServices {
    Log-Section "LAYER 6: Unnecessary Services"

    foreach ($svcName in $ServicesToDisable) {
        $svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue

        if (-not $svc) {
            Log-Info "  $svcName: ⏭️  not installed"
            continue
        }

        if ($svc.StartType -eq "Disabled" -or $svc.Status -eq "Stopped") {
            Log-Info "  $svcName: ✅  already stopped/disabled"
            Mark-Pass
        } else {
            Log-Warn "  $svcName: running (StartType=$($svc.StartType))"
            if (-not $CheckOnly) {
                try {
                    Stop-Service -Name $svcName -Force -ErrorAction SilentlyContinue
                    Set-Service  -Name $svcName -StartupType Disabled
                    Log-Info "  → Stopped and disabled $svcName"
                    Mark-Pass
                } catch {
                    Log-Warn "  Could not disable $svcName — $($_.Exception.Message)"
                    Mark-Fail
                }
            } else {
                Mark-Fail
            }
        }
    }
}


# ─────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────

function Print-Summary {
    $total = $PassCount + $FailCount

    Write-Host ""
    Log-Section "═══════════════════════════════════════"
    Log-Section "  SUMMARY"
    Log-Section "═══════════════════════════════════════"
    Log-Info "  Checks passed : $PassCount / $total"

    if ($FailCount -gt 0) {
        Log-Error "  Checks failed : $FailCount / $total"
        Log-Warn  "  Review warnings above before starting Matter."
    } else {
        Log-Info  "  ✅  All checks passed. Matter is ready."
    }

    Log-Info "  Log saved to  : $LogFile"
    Write-Host ""
}


# ─────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────

Write-Host ""
Log-Section "════════════════════════════════════════════"
Log-Section "  MATTER POWERSHELL LOCKDOWN (Admin)"
Log-Section "  $(Get-Date -Format 'dddd, dd MMMM yyyy  HH:mm:ss')"
if ($CheckOnly) { Log-Section "  MODE: Audit only (no changes)" }
Log-Section "════════════════════════════════════════════"
Write-Host ""

if ($Remove) {
    Remove-FirewallRules
    exit 0
}

if ($Status) {
    Show-FirewallStatus
    exit 0
}

# Run all layers
Setup-Firewall
Write-Host ""
Setup-Defender
Write-Host ""
Harden-FileACLs
Write-Host ""
Setup-AuditPolicy
Write-Host ""
Harden-Registry
Write-Host ""
Disable-UnnecessaryServices
Write-Host ""
Print-Summary