# Build a local Windows executable with PyInstaller. No network at runtime.
# Usage: powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1
$ErrorActionPreference = "Stop"
py -m pip install --upgrade pip
py -m pip install --editable ".[build]"
py -m PyInstaller --noconfirm --clean --onefile --name companion --paths src src/companion/cli.py
Write-Output "dist\companion.exe ready. Run: .\dist\companion.exe doctor"
