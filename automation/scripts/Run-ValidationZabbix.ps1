[CmdletBinding()]
param(
    [switch]$EnableTraefik,
    [switch]$VerifyIdempotence,
    [switch]$VerifyPersistence
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$validationRoot = Join-Path $projectRoot '.validation'
$privateKey = Join-Path $validationRoot 'id_ed25519'
$vagrantConfig = Join-Path $validationRoot 'vagrant.json'
$ansibleRoot = Join-Path $validationRoot 'ansible'
$inventory = Join-Path $ansibleRoot 'hosts.yml'
$groupVarsRoot = Join-Path $ansibleRoot 'group_vars\all'
$groupVars = Join-Path $groupVarsRoot 'main.yml'
$vaultFile = Join-Path $groupVarsRoot 'vault.yml'
$vaultPasswordFile = Join-Path $ansibleRoot 'vault-password.txt'
$credentialFile = Join-Path $validationRoot 'zabbix-initial-credentials.txt'
$vaultAdditionsFile = Join-Path $ansibleRoot 'zabbix-vault-additions.yml'
$requirements = Join-Path $projectRoot 'requirements.yml'
$playbook = Join-Path $projectRoot 'playbooks\zabbix.yml'
$dockerRole = Join-Path $projectRoot 'roles\docker_engine'
$zabbixRole = Join-Path $projectRoot 'roles\zabbix'
$preflightRunner = Join-Path $PSScriptRoot 'Run-ValidationPreflight.ps1'
$vagrantRoot = Join-Path $projectRoot 'automation\vagrant'

foreach ($path in @(
    $privateKey,
    $vagrantConfig,
    $inventory,
    $requirements,
    $playbook,
    $preflightRunner
)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required validation file not found: $path"
    }
}
foreach ($path in @($dockerRole, $zabbixRole)) {
    if (-not (Test-Path -LiteralPath $path -PathType Container)) {
        throw "Required role not found: $path"
    }
}

function New-RandomSecret {
    param([ValidateRange(24, 128)][int]$ByteCount = 36)
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
    throw 'Validation preflight failed before Zabbix execution.'
}

$configuration = Get-Content -LiteralPath $vagrantConfig -Raw | ConvertFrom-Json
$controller = "automation@$($configuration.controller_ip)"
$remoteRoot = '/home/automation/infrastructure-operations-platform'
$commonOptions = @(
    '-i', $privateKey,
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL',
    '-o', 'ConnectTimeout=10'
)

New-Item -ItemType Directory -Path $groupVarsRoot -Force | Out-Null
$utf8WithoutBom = New-Object System.Text.UTF8Encoding -ArgumentList $false

$zabbixTraefikVariables = @('zabbix_enable_traefik: false')
if ($EnableTraefik) {
    $zabbixTraefikVariables = @(
        'zabbix_enable_traefik: true'
        'zabbix_traefik_hostname: zabbix.localhost'
        'zabbix_traefik_network: proxy'
        'zabbix_traefik_middlewares:'
        '  - security-headers@file'
        'zabbix_traefik_validation_address: 127.0.0.1'
        'zabbix_traefik_https_port: 8443'
    )
}
$zabbixTraefikVariablesYaml = $zabbixTraefikVariables -join "`n"

$groupVarsContent = if (Test-Path -LiteralPath $groupVars) {
    Get-Content -LiteralPath $groupVars -Raw
}
else {
    "---`n"
}
$zabbixSectionPattern = '(?ms)^# BEGIN VALIDATION ZABBIX\r?\n.*?^# END VALIDATION ZABBIX\r?\n?'
$groupVarsContent = [regex]::Replace($groupVarsContent, $zabbixSectionPattern, '')
$zabbixSection = @"
# BEGIN VALIDATION ZABBIX
zabbix_project_dir: /opt/zabbix
zabbix_server_image: zabbix/zabbix-server-mysql:7.4.12-alpine
zabbix_web_image: zabbix/zabbix-web-nginx-mysql:7.4.12-alpine
zabbix_mysql_image: mysql:8.4.10-oraclelinux9
zabbix_database_name: zabbix
zabbix_database_user: zabbix
zabbix_database_password: "{{ vault_zabbix_database_password }}"
zabbix_database_root_password: "{{ vault_zabbix_database_root_password }}"
zabbix_admin_user: Admin
zabbix_admin_password: "{{ vault_zabbix_admin_password }}"
zabbix_timezone: America/Sao_Paulo
zabbix_web_bind_address: 127.0.0.1
zabbix_web_port: 8081
zabbix_server_bind_address: 127.0.0.1
zabbix_server_port: 10051
zabbix_provision_platform_map: true
zabbix_platform_map_name: Infrastructure Operations Platform
zabbix_platform_map_host: infrastructure-operations-platform
zabbix_platform_display_name: SRV01-VALIDATION
zabbix_platform_host_address: $($configuration.platform_ip)
zabbix_agent2_enabled: true
zabbix_agent2_server_active: 127.0.0.1:10051
zabbix_agent2_template_name: Linux by Zabbix agent active
$zabbixTraefikVariablesYaml
# END VALIDATION ZABBIX
"@
[IO.File]::WriteAllText(
    $groupVars,
    $groupVarsContent.TrimEnd() + "`n`n" + $zabbixSection,
    $utf8WithoutBom
)

$databaseCredential = New-RandomSecret
$databaseRootCredential = New-RandomSecret
$adminCredential = New-RandomSecret
$vaultAdditions = @"
vault_zabbix_database_password: "$databaseCredential"
vault_zabbix_database_root_password: "$databaseRootCredential"
vault_zabbix_admin_password: "$adminCredential"
"@
[IO.File]::WriteAllText($vaultAdditionsFile, $vaultAdditions, $utf8WithoutBom)
Set-CurrentUserFileAcl -Path $vaultAdditionsFile

if (-not (Test-Path -LiteralPath $vaultPasswordFile -PathType Leaf)) {
    [IO.File]::WriteAllText(
        $vaultPasswordFile,
        (New-RandomSecret -ByteCount 48),
        $utf8WithoutBom
    )
    Set-CurrentUserFileAcl -Path $vaultPasswordFile
}

Write-Host 'Preparing Zabbix automation and Vault on the controller.'
& ssh.exe @commonOptions $controller `
    "install -d -m 0755 $remoteRoot/playbooks $remoteRoot/roles $remoteRoot/inventories/validation/group_vars/all; install -d -m 0700 /home/automation/.ansible; sudo chown -R automation:automation $remoteRoot/roles; chmod -R u+rwX $remoteRoot/roles"
if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare controller directories.' }

& scp.exe @commonOptions $vaultPasswordFile "${controller}:/tmp/platform-vault-password"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Vault password.' }
& scp.exe @commonOptions $vaultAdditionsFile "${controller}:/tmp/zabbix-vault-additions.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage Zabbix Vault additions.' }
if (Test-Path -LiteralPath $vaultFile -PathType Leaf) {
    & scp.exe @commonOptions $vaultFile "${controller}:/tmp/platform-vault.yml"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the encrypted Vault.' }
}

$vaultMergeScript = @"
set -e
remote_root=$remoteRoot
vault_key_path=/home/automation/.ansible/vault-password
vault_target=`$remote_root/inventories/validation/group_vars/all/vault.yml
install -m 0600 /tmp/platform-vault-password "`$vault_key_path"
if [ -s /tmp/platform-vault.yml ]; then
  ansible-vault decrypt /tmp/platform-vault.yml \
    --vault-password-file "`$vault_key_path" \
    --output /tmp/platform-vault-plain.yml
else
  printf '%s\n' '---' > /tmp/platform-vault-plain.yml
fi
for key in vault_zabbix_database_password vault_zabbix_database_root_password vault_zabbix_admin_password; do
  if ! grep -q "^`$key:" /tmp/platform-vault-plain.yml; then
    grep "^`$key:" /tmp/zabbix-vault-additions.yml >> /tmp/platform-vault-plain.yml
  fi
done
ansible-vault encrypt /tmp/platform-vault-plain.yml \
  --vault-password-file "`$vault_key_path" \
  --output "`$vault_target"
chmod 0600 "`$vault_target"
rm -f /tmp/platform-vault.yml /tmp/platform-vault-plain.yml \
  /tmp/platform-vault-password /tmp/zabbix-vault-additions.yml
"@
$vaultMergeScript = $vaultMergeScript -replace "`r`n", "`n"
$vaultMergeScriptFile = Join-Path $ansibleRoot 'zabbix-merge-vault.sh'
[IO.File]::WriteAllText($vaultMergeScriptFile, $vaultMergeScript, $utf8WithoutBom)
Set-CurrentUserFileAcl -Path $vaultMergeScriptFile
& scp.exe @commonOptions $vaultMergeScriptFile "${controller}:/tmp/zabbix-merge-vault.sh"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Vault merge script.' }
& ssh.exe @commonOptions $controller `
    "bash /tmp/zabbix-merge-vault.sh; rc=`$?; rm -f /tmp/zabbix-merge-vault.sh; exit `$rc"
if ($LASTEXITCODE -ne 0) { throw 'Failed to merge Zabbix secrets into Vault.' }
& scp.exe @commonOptions `
    "${controller}:$remoteRoot/inventories/validation/group_vars/all/vault.yml" `
    $vaultFile
if ($LASTEXITCODE -ne 0) { throw 'Failed to preserve the encrypted Vault locally.' }
Set-CurrentUserFileAcl -Path $vaultFile
Remove-Item -LiteralPath $vaultAdditionsFile, $vaultMergeScriptFile -Force

if (-not (Test-Path -LiteralPath $credentialFile -PathType Leaf)) {
    [IO.File]::WriteAllText(
        $credentialFile,
        "Direct fallback URL (via SSH tunnel): http://127.0.0.1:8081`r`nTraefik URL (when enabled): https://zabbix.localhost:8443/`r`nUsername: Admin`r`nPassword: $adminCredential`r`n",
        $utf8WithoutBom
    )
    Set-CurrentUserFileAcl -Path $credentialFile
}

& scp.exe @commonOptions $requirements "${controller}:$remoteRoot/requirements.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage requirements.yml.' }
& scp.exe @commonOptions $playbook "${controller}:$remoteRoot/playbooks/zabbix.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Zabbix playbook.' }
& scp.exe @commonOptions $inventory "${controller}:$remoteRoot/inventories/validation/hosts.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the validation inventory.' }
& scp.exe @commonOptions $groupVars "${controller}:$remoteRoot/inventories/validation/group_vars/all/main.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage validation variables.' }
foreach ($role in @($dockerRole, $zabbixRole)) {
    & scp.exe @commonOptions -r $role "${controller}:$remoteRoot/roles/"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage role: $role" }
}

& ssh.exe @commonOptions $controller `
    "cd $remoteRoot && ansible-galaxy collection install -r requirements.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to install required Ansible collections.' }

$runs = if ($VerifyIdempotence) { 2 } else { 1 }
for ($run = 1; $run -le $runs; $run++) {
    Write-Host "Executing Zabbix automation: pass $run of $runs."
    & ssh.exe @commonOptions $controller `
        "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/zabbix.yml"
    if ($LASTEXITCODE -ne 0) {
        throw "Zabbix automation failed on pass $run."
    }

    $networkIsolationCheck = @"
set -eu
if timeout 3 bash -c '</dev/tcp/$($configuration.platform_ip)/10051' \
  >/dev/null 2>&1; then
  echo 'Zabbix Server port 10051 is reachable from the controller.' >&2
  exit 30
fi
"@ -replace "`r`n", "`n"
    & ssh.exe @commonOptions $controller $networkIsolationCheck
    if ($LASTEXITCODE -ne 0) {
        throw 'Zabbix Server network-origin restriction validation failed.'
    }

    if ($run -eq 1 -and $VerifyPersistence) {
        Write-Host 'Reloading SRV01-VALIDATION to verify Zabbix persistence.'
        Push-Location $vagrantRoot
        try {
            & vagrant.exe reload srv01-validation --no-provision
            if ($LASTEXITCODE -ne 0) {
                throw 'Vagrant reload failed during Zabbix persistence validation.'
            }
        }
        finally {
            Pop-Location
        }
    }
}

Write-Host "Zabbix initial credentials: $credentialFile"
Write-Warning 'Store the credential in a password manager and remove the local credential file.'
Write-Host 'Zabbix validation completed successfully.' -ForegroundColor Green
