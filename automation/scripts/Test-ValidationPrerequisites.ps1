[CmdletBinding()]
param(
    [string]$IsoPath = 'D:\ISOs\rhel-9.8-x86_64-dvd.iso',
    [switch]$SkipIsoHash
)

$ErrorActionPreference = 'Stop'
$expectedIsoHash = 'C0DD53B73406B85B40D6168D1748E605D71361B2992D282C408B7D7D2E1D2C80'
$errors = [System.Collections.Generic.List[string]]::new()

if (-not (Test-Path -LiteralPath $IsoPath -PathType Leaf)) {
    $errors.Add("RHEL DVD ISO not found: $IsoPath")
}
elseif (-not $SkipIsoHash) {
    $actualHash = (Get-FileHash -LiteralPath $IsoPath -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedIsoHash) {
        $errors.Add("RHEL DVD ISO checksum mismatch: $actualHash")
    }
}

$vmware = Get-ItemProperty `
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', `
    'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' `
    -ErrorAction SilentlyContinue |
    Where-Object { $_.DisplayName -eq 'VMware Workstation' } |
    Select-Object -First 1

if (-not $vmware) {
    $errors.Add('VMware Workstation is not installed.')
}

foreach ($tool in @('ssh-keygen', 'packer', 'vagrant')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        $errors.Add("Required command not found in PATH: $tool")
    }
}

if ($errors.Count -gt 0) {
    $errors | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host 'Validation prerequisites approved.'
Write-Host "VMware Workstation: $($vmware.DisplayVersion)"
Write-Host "RHEL ISO: $IsoPath"
Write-Host "Packer: $(& packer version)"
Write-Host "Vagrant: $(& vagrant --version)"
