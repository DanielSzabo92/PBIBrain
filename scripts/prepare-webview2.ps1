[CmdletBinding()]
param(
    [string]$Destination = (Join-Path $PSScriptRoot "..\runtime")
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $Destination | Out-Null

# Evergreen bootstrapper is bundled for the Inno Setup installer. It is used
# only when Microsoft Edge WebView2 is missing.
Invoke-WebRequest -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124703" -OutFile (Join-Path $Destination "MicrosoftEdgeWebView2Setup.exe")
