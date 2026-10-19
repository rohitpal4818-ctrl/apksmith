# Fetch the sample APK used by the integration tests.
#
# The integration tests skip cleanly when this file is absent, so running them
# without it is fine. This exists so a contributor can opt into the tests that
# need a real APK.
#
# F-Droid is open source (Apache-2.0) and is used as a known-good baseline:
# a legitimate app that should not produce a wall of false positives.

$ErrorActionPreference = "Stop"

$url = "https://f-droid.org/F-Droid.apk"
$dest = Join-Path (Split-Path -Parent $PSScriptRoot) "samples\F-Droid.apk"

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dest) | Out-Null

Write-Host "downloading F-Droid.apk (~12 MB) ..."
Invoke-WebRequest -Uri $url -OutFile $dest -TimeoutSec 900

$size = [math]::Round((Get-Item $dest).Length / 1MB, 1)
Write-Host "done: $dest ($size MB)"
Write-Host ""
Write-Host "Now run:  pytest"