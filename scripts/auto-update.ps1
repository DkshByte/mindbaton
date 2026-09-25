# Mindbaton on Docker (Windows): get the newest release, and go back to the one you had if it doesn't come up healthy.
# Your memories live in the mindbaton-data volume and are never touched. In PowerShell, in the folder with compose.yaml:
#
#   powershell -ExecutionPolicy Bypass -File scripts\auto-update.ps1            update now
#   powershell -ExecutionPolicy Bypass -File scripts\auto-update.ps1 -Install   also every night at 04:00 (Task Scheduler)
#   powershell -ExecutionPolicy Bypass -File scripts\auto-update.ps1 -Remove    stop the nightly update
#
# Linux, macOS, NAS: scripts/auto-update.sh does the same with cron.
param([switch]$Install, [switch]$Remove)
$ErrorActionPreference = 'Continue'   # docker writes progress to stderr; results are checked through $LASTEXITCODE
Set-Location (Split-Path -Parent $PSScriptRoot)
$img = if ($env:MINDBATON_IMAGE) { $env:MINDBATON_IMAGE } else { 'ghcr.io/dkshbyte/mindbaton:latest' }
$task = 'Mindbaton nightly update'
function Log($msg) { $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"; Write-Host $line; Add-Content -Path 'auto-update.log' -Value $line }
function Running { (docker compose ps -q mindbaton | Select-Object -First 1) }

if ($Install) {
  $action = New-ScheduledTaskAction -Execute 'powershell.exe' -WorkingDirectory (Get-Location).Path `
    -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`""
  $when = New-ScheduledTaskTrigger -Daily -At '04:00'
  $opts = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30)  # a missed night runs at the next start
  Register-ScheduledTask -TaskName $task -Action $action -Trigger $when -Settings $opts -Force | Out-Null
  Write-Host "Mindbaton will update itself every night at 04:00 (Task Scheduler: '$task'). Log: $((Get-Location).Path)\auto-update.log"
  exit 0
}
if ($Remove) {
  Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host 'Nightly updates are off.'
  exit 0
}

$cid = Running
if (-not $cid) { Log "Mindbaton isn't running in this folder: start it with docker compose up -d"; exit 1 }
$old = docker inspect -f '{{.Image}}' $cid
docker compose pull -q mindbaton
if ($LASTEXITCODE -ne 0) { Log "couldn't download the new version (offline?); nothing changed"; exit 1 }
$new = docker image inspect -f '{{.Id}}' $img
if ($old -eq $new) { Log 'already up to date'; exit 0 }
$skip = if (Test-Path '.auto-update-skip') { (Get-Content '.auto-update-skip' -Raw).Trim() } else { '' }
if ($new -eq $skip) {  # this release failed here before: wait for a newer one
  docker tag $old $img; Log 'skipping the release that failed its health check last time; waiting for a newer one'; exit 0
}
docker compose up -d mindbaton
if ($LASTEXITCODE -ne 0) { Log "couldn't start the new version: going back"; docker tag $old $img; docker compose up -d mindbaton; exit 1 }

$state = 'starting'
for ($i = 0; $i -lt 36; $i++) {  # up to 3 minutes: the first health check runs 30 s after start
  $state = docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' (Running)
  if ($state -eq 'healthy') {
    $v = docker image inspect -f '{{index .Config.Labels "org.opencontainers.image.version"}}' $img
    Log "updated to $v"; docker image prune -f | Out-Null; exit 0
  }
  if ($state -eq 'unhealthy') { break }
  Start-Sleep -Seconds 5
}
Log "the new version didn't come up healthy ($state): going back to the one you had (and skipping that release)"
Set-Content -Path '.auto-update-skip' -Value $new
docker tag $old $img
docker compose up -d mindbaton
exit 1
