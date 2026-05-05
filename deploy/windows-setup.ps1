<#
.SYNOPSIS
    PiCar-X Windows host setup — adds picarx.local to the hosts file so the
    dashboard is reachable at https://picarx.local:8080/ from this PC.

.DESCRIPTION
    * Removes any commented-out picarx.local entry.
    * Adds or updates the active entry: 192.168.2.249  picarx.local
    * Self-elevates to Administrator if not already running elevated.
    * Safe to run multiple times (idempotent).

.PARAMETER PiIp
    IP address of the Raspberry Pi.  Default: 192.168.2.249

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File deploy\windows-setup.ps1
    powershell -ExecutionPolicy Bypass -File deploy\windows-setup.ps1 -PiIp 192.168.2.100
#>
param(
    [string]$PiIp = "192.168.2.249"
)

# ── Self-elevation ────────────────────────────────────────────────────────────
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "Requesting administrator privileges..." -ForegroundColor Yellow
    $elevateArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`" -PiIp $PiIp"
    Start-Process powershell -Verb RunAs -ArgumentList $elevateArgs -Wait
    exit
}

# ── Hosts file update ─────────────────────────────────────────────────────────
$hostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
$hostname  = "picarx.local"
$newEntry  = "$PiIp`t$hostname"

$lines = Get-Content $hostsPath -Raw

# Remove any existing lines (commented or active) that reference picarx.local
$cleaned = ($lines -split "`r?`n" | Where-Object {
    $_ -notmatch "\bpicarx\.local\b"
}) -join "`n"

# Append the active entry
$updated = $cleaned.TrimEnd() + "`n$newEntry`n"
Set-Content -Path $hostsPath -Value $updated -Encoding ASCII -NoNewline

Write-Host "" 
Write-Host "OK  Hosts file updated:" -ForegroundColor Green
Write-Host "    $newEntry" -ForegroundColor Cyan
Write-Host ""
Write-Host "You can now open:  https://picarx.local:8080/" -ForegroundColor Green
Write-Host "(Accept the self-signed certificate warning in your browser.)"
Write-Host ""

# Flush the DNS cache so the new entry takes effect immediately
try {
    ipconfig /flushdns | Out-Null
    Write-Host "DNS cache flushed." -ForegroundColor DarkGray
} catch {}

Read-Host "Press Enter to close"
