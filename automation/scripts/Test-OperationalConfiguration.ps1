[CmdletBinding()]
param(
    [ValidateSet('Image', 'Virtualization', 'Deployment')]
    [string]$Phase = 'Deployment'
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$operationalRoot = Join-Path $projectRoot '.operational'
$inventoryRoot = Join-Path $projectRoot 'inventories\operational'
$packerRoot = Join-Path $projectRoot 'automation\packer\rhel9'
$errors = [System.Collections.Generic.List[string]]::new()

function Add-CheckError {
    param([Parameter(Mandatory)][string]$Message)
    $errors.Add($Message)
}

function Test-GitIgnored {
    param([Parameter(Mandatory)][string]$RelativePath)

    & git -C $projectRoot check-ignore -q -- $RelativePath
    if ($LASTEXITCODE -ne 0) {
        Add-CheckError "Private path is not ignored by Git: $RelativePath"
    }
}

foreach ($tool in @('git', 'packer', 'ssh-keygen', 'vagrant')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        Add-CheckError "Required command not found in PATH: $tool"
    }
}

$requiredFiles = [ordered]@{
    'Operational SSH private key' = Join-Path $operationalRoot 'id_ed25519'
    'Operational SSH public key' = Join-Path $operationalRoot 'id_ed25519.pub'
    'Packer variable file' = Join-Path $operationalRoot 'operational.pkrvars.hcl'
    'Vagrant configuration' = Join-Path $operationalRoot 'vagrant.json'
}
if ($Phase -eq 'Deployment') {
    $requiredFiles['Private Ansible inventory'] = Join-Path $inventoryRoot 'hosts.yml'
    $requiredFiles['Private Ansible variables'] = Join-Path $inventoryRoot 'group_vars\all.yml'
    $requiredFiles['Encrypted Ansible Vault'] = Join-Path $inventoryRoot 'group_vars\vault.yml'
}

foreach ($entry in $requiredFiles.GetEnumerator()) {
    if (-not (Test-Path -LiteralPath $entry.Value -PathType Leaf)) {
        Add-CheckError "$($entry.Key) not found. Run Initialize-Operational.ps1 first."
    }
}

if (Get-Command git -ErrorAction SilentlyContinue) {
    foreach ($relativePath in @(
            '.operational/vagrant.json',
            '.operational/operational.pkrvars.hcl',
            '.operational/id_ed25519',
            '.operational/id_ed25519.pub',
            'inventories/operational/hosts.yml',
            'inventories/operational/group_vars/all.yml',
            'inventories/operational/group_vars/vault.yml'
        )) {
        Test-GitIgnored -RelativePath $relativePath
    }
}

$placeholderPattern = '<[A-Z][A-Z0-9_]+>'
if ($Phase -eq 'Deployment') {
    foreach ($relativePath in @(
            'inventories\operational\hosts.yml',
            'inventories\operational\group_vars\all.yml'
        )) {
        $fullPath = Join-Path $projectRoot $relativePath
        if (
            (Test-Path -LiteralPath $fullPath -PathType Leaf) -and
            (Get-Content -LiteralPath $fullPath -Raw) -match $placeholderPattern
        ) {
            Add-CheckError "Unresolved placeholder found in private file: $relativePath"
        }
    }

    $vaultPath = Join-Path $inventoryRoot 'group_vars\vault.yml'
    if (Test-Path -LiteralPath $vaultPath -PathType Leaf) {
        $vaultHeader = Get-Content -LiteralPath $vaultPath -TotalCount 1
        if ($vaultHeader -notmatch '^\$ANSIBLE_VAULT;1\.[12];AES256$') {
            Add-CheckError 'vault.yml is not encrypted with Ansible Vault.'
        }
    }
}

$vagrantConfigPath = Join-Path $operationalRoot 'vagrant.json'
if (Test-Path -LiteralPath $vagrantConfigPath -PathType Leaf) {
    try {
        $vagrantConfig = Get-Content -LiteralPath $vagrantConfigPath -Raw |
            ConvertFrom-Json -ErrorAction Stop
        foreach ($propertyName in @(
                'box_name',
                'admin_username',
                'ssh_private_key',
                'controller_ip',
                'platform_ip',
                'resources'
            )) {
            if (-not $vagrantConfig.PSObject.Properties[$propertyName]) {
                Add-CheckError "Vagrant configuration is missing: $propertyName"
            }
        }
        foreach ($resourceName in @('controller', 'platform', 'recovery', 'standby')) {
            if (-not $vagrantConfig.resources.PSObject.Properties[$resourceName]) {
                Add-CheckError "Vagrant resource definition is missing: $resourceName"
            }
        }
    }
    catch {
        Add-CheckError 'Vagrant configuration is not valid JSON.'
    }
}

$packerVarsPath = Join-Path $operationalRoot 'operational.pkrvars.hcl'
if (Test-Path -LiteralPath $packerVarsPath -PathType Leaf) {
    $packerVariables = Get-Content -LiteralPath $packerVarsPath -Raw
    if ($packerVariables -notmatch '(?m)^disk_size_mb\s*=\s*81920\s*$') {
        Add-CheckError 'Operational Packer disk capacity must be 81920 MiB.'
    }
    $isoMatch = [regex]::Match(
        $packerVariables,
        '(?m)^iso_path\s*=\s*"(?<path>[^"]+)"\s*$'
    )
    if (-not $isoMatch.Success) {
        Add-CheckError 'Unable to resolve iso_path from operational Packer variables.'
    }
    else {
        $isoPath = $isoMatch.Groups['path'].Value.Replace('/', '\')
        if (-not (Test-Path -LiteralPath $isoPath -PathType Leaf)) {
            Add-CheckError 'The RHEL DVD ISO referenced by Packer does not exist.'
        }
    }
}

if (Get-Command vagrant -ErrorAction SilentlyContinue) {
    $pluginOutput = (& vagrant plugin list 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0 -or $pluginOutput -notmatch 'vagrant-vmware-desktop') {
        Add-CheckError 'The vagrant-vmware-desktop plugin is not installed.'
    }

    if (Test-Path -LiteralPath $vagrantConfigPath -PathType Leaf) {
        Push-Location (Join-Path $projectRoot 'automation\vagrant\operational')
        try {
            & vagrant validate *> $null
            if ($LASTEXITCODE -ne 0) {
                Add-CheckError 'Operational Vagrant configuration failed validation.'
            }
        }
        finally {
            Pop-Location
        }
    }

    if ($Phase -ne 'Image' -and $null -ne $vagrantConfig) {
        $boxOutput = (& vagrant box list 2>&1 | Out-String)
        $escapedBoxName = [regex]::Escape([string]$vagrantConfig.box_name)
        if ($LASTEXITCODE -ne 0 -or $boxOutput -notmatch "(?m)^$escapedBoxName\s") {
            Add-CheckError 'The operational Vagrant box is not registered locally.'
        }
    }
}

if (
    (Get-Command packer -ErrorAction SilentlyContinue) -and
    (Test-Path -LiteralPath $packerVarsPath -PathType Leaf)
) {
    Push-Location $packerRoot
    try {
        & packer validate "-var-file=$packerVarsPath" . *> $null
        if ($LASTEXITCODE -ne 0) {
            Add-CheckError 'Operational Packer configuration failed validation.'
        }
    }
    finally {
        Pop-Location
    }
}

if ($errors.Count -gt 0) {
    $errors | Sort-Object -Unique | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host 'Operational configuration approved.'
Write-Host "Validation phase: $Phase."
Write-Host 'Packer and Vagrant: valid.'
if ($Phase -eq 'Image') {
    Write-Host 'Vagrant box registration: not required in the image phase.'
}
else {
    Write-Host 'Vagrant box registration: approved.'
}
if ($Phase -eq 'Deployment') {
    Write-Host 'Private inventory: ignored by Git and free of placeholders.'
    Write-Host 'Ansible Vault: encrypted.'
}
