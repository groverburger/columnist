$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$venv = ".build-venv"

if (!(Test-Path $venv)) {
    Write-Host "Creating build virtual environment..."
    py -3 -m venv $venv
}

& "$venv\Scripts\Activate.ps1"

Write-Host "Installing dependencies..."
python -m pip install --quiet --upgrade pip
python -m pip install --quiet pyinstaller yfinance pywebview

Write-Host "Building Columnist..."
python -m PyInstaller -y "Columnist.spec"

Write-Host ""
Write-Host "Build complete: dist\Columnist\Columnist.exe"
