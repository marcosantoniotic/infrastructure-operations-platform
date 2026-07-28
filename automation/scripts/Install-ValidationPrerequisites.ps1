<#
.SYNOPSIS
Prepara a estação para validar a Infrastructure Operations Platform.

.DESCRIPTION
Executa o bootstrap universal da estação e acrescenta as verificações específicas
do repositório, do fluxo Packer/Vagrant e da mídia RHEL utilizada pelo projeto.

O Ansible deste ambiente roda na VM AUTOMATION-CONTROLLER; por isso o wrapper
não exige Ansible/WSL na estação Windows.
#>

[CmdletBinding()]
param(
    [string]$IsoPath = 'D:\ISOs\rhel-9.8-x86_64-dvd.iso',
    [string]$ExpectedIsoHash = 'C0DD53B73406B85B40D6168D1748E605D71361B2992D282C408B7D7D2E1D2C80',
    [switch]$AuditOnly,
    [switch]$InstallVmware,
    [switch]$KeepDownloads
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$bootstrap = Join-Path $PSScriptRoot 'Install-InfrastructureWorkstation.ps1'

Write-Host "`n==> Validando a estrutura específica do projeto" -ForegroundColor Cyan
$requiredPaths = @(
    'automation\packer\rhel9\rhel9.pkr.hcl',
    'automation\vagrant\Vagrantfile',
    'playbooks\preflight.yml'
)
foreach ($relativePath in $requiredPaths) {
    $path = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Arquivo obrigatório não encontrado: $path"
    }
}
Write-Host "Repositório aprovado: $projectRoot" -ForegroundColor Green

Write-Host "`n==> Executando o bootstrap universal da estação" -ForegroundColor Cyan
$bootstrapArguments = @{
    SkipAnsible = $true
}
if ($AuditOnly) {
    $bootstrapArguments.AuditOnly = $true
}
if ($InstallVmware) {
    $bootstrapArguments.InstallVmware = $true
}
if ($KeepDownloads) {
    $bootstrapArguments.KeepDownloads = $true
}

& $bootstrap @bootstrapArguments
if ($LASTEXITCODE -notin @(0, $null)) {
    throw "O bootstrap universal retornou o código $LASTEXITCODE."
}

Write-Host "`n==> Validando a mídia RHEL do projeto" -ForegroundColor Cyan
if (-not (Test-Path -LiteralPath $IsoPath -PathType Leaf)) {
    throw "ISO RHEL não encontrada: $IsoPath"
}
$actualHash = (Get-FileHash -LiteralPath $IsoPath -Algorithm SHA256).Hash
if ($actualHash.ToUpperInvariant() -ne $ExpectedIsoHash.ToUpperInvariant()) {
    throw "Checksum da ISO RHEL divergente: $actualHash"
}
Write-Host "ISO RHEL aprovada: $IsoPath" -ForegroundColor Green

Write-Host "`nPré-requisitos específicos do projeto aprovados." -ForegroundColor Green
Write-Host 'A próxima etapa é Initialize-Validation.ps1.'
