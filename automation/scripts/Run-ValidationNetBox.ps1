[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidatePattern('^[^@\s]+@[^@\s]+\.[^@\s]+$')]
    [string]$AdminEmail,

    [switch]$VerifyIdempotence,
    [switch]$VerifyPersistence
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$validationRoot = Join-Path $projectRoot '.validation'
$privateKey = Join-Path $validationRoot 'id_ed25519'
$vagrantConfig = Join-Path $validationRoot 'vagrant.json'
$ansibleRoot = Join-Path $validationRoot 'ansible'
$groupVarsRoot = Join-Path $ansibleRoot 'group_vars\all'
$groupVars = Join-Path $groupVarsRoot 'main.yml'
$vaultFile = Join-Path $groupVarsRoot 'vault.yml'
$vaultPasswordFile = Join-Path $ansibleRoot 'vault-password.txt'
$credentialFile = Join-Path $validationRoot 'netbox-initial-credentials.txt'
$requirements = Join-Path $projectRoot 'requirements.yml'
$playbook = Join-Path $projectRoot 'playbooks\netbox.yml'
$dockerRole = Join-Path $projectRoot 'roles\docker_engine'
$netboxRole = Join-Path $projectRoot 'roles\netbox'
$preflightRunner = Join-Path $PSScriptRoot 'Run-ValidationPreflight.ps1'
$vagrantRoot = Join-Path $projectRoot 'automation\vagrant'

foreach ($path in @(
    $privateKey,
    $vagrantConfig,
    $requirements,
    $playbook,
    $preflightRunner
)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required validation file not found: $path"
    }
}
foreach ($path in @($dockerRole, $netboxRole)) {
    if (-not (Test-Path -LiteralPath $path -PathType Container)) {
        throw "Required role not found: $path"
    }
}

function New-RandomSecret {
    param([ValidateRange(24, 128)][int]$ByteCount = 48)
    $bytes = New-Object byte[] $ByteCount
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Set-CurrentUserFileAcl {
    param([Parameter(Mandatory)][string]$Path)
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $Path /inheritance:r /grant:r "${identity}:(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to restrict the local ACL: $Path"
    }
}

& $preflightRunner
if ($LASTEXITCODE -notin @(0, $null)) {
    throw 'Validation preflight failed before NetBox execution.'
}

$configuration = Get-Content -LiteralPath $vagrantConfig -Raw | ConvertFrom-Json
$controllerAddress = $configuration.controller_ip
$adminUsername = 'automation'
$controller = "$adminUsername@$controllerAddress"
$remoteRoot = "/home/$adminUsername/infrastructure-operations-platform"

New-Item -ItemType Directory -Path $groupVarsRoot -Force | Out-Null
$utf8WithoutBom = New-Object System.Text.UTF8Encoding -ArgumentList $false

$escapedAdminEmail = $AdminEmail.Replace("'", "''")
$groupVarsContent = @"
---
docker_users:
  - automation
docker_daemon_config:
  log-driver: json-file
  log-opts:
    max-size: 10m
    max-file: "3"
  live-restore: true

netbox_project_dir: /opt/netbox
netbox_image: netboxcommunity/netbox:v4.5.10-4.0.2
netbox_postgres_image: postgres:18-alpine
netbox_valkey_image: valkey/valkey:9.0-alpine
netbox_bind_address: 127.0.0.1
netbox_http_port: 8000
netbox_allowed_hosts:
  - localhost
  - 127.0.0.1
netbox_secret_key: "{{ vault_netbox_secret_key }}"
netbox_api_token_pepper: "{{ vault_netbox_api_token_pepper }}"
netbox_postgres_password: "{{ vault_netbox_postgres_password }}"
netbox_redis_password: "{{ vault_netbox_redis_password }}"
netbox_redis_cache_password: "{{ vault_netbox_redis_cache_password }}"
netbox_superuser_name: admin
netbox_superuser_email: '$escapedAdminEmail'
netbox_superuser_password: "{{ vault_netbox_superuser_password }}"
netbox_enable_metrics: true
netbox_enable_traefik: false
netbox_manage_firewall: false
netbox_validation_host: 127.0.0.1
"@
[IO.File]::WriteAllText($groupVars, $groupVarsContent, $utf8WithoutBom)

$commonOptions = @(
    '-i', $privateKey,
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL',
    '-o', 'ConnectTimeout=10'
)

Write-Host 'Preparing NetBox automation and Vault on the controller.'
& ssh.exe @commonOptions $controller `
    "rm -f $remoteRoot/inventories/validation/group_vars/all.yml $remoteRoot/inventories/validation/group_vars/vault.yml; install -d -m 0755 $remoteRoot/roles $remoteRoot/inventories/validation/group_vars/all; install -d -m 0700 /home/$adminUsername/.ansible"
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to prepare NetBox directories on the controller.'
}

if (-not (Test-Path -LiteralPath $vaultFile -PathType Leaf) -or
    -not (Test-Path -LiteralPath $vaultPasswordFile -PathType Leaf)) {
    $plainVault = Join-Path $ansibleRoot 'vault.plain.yml'
    $vaultKeyMaterial = New-RandomSecret -ByteCount 36
    $initialAdminCredential = New-RandomSecret -ByteCount 36
    $plainVaultContent = @"
---
vault_netbox_secret_key: "$(New-RandomSecret -ByteCount 64)"
vault_netbox_api_token_pepper: "$(New-RandomSecret -ByteCount 48)"
vault_netbox_postgres_password: "$(New-RandomSecret -ByteCount 36)"
vault_netbox_redis_password: "$(New-RandomSecret -ByteCount 36)"
vault_netbox_redis_cache_password: "$(New-RandomSecret -ByteCount 36)"
vault_netbox_superuser_password: "$initialAdminCredential"
"@
    [IO.File]::WriteAllText($plainVault, $plainVaultContent, $utf8WithoutBom)
    [IO.File]::WriteAllText($vaultPasswordFile, $vaultKeyMaterial, $utf8WithoutBom)
    [IO.File]::WriteAllText(
        $credentialFile,
        "URL (via SSH tunnel): http://127.0.0.1:8000`r`nUsername: admin`r`nPassword: $initialAdminCredential`r`n",
        $utf8WithoutBom
    )
    Set-CurrentUserFileAcl -Path $plainVault
    Set-CurrentUserFileAcl -Path $vaultPasswordFile
    Set-CurrentUserFileAcl -Path $credentialFile

    & scp.exe @commonOptions $plainVault "${controller}:/tmp/netbox-vault-plain.yml"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the plaintext Vault.' }
    & scp.exe @commonOptions $vaultPasswordFile "${controller}:/tmp/netbox-vault-password"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Vault password.' }

    & ssh.exe @commonOptions $controller `
        "set -e; install -m 0600 /tmp/netbox-vault-password /home/$adminUsername/.ansible/vault-password; ansible-vault encrypt /tmp/netbox-vault-plain.yml --vault-password-file /home/$adminUsername/.ansible/vault-password --output $remoteRoot/inventories/validation/group_vars/all/vault.yml; rm -f /tmp/netbox-vault-plain.yml /tmp/netbox-vault-password"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to encrypt the NetBox Vault.' }
    & scp.exe @commonOptions `
        "${controller}:$remoteRoot/inventories/validation/group_vars/all/vault.yml" `
        $vaultFile
    if ($LASTEXITCODE -ne 0) { throw 'Failed to preserve the encrypted Vault locally.' }
    Set-CurrentUserFileAcl -Path $vaultFile
    Remove-Item -LiteralPath $plainVault -Force
}
else {
    & scp.exe @commonOptions $vaultPasswordFile "${controller}:/tmp/netbox-vault-password"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Vault password.' }
    & scp.exe @commonOptions $vaultFile `
        "${controller}:$remoteRoot/inventories/validation/group_vars/all/vault.yml"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the encrypted Vault.' }
    & ssh.exe @commonOptions $controller `
        "install -m 0600 /tmp/netbox-vault-password /home/$adminUsername/.ansible/vault-password; rm -f /tmp/netbox-vault-password"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install the Vault password.' }
}

& scp.exe @commonOptions $requirements "${controller}:$remoteRoot/requirements.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage requirements.yml.' }
& scp.exe @commonOptions $playbook "${controller}:$remoteRoot/playbooks/netbox.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the NetBox playbook.' }
& scp.exe @commonOptions $groupVars `
    "${controller}:$remoteRoot/inventories/validation/group_vars/all/main.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage NetBox variables.' }
foreach ($role in @($dockerRole, $netboxRole)) {
    & scp.exe @commonOptions -r $role "${controller}:$remoteRoot/roles/"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage role: $role" }
}

& ssh.exe @commonOptions $controller `
    "cd $remoteRoot && ansible-galaxy collection install -r requirements.yml"
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to install required Ansible collections.'
}

$runs = if ($VerifyIdempotence) { 2 } else { 1 }
for ($run = 1; $run -le $runs; $run++) {
    Write-Host "Executing NetBox automation: pass $run of $runs."
    & ssh.exe @commonOptions $controller `
        "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/$adminUsername/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/netbox.yml"
    if ($LASTEXITCODE -ne 0) {
        throw "NetBox automation failed on pass $run."
    }

    if ($run -eq 1 -and $VerifyPersistence) {
        Write-Host 'Reloading SRV01-VALIDATION to verify persistent services and data.'
        Push-Location $vagrantRoot
        try {
            & vagrant.exe reload srv01-validation --no-provision
            if ($LASTEXITCODE -ne 0) {
                throw 'Vagrant reload failed during NetBox persistence validation.'
            }
        }
        finally {
            Pop-Location
        }
    }
}

Write-Host "NetBox initial credentials: $credentialFile"
Write-Warning 'Store the initial credential in a password manager and remove the local credential file.'
Write-Host 'NetBox validation completed successfully.' -ForegroundColor Green
