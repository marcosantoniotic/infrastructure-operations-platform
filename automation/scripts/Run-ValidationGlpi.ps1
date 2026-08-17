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
$groupVarsRoot = Join-Path $ansibleRoot 'group_vars\all'
$groupVars = Join-Path $groupVarsRoot 'main.yml'
$vaultFile = Join-Path $groupVarsRoot 'vault.yml'
$vaultPasswordFile = Join-Path $ansibleRoot 'vault-password.txt'
$credentialFile = Join-Path $validationRoot 'glpi-initial-credentials.txt'
$vaultAdditionsFile = Join-Path $ansibleRoot 'glpi-vault-additions.yml'
$requirements = Join-Path $projectRoot 'requirements.yml'
$playbook = Join-Path $projectRoot 'playbooks\glpi.yml'
$dockerRole = Join-Path $projectRoot 'roles\docker_engine'
$glpiRole = Join-Path $projectRoot 'roles\glpi'
$preflightRunner = Join-Path $PSScriptRoot 'Run-ValidationPreflight.ps1'
$traefikRunner = Join-Path $PSScriptRoot 'Run-ValidationTraefik.ps1'
$vagrantRoot = Join-Path $projectRoot 'automation\vagrant'

foreach ($path in @(
    $privateKey,
    $vagrantConfig,
    $inventory = Join-Path $ansibleRoot 'hosts.yml',
    $requirements,
    $playbook,
    $preflightRunner
)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required validation file not found: $path"
    }
}
foreach ($path in @($dockerRole, $glpiRole)) {
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
    throw 'Validation preflight failed before GLPI execution.'
}

if ($EnableTraefik) {
    & $traefikRunner
    if ($LASTEXITCODE -notin @(0, $null)) {
        throw 'Traefik validation failed before GLPI execution.'
    }
}

# Nested validation runners use the same conventional variable names. Rebuild
# this runner's paths after they return so PowerShell dynamic scoping cannot
# leave a shared path unset.
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
$credentialFile = Join-Path $validationRoot 'glpi-initial-credentials.txt'
$vaultAdditionsFile = Join-Path $ansibleRoot 'glpi-vault-additions.yml'
$requirements = Join-Path $projectRoot 'requirements.yml'
$playbook = Join-Path $projectRoot 'playbooks\glpi.yml'
$dockerRole = Join-Path $projectRoot 'roles\docker_engine'
$glpiRole = Join-Path $projectRoot 'roles\glpi'
$vagrantRoot = Join-Path $projectRoot 'automation\vagrant'

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

$traefikVariables = @('glpi_enable_traefik: false')
if ($EnableTraefik) {
    $traefikVariables = @(
        'glpi_enable_traefik: true'
        'glpi_traefik_hostname: glpi.localhost'
        'glpi_traefik_additional_hostnames: []'
        'glpi_traefik_network: proxy'
        'glpi_traefik_middlewares:'
        '  - security-headers@file'
        'glpi_traefik_validation_address: 127.0.0.1'
        'glpi_traefik_https_port: 8443'
    )
}
$traefikVariablesYaml = $traefikVariables -join "`n"
$groupVarsContent = if (Test-Path -LiteralPath $groupVars) {
    Get-Content -LiteralPath $groupVars -Raw
}
else {
    "---`n"
}
$sectionPattern = '(?ms)^# BEGIN VALIDATION GLPI\r?\n.*?^# END VALIDATION GLPI\r?\n?'
$groupVarsContent = [regex]::Replace($groupVarsContent, $sectionPattern, '')
$glpiSection = @"
# BEGIN VALIDATION GLPI
glpi_project_dir: /opt/glpi
glpi_image: glpi/glpi:11.0.8
glpi_database_image: mariadb:11.8.8
glpi_database_name: glpi
glpi_database_user: glpi
glpi_database_password: "{{ vault_glpi_database_password }}"
glpi_database_root_password: "{{ vault_glpi_database_root_password }}"
glpi_timezone: America/Sao_Paulo
glpi_auto_install: true
glpi_skip_auto_update: true
glpi_crontab_enabled: true
glpi_admin_managed: true
glpi_admin_user: glpi-admin
glpi_admin_password: "{{ vault_glpi_admin_password }}"
glpi_admin_profile_id: 4
glpi_admin_entity_id: 0
glpi_admin_recursive: true
glpi_admin_rotate_password: false
glpi_disable_default_accounts: true
glpi_bind_address: 127.0.0.1
glpi_http_port: 8083
glpi_validation_host: 127.0.0.1
$traefikVariablesYaml
# END VALIDATION GLPI
"@
[IO.File]::WriteAllText(
    $groupVars,
    $groupVarsContent.TrimEnd() + "`n`n" + $glpiSection,
    $utf8WithoutBom
)

$adminCredential = New-RandomSecret -ByteCount 36
$vaultAdditions = @"
vault_glpi_database_password: "$(New-RandomSecret)"
vault_glpi_database_root_password: "$(New-RandomSecret)"
vault_glpi_admin_password: "$adminCredential"
"@
[IO.File]::WriteAllText($vaultAdditionsFile, $vaultAdditions, $utf8WithoutBom)
Set-CurrentUserFileAcl -Path $vaultAdditionsFile

if (-not (Test-Path -LiteralPath $vaultPasswordFile -PathType Leaf)) {
    [IO.File]::WriteAllText($vaultPasswordFile, (New-RandomSecret), $utf8WithoutBom)
    Set-CurrentUserFileAcl -Path $vaultPasswordFile
}

Write-Host 'Preparing GLPI automation and Vault on AUTOMATION-CONTROLLER.'
& ssh.exe @commonOptions $controller `
    "sudo rm -rf $remoteRoot/roles/docker_engine $remoteRoot/roles/glpi; install -d -m 0755 $remoteRoot/playbooks $remoteRoot/roles $remoteRoot/inventories/validation/group_vars/all; install -d -m 0700 /home/automation/.ansible; sudo chown -R automation:automation $remoteRoot/roles"
if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare controller directories.' }

& scp.exe @commonOptions $vaultPasswordFile "${controller}:/tmp/platform-vault-password"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Vault password.' }
& scp.exe @commonOptions $vaultAdditionsFile "${controller}:/tmp/glpi-vault-additions.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage GLPI Vault additions.' }
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
  ansible-vault decrypt /tmp/platform-vault.yml --vault-password-file "`$vault_key_path" --output /tmp/platform-vault-plain.yml
else
  printf '%s\n' '---' > /tmp/platform-vault-plain.yml
fi
created=false
admin_created=false
for variable in vault_glpi_database_password vault_glpi_database_root_password vault_glpi_admin_password; do
  if ! grep -q "^`$variable:" /tmp/platform-vault-plain.yml; then
    grep "^`$variable:" /tmp/glpi-vault-additions.yml >> /tmp/platform-vault-plain.yml
    created=true
    if [ "`$variable" = vault_glpi_admin_password ]; then
      admin_created=true
    fi
  fi
done
if [ "`$admin_created" = true ]; then
  printf '%s\n' created > /tmp/glpi-secret-state
else
  printf '%s\n' existing > /tmp/glpi-secret-state
fi
ansible-vault encrypt /tmp/platform-vault-plain.yml --vault-password-file "`$vault_key_path" --output "`$vault_target"
chmod 0600 "`$vault_target"
rm -f /tmp/platform-vault.yml /tmp/platform-vault-plain.yml /tmp/platform-vault-password /tmp/glpi-vault-additions.yml
"@
$vaultMergeScript = $vaultMergeScript -replace "`r`n", "`n"
$vaultMergeScriptFile = Join-Path $ansibleRoot 'glpi-merge-vault.sh'
[IO.File]::WriteAllText($vaultMergeScriptFile, $vaultMergeScript, $utf8WithoutBom)
Set-CurrentUserFileAcl -Path $vaultMergeScriptFile
& scp.exe @commonOptions $vaultMergeScriptFile "${controller}:/tmp/glpi-merge-vault.sh"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the GLPI Vault merge script.' }
& ssh.exe @commonOptions $controller `
    "bash /tmp/glpi-merge-vault.sh; rc=`$?; rm -f /tmp/glpi-merge-vault.sh; exit `$rc"
if ($LASTEXITCODE -ne 0) { throw 'Failed to merge GLPI secrets into Vault.' }
& scp.exe @commonOptions `
    "${controller}:$remoteRoot/inventories/validation/group_vars/all/vault.yml" $vaultFile
if ($LASTEXITCODE -ne 0) { throw 'Failed to preserve the encrypted Vault locally.' }
Set-CurrentUserFileAcl -Path $vaultFile

$secretState = (& ssh.exe @commonOptions $controller 'cat /tmp/glpi-secret-state').Trim()
& ssh.exe @commonOptions $controller 'rm -f /tmp/glpi-secret-state'
Remove-Item -LiteralPath $vaultAdditionsFile, $vaultMergeScriptFile -Force

if ($secretState -eq 'created') {
    [IO.File]::WriteAllText(
        $credentialFile,
        "Direct health URL (via SSH tunnel): http://127.0.0.1:8083/`r`nTraefik URL (when enabled): https://glpi.localhost:8443/`r`nUsername: glpi-admin`r`nPassword: $adminCredential`r`n",
        $utf8WithoutBom
    )
    Set-CurrentUserFileAcl -Path $credentialFile
}
elseif (-not (Test-Path -LiteralPath $credentialFile -PathType Leaf)) {
    throw 'GLPI secrets exist in Vault, but the local credential record is unavailable.'
}

foreach ($copy in @(
    @{ Source = $requirements; Target = "$remoteRoot/requirements.yml" }
    @{ Source = $playbook; Target = "$remoteRoot/playbooks/glpi.yml" }
    @{ Source = $inventory; Target = "$remoteRoot/inventories/validation/hosts.yml" }
    @{ Source = $groupVars; Target = "$remoteRoot/inventories/validation/group_vars/all/main.yml" }
)) {
    & scp.exe @commonOptions $copy.Source "${controller}:$($copy.Target)"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage: $($copy.Source)" }
}
foreach ($role in @($dockerRole, $glpiRole)) {
    & scp.exe @commonOptions -r $role "${controller}:$remoteRoot/roles/"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage role: $role" }
}

& ssh.exe @commonOptions $controller `
    "cd $remoteRoot && ansible-galaxy collection install -r requirements.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to install required Ansible collections.' }

$runs = if ($VerifyIdempotence -or $VerifyPersistence) { 2 } else { 1 }
for ($run = 1; $run -le $runs; $run++) {
    Write-Host "Executing GLPI automation: pass $run of $runs."
    & ssh.exe @commonOptions $controller `
        "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/glpi.yml"
    if ($LASTEXITCODE -ne 0) { throw "GLPI automation failed on pass $run." }

    if ($run -eq 1 -and $VerifyPersistence) {
        Write-Host 'Reloading SRV01-VALIDATION to verify GLPI persistence.'
        Push-Location $vagrantRoot
        try {
            & vagrant.exe reload srv01-validation --no-provision
            if ($LASTEXITCODE -ne 0) {
                throw 'Vagrant reload failed during GLPI persistence validation.'
            }
        }
        finally {
            Pop-Location
        }
    }
}

Write-Host "GLPI initial credentials: $credentialFile"
Write-Warning 'Store the credential in a password manager and remove the local credential file.'
Write-Host 'GLPI validation completed successfully.' -ForegroundColor Green
