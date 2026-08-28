param(
    [Parameter(Mandatory = $true)]
    [string]$IsoPath
)

$ErrorActionPreference = "Stop"
$Iso = Resolve-Path $IsoPath
$ChecksumPath = "$Iso.sha256"
if (-not (Test-Path $ChecksumPath)) {
    throw "Checksum file not found: $ChecksumPath"
}

$Expected = ((Get-Content $ChecksumPath -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
$Actual = (Get-FileHash -Algorithm SHA256 $Iso).Hash.ToLowerInvariant()

Write-Host "Expected: $Expected"
Write-Host "Actual:   $Actual"
if ($Expected -ne $Actual) {
    throw "SHA-256 verification FAILED. Do not write this ISO to USB."
}
Write-Host "[OK] SHA-256 verification passed."
