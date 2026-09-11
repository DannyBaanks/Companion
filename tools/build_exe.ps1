# Build local Windows executables with PyInstaller. No network is used at runtime.
# Usage: powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1 [-Target all|cli|hub]
param(
    [ValidateSet("all", "cli", "hub")]
    [string]$Target = "all"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    if ($Target -in @("all", "cli", "hub")) {
        py -m PyInstaller --noconfirm --clean --onefile --name companion --paths src --add-data "packs;packs" src/companion_cli.py
        Write-Output "dist\companion.exe ready. Run: .\dist\companion.exe doctor"
    }
    if ($Target -in @("all", "hub")) {
        py -m PyInstaller --noconfirm --clean --onefile --windowed --name "Companion Hub" --paths src --add-data "packs;packs" src/companion_hub.py
        Write-Output "dist\Companion Hub.exe ready. Run: .\dist\Companion Hub.exe"
    }
}
finally {
    Pop-Location
}
