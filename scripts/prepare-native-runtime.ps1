[CmdletBinding()]
param(
    [string]$Destination = (Join-Path $PSScriptRoot "..\runtime"),
    [string]$Cache = (Join-Path $PSScriptRoot "..\.cache\native")
)

$ErrorActionPreference = "Stop"
$ladybugUrl = "https://github.com/LadybugDB/ladybug/releases/download/v0.20.0/liblbug-windows-x86_64.zip"
$ladybugHash = "CDDFE2ED043E534086F161E8F0D32C4766E074F84E3D1416270465F05BC45828"
$gitUrl = "https://github.com/git-for-windows/git/releases/download/v2.55.0.windows.5/MinGit-2.55.0.5-64-bit.zip"
$gitHash = "56D7B226B7693196CFC71FEF26568F536C4A021AB6C37FF2DB4287BED908E96E"

function Get-VerifiedFile([string]$Url, [string]$Path, [string]$ExpectedHash) {
    if (-not (Test-Path -LiteralPath $Path)) { Invoke-WebRequest -Uri $Url -OutFile $Path }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    if ($actual -ne $ExpectedHash) { throw "SHA-256 mismatch for $Path. Expected $ExpectedHash, got $actual." }
}

New-Item -ItemType Directory -Force -Path $Cache, $Destination | Out-Null
$native = Join-Path $Destination "native"
$licenses = Join-Path $Destination "licenses"
New-Item -ItemType Directory -Force -Path $native, $licenses | Out-Null

$ladybugArchive = Join-Path $Cache "liblbug-windows-x86_64-v0.20.0.zip"
Get-VerifiedFile $ladybugUrl $ladybugArchive $ladybugHash
$ladybugExtract = Join-Path $Cache "liblbug-windows-x86_64-v0.20.0"
if (-not (Test-Path -LiteralPath $ladybugExtract)) {
    Expand-Archive -LiteralPath $ladybugArchive -DestinationPath $ladybugExtract
}
Copy-Item -LiteralPath (Join-Path $ladybugExtract "lbug_shared.dll") -Destination $native -Force

# OpenSSL DLLs are copied from the maintained Git for Windows release. Only
# the two required runtime DLLs remain in the application payload.
$gitArchive = Join-Path $Cache "MinGit-2.55.0.5-64-bit.zip"
Get-VerifiedFile $gitUrl $gitArchive $gitHash
$gitExtract = Join-Path $Cache "MinGit-2.55.0.5-64-bit"
if (-not (Test-Path -LiteralPath $gitExtract)) {
    Expand-Archive -LiteralPath $gitArchive -DestinationPath $gitExtract
}
$ssl = Get-ChildItem -LiteralPath $gitExtract -Recurse -Filter "libssl-3-x64.dll" | Select-Object -First 1
$crypto = Get-ChildItem -LiteralPath $gitExtract -Recurse -Filter "libcrypto-3-x64.dll" | Select-Object -First 1
if ($null -eq $ssl -or $null -eq $crypto) { throw "OpenSSL 3 x64 DLLs were not found in the verified Git for Windows archive." }
Copy-Item -LiteralPath $ssl.FullName, $crypto.FullName -Destination $native -Force

Invoke-WebRequest -Uri "https://raw.githubusercontent.com/LadybugDB/ladybug/v0.20.0/LICENSE" -OutFile (Join-Path $licenses "LadybugDB-LICENSE.txt")
Copy-Item -LiteralPath (Join-Path $gitExtract "mingw64\share\licenses\openssl\LICENSE") -Destination (Join-Path $licenses "OpenSSL-LICENSE.txt") -Force

# Evergreen bootstrapper is bundled for the Inno Setup installer. It is used
# only when Microsoft Edge WebView2 is missing.
Invoke-WebRequest -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124703" -OutFile (Join-Path $Destination "MicrosoftEdgeWebView2Setup.exe")

$needed = "lbug_shared.dll", "libssl-3-x64.dll", "libcrypto-3-x64.dll"
foreach ($name in $needed) {
    if (-not (Test-Path -LiteralPath (Join-Path $native $name))) { throw "Missing bundled native file: $name" }
}
Get-ChildItem -LiteralPath $native -File | Get-FileHash -Algorithm SHA256 | Format-Table -AutoSize
