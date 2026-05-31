# Build CyberMirror.exe — run once, then double-click the exe in project root.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $PSScriptRoot

Write-Host "Installing PyInstaller if needed…"
python -m pip install pyinstaller --quiet

Write-Host "Building CyberMirror.exe…"
python -m PyInstaller `
  --onefile `
  --console `
  --name CyberMirror `
  --distpath "$Root" `
  --workpath "$PSScriptRoot\build" `
  --specpath "$PSScriptRoot" `
  --clean `
  cybermirror_launcher.py

if (Test-Path "$Root\CyberMirror.exe") {
  Write-Host ""
  Write-Host "Done! Double-click: $Root\CyberMirror.exe"
} else {
  Write-Host "Build failed." -ForegroundColor Red
  exit 1
}
