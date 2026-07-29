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
$credentialFile = Join-Path $validationRoot 'portainer-initial-credentials.txt'
$vaultAdditionsFile = Join-Path $ansibleRoot 'portainer-vault-additions.yml'
$requirements = Join-Path $projectRoot 'requirements.yml'
$playbook = Join-Path $projectRoot 'playbooks\portainer.yml'
$dockerRole = Join-Path $projectRoot 'roles\docker_engine'
$portainerRole = Join-Path $projectRoot 'roles\portainer'
$preflightRunner = Join-Path $PSScriptRoot 'Run-ValidationPreflight.ps1'
$traefikRunner = Join-Path $PSScriptRoot 'Run-ValidationTraefik.ps1'
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
foreach ($path in @($dockerRole, $portainerRole)) {
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
    throw 'Validation preflight failed before Portainer execution.'
}

if ($EnableTraefik) {
    & $traefikRunner
    if ($LASTEXITCODE -notin @(0, $null)) {
        throw 'Traefik validation failed before Portainer execution.'
    }
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

$portainerTraefikVariables = @('portainer_enable_traefik: false')
if ($EnableTraefik) {
    $portainerTraefikVariables = @(
        'portainer_enable_traefik: true'
        'portainer_traefik_hostname: portainer.localhost'
        'portainer_traefik_network: proxy'
        'portainer_traefik_middlewares:'
        '  - security-headers@file'
        'portainer_traefik_validation_address: 127.0.0.1'
        'portainer_traefik_https_port: 8443'
    )
}
$portainerTraefikVariablesYaml = $portainerTraefikVariables -join "`n"

$groupVarsContent = if (Test-Path -LiteralPath $groupVars) {
    Get-Content -LiteralPath $groupVars -Raw
}
else {
    "---`n"
}
$sectionPattern = '(?ms)^# BEGIN VALIDATION PORTAINER\r?\n.*?^# END VALIDATION PORTAINER\r?\n?'
$groupVarsContent = [regex]::Replace($groupVarsContent, $sectionPattern, '')
$portainerSection = @"
# BEGIN VALIDATION PORTAINER
portainer_project_dir: /opt/portainer
portainer_image: portainer/portainer-ce:2.39.5-alpine
portainer_admin_user: admin
portainer_admin_password: "{{ vault_portainer_admin_password }}"
portainer_bind_address: 127.0.0.1
portainer_http_port: 9000
$portainerTraefikVariablesYaml
# END VALIDATION PORTAINER
"@
[IO.File]::WriteAllText(
    $groupVars,
    $groupVarsContent.TrimEnd() + "`n`n" + $portainerSection,
    $utf8WithoutBom
)

$adminCredential = New-RandomSecret
$vaultAdditions = "vault_portainer_admin_password: `"$adminCredential`"`n"
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

Write-Host 'Preparing Portainer automation and Vault on the controller.'
& ssh.exe @commonOptions $controller `
    "install -d -m 0755 $remoteRoot/playbooks $remoteRoot/roles $remoteRoot/inventories/validation/group_vars/all; install -d -m 0700 /home/automation/.ansible; sudo chown -R automation:automation $remoteRoot/roles; chmod -R u+rwX $remoteRoot/roles"
if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare controller directories.' }

& scp.exe @commonOptions $vaultPasswordFile "${controller}:/tmp/platform-vault-password"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Vault password.' }
& scp.exe @commonOptions $vaultAdditionsFile "${controller}:/tmp/portainer-vault-additions.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage Portainer Vault additions.' }
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
if ! grep -q '^vault_portainer_admin_password:' /tmp/platform-vault-plain.yml; then
  grep '^vault_portainer_admin_password:' /tmp/portainer-vault-additions.yml \
    >> /tmp/platform-vault-plain.yml
  printf '%s\n' created > /tmp/portainer-secret-state
else
  printf '%s\n' existing > /tmp/portainer-secret-state
fi
ansible-vault encrypt /tmp/platform-vault-plain.yml \
  --vault-password-file "`$vault_key_path" \
  --output "`$vault_target"
chmod 0600 "`$vault_target"
rm -f /tmp/platform-vault.yml /tmp/platform-vault-plain.yml \
  /tmp/platform-vault-password /tmp/portainer-vault-additions.yml
"@
$vaultMergeScript = $vaultMergeScript -replace "`r`n", "`n"
$vaultMergeScriptFile = Join-Path $ansibleRoot 'portainer-merge-vault.sh'
[IO.File]::WriteAllText($vaultMergeScriptFile, $vaultMergeScript, $utf8WithoutBom)
Set-CurrentUserFileAcl -Path $vaultMergeScriptFile
& scp.exe @commonOptions $vaultMergeScriptFile "${controller}:/tmp/portainer-merge-vault.sh"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Vault merge script.' }
& ssh.exe @commonOptions $controller `
    "bash /tmp/portainer-merge-vault.sh; rc=`$?; rm -f /tmp/portainer-merge-vault.sh; exit `$rc"
if ($LASTEXITCODE -ne 0) { throw 'Failed to merge Portainer secret into Vault.' }
& scp.exe @commonOptions `
    "${controller}:$remoteRoot/inventories/validation/group_vars/all/vault.yml" `
    $vaultFile
if ($LASTEXITCODE -ne 0) { throw 'Failed to preserve the encrypted Vault locally.' }
Set-CurrentUserFileAcl -Path $vaultFile

$secretState = (& ssh.exe @commonOptions $controller 'cat /tmp/portainer-secret-state').Trim()
& ssh.exe @commonOptions $controller 'rm -f /tmp/portainer-secret-state'
Remove-Item -LiteralPath $vaultAdditionsFile, $vaultMergeScriptFile -Force

if ($secretState -eq 'created') {
    [IO.File]::WriteAllText(
        $credentialFile,
        "Direct fallback URL (via SSH tunnel): http://127.0.0.1:9000`r`nTraefik URL (when enabled): https://portainer.localhost:8443/`r`nUsername: admin`r`nPassword: $adminCredential`r`n",
        $utf8WithoutBom
    )
    Set-CurrentUserFileAcl -Path $credentialFile
}
elseif (-not (Test-Path -LiteralPath $credentialFile -PathType Leaf)) {
    throw 'The Portainer secret exists in Vault, but the local credential record is unavailable.'
}

foreach ($copy in @(
    @{ Source = $requirements; Target = "$remoteRoot/requirements.yml" }
    @{ Source = $playbook; Target = "$remoteRoot/playbooks/portainer.yml" }
    @{ Source = $inventory; Target = "$remoteRoot/inventories/validation/hosts.yml" }
    @{ Source = $groupVars; Target = "$remoteRoot/inventories/validation/group_vars/all/main.yml" }
)) {
    & scp.exe @commonOptions $copy.Source "${controller}:$($copy.Target)"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage: $($copy.Source)" }
}
foreach ($role in @($dockerRole, $portainerRole)) {
    & scp.exe @commonOptions -r $role "${controller}:$remoteRoot/roles/"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage role: $role" }
}

& ssh.exe @commonOptions $controller `
    "cd $remoteRoot && ansible-galaxy collection install -r requirements.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to install required Ansible collections.' }

$runs = if ($VerifyIdempotence) { 2 } else { 1 }
for ($run = 1; $run -le $runs; $run++) {
    Write-Host "Executing Portainer automation: pass $run of $runs."
    & ssh.exe @commonOptions $controller `
        "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/portainer.yml"
    if ($LASTEXITCODE -ne 0) {
        throw "Portainer automation failed on pass $run."
    }

    if ($run -eq 1 -and $VerifyPersistence) {
        Write-Host 'Reloading SRV01-VALIDATION to verify Portainer persistence.'
        Push-Location $vagrantRoot
        try {
            & vagrant.exe reload srv01-validation --no-provision
            if ($LASTEXITCODE -ne 0) {
                throw 'Vagrant reload failed during Portainer persistence validation.'
            }
        }
        finally {
            Pop-Location
        }
    }
}

Write-Host "Portainer initial credentials: $credentialFile"
Write-Warning 'Store the credential in a password manager and remove the local credential file.'
Write-Host 'Portainer validation completed successfully.' -ForegroundColor Green
