[CmdletBinding()]
param(
    [switch]$SkipFrontend,
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root

$distribution = Join-Path $root "dist\PBIBrain"
$runningBuild = Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -and ([IO.Path]::GetDirectoryName($_.Path) -eq $distribution)
}
if ($runningBuild) { throw "Close PBIBrain and PBIBrain-Agent before rebuilding the distribution." }

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Description)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "$Description failed with exit code $LASTEXITCODE." }
}

if (-not $SkipFrontend) {
    Push-Location frontend
    Invoke-Checked { npm ci } "npm ci"
    Invoke-Checked { npm run build } "frontend build"
    Pop-Location
}

& (Join-Path $root "scripts\prepare-native-runtime.ps1")
$venv = Join-Path $root ".venv-build"
if (-not (Test-Path -LiteralPath $venv)) { py -3.11 -m venv $venv }
$python = Join-Path $venv "Scripts\python.exe"
Invoke-Checked { & $python -m pip install --disable-pip-version-check --upgrade pip } "pip upgrade"
Invoke-Checked { & $python -m pip install --disable-pip-version-check -r (Join-Path $root "packaging\requirements-build.txt") } "build dependency install"
Invoke-Checked { & $python -m PyInstaller --noconfirm --clean --workpath build\pyinstaller --distpath dist packaging\pbibrain.spec } "PyInstaller"
Invoke-Checked { & $python scripts\check-frozen-desktop.py dist\PBIBrain\PBIBrain-Agent.exe } "Frozen native scan/reopen"

$portable = Join-Path $root "dist\PBIBrain-Portable-x64.zip"
if (Test-Path -LiteralPath $portable) { Remove-Item -LiteralPath $portable -Force }
Compress-Archive -LiteralPath (Join-Path $root "dist\PBIBrain") -DestinationPath $portable -CompressionLevel Optimal

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $SkipInstaller -and $null -ne $iscc) {
    Invoke-Checked { & $iscc.Source (Join-Path $root "packaging\PBIBrain.iss") } "Inno Setup"
} elseif (-not $SkipInstaller) {
    Write-Warning "Inno Setup was not found. Portable ZIP was built; install Inno Setup 6 and rerun this command to create the installer."
}

Write-Host "Portable build: $portable"
