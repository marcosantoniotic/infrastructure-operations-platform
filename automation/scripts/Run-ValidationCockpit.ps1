[CmdletBinding()]
param(
    [switch]$VerifyIdempotence,
    [switch]$VerifyPersistence
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$vagrantRoot = Join-Path $projectRoot 'automation\vagrant'
$validationRoot = Join-Path $projectRoot '.validation'
$privateKey = Join-Path $validationRoot 'id_ed25519'
$configuration = Get-Content (Join-Path $validationRoot 'vagrant.json') -Raw |
    ConvertFrom-Json
$ansibleRoot = Join-Path $validationRoot 'ansible'
$inventory = Join-Path $ansibleRoot 'hosts.yml'
$groupVarsRoot = Join-Path $ansibleRoot 'group_vars\all'
$groupVars = Join-Path $groupVarsRoot 'main.yml'
$vaultFile = Join-Path $groupVarsRoot 'vault.yml'
$vaultPasswordFile = Join-Path $ansibleRoot 'vault-password.txt'
$credentialFile = Join-Path $validationRoot 'cockpit-initial-credentials.txt'
$passwordCandidateFile = Join-Path $ansibleRoot 'cockpit-admin-password.tmp'
$vaultMergeScriptFile = Join-Path $ansibleRoot 'cockpit-merge-vault.sh'
$playbook = Join-Path $projectRoot 'playbooks\cockpit.yml'
$cockpitRole = Join-Path $projectRoot 'roles\cockpit'
$traefikRole = Join-Path $projectRoot 'roles\traefik'
$traefikRunner = Join-Path $PSScriptRoot 'Run-ValidationTraefik.ps1'
$controller = "automation@$($configuration.controller_ip)"
$remoteRoot = '/home/automation/infrastructure-operations-platform'
$options = @(
    '-i', $privateKey,
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL',
    '-o', 'ConnectTimeout=10'
)

foreach ($path in @($privateKey, $inventory, $groupVars, $playbook, $traefikRunner)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required validation file not found: $path"
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

$content = Get-Content -LiteralPath $groupVars -Raw
$pattern = '(?ms)^# BEGIN VALIDATION COCKPIT\r?\n.*?^# END VALIDATION COCKPIT\r?\n?'
$content = [regex]::Replace($content, $pattern, '')
$section = @'
# BEGIN VALIDATION COCKPIT
cockpit_hostname: cockpit.localhost
cockpit_additional_hostnames:
  - cockpit.localhost:8443
cockpit_enable_traefik: true
cockpit_direct_firewall_access: false
cockpit_login_title: Infrastructure Operations Platform
cockpit_validation_address: 127.0.0.1
cockpit_validation_port: 9091
cockpit_listen_port: 9091
cockpit_admin_enabled: true
cockpit_admin_username: cockpit-admin
cockpit_admin_password_hash: "{{ vault_cockpit_admin_password_hash }}"
cockpit_admin_groups:
  - wheel
traefik_enable_cockpit: true
traefik_cockpit_hostname: cockpit.localhost
traefik_cockpit_backend_url: https://host.containers.internal:9091
# END VALIDATION COCKPIT
'@
$utf8 = New-Object System.Text.UTF8Encoding -ArgumentList $false
[IO.File]::WriteAllText($groupVars, $content.TrimEnd() + "`n`n" + $section, $utf8)

$adminCredentialCandidate = New-RandomSecret
[IO.File]::WriteAllText(
    $passwordCandidateFile,
    $adminCredentialCandidate + "`n",
    $utf8
)
Set-CurrentUserFileAcl -Path $passwordCandidateFile

if (-not (Test-Path -LiteralPath $vaultPasswordFile -PathType Leaf)) {
    [IO.File]::WriteAllText($vaultPasswordFile, (New-RandomSecret), $utf8)
    Set-CurrentUserFileAcl -Path $vaultPasswordFile
}

Write-Host 'Preparing the dedicated Cockpit administrator in Ansible Vault.'
& ssh.exe @options $controller `
    "install -d -m 0755 $remoteRoot/inventories/validation/group_vars/all; install -d -m 0700 /home/automation/.ansible"
if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare the controller Vault directories.' }

& scp.exe @options $vaultPasswordFile "${controller}:/tmp/platform-vault-password"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Vault password.' }
& scp.exe @options $passwordCandidateFile "${controller}:/tmp/cockpit-admin-password"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Cockpit password candidate.' }
if (Test-Path -LiteralPath $vaultFile -PathType Leaf) {
    & scp.exe @options $vaultFile "${controller}:/tmp/platform-vault.yml"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the encrypted Vault.' }
}

$vaultMergeScript = @"
set -e
remote_root=$remoteRoot
vault_key_path=/home/automation/.ansible/vault-password
vault_target=`$remote_root/inventories/validation/group_vars/all/vault.yml
chmod 0600 /tmp/platform-vault-password /tmp/cockpit-admin-password
install -m 0600 /tmp/platform-vault-password "`$vault_key_path"
if [ -s /tmp/platform-vault.yml ]; then
  ansible-vault decrypt /tmp/platform-vault.yml --vault-password-file "`$vault_key_path" --output /tmp/platform-vault-plain.yml
else
  printf '%s\n' '---' > /tmp/platform-vault-plain.yml
fi
if grep -q '^vault_cockpit_admin_password_hash:' /tmp/platform-vault-plain.yml; then
  printf '%s\n' existing > /tmp/cockpit-secret-state
else
  cockpit_hash=`$(openssl passwd -6 -stdin < /tmp/cockpit-admin-password)
  printf "vault_cockpit_admin_password_hash: '%s'\n" "`$cockpit_hash" >> /tmp/platform-vault-plain.yml
  printf '%s\n' created > /tmp/cockpit-secret-state
fi
ansible-vault encrypt /tmp/platform-vault-plain.yml --vault-password-file "`$vault_key_path" --output "`$vault_target"
chmod 0600 "`$vault_target" /tmp/cockpit-secret-state
rm -f /tmp/platform-vault.yml /tmp/platform-vault-plain.yml /tmp/platform-vault-password /tmp/cockpit-admin-password
"@
$vaultMergeScript = $vaultMergeScript -replace "`r`n", "`n"
[IO.File]::WriteAllText($vaultMergeScriptFile, $vaultMergeScript, $utf8)
Set-CurrentUserFileAcl -Path $vaultMergeScriptFile
& scp.exe @options $vaultMergeScriptFile "${controller}:/tmp/cockpit-merge-vault.sh"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Cockpit Vault merge script.' }
& ssh.exe @options $controller `
    'bash /tmp/cockpit-merge-vault.sh; rc=$?; rm -f /tmp/cockpit-merge-vault.sh; exit $rc'
if ($LASTEXITCODE -ne 0) { throw 'Failed to merge the Cockpit administrator into Vault.' }
& scp.exe @options `
    "${controller}:$remoteRoot/inventories/validation/group_vars/all/vault.yml" $vaultFile
if ($LASTEXITCODE -ne 0) { throw 'Failed to preserve the encrypted Vault locally.' }
Set-CurrentUserFileAcl -Path $vaultFile

$secretState = (& ssh.exe @options $controller 'cat /tmp/cockpit-secret-state').Trim()
& ssh.exe @options $controller 'rm -f /tmp/cockpit-secret-state'
Remove-Item -LiteralPath $passwordCandidateFile, $vaultMergeScriptFile -Force

if ($secretState -eq 'created') {
    [IO.File]::WriteAllText(
        $credentialFile,
        "Direct URL (via SSH tunnel): https://127.0.0.1:9091/`r`nTraefik URL: https://cockpit.localhost:8443/`r`nUsername: cockpit-admin`r`nPassword: $adminCredentialCandidate`r`n",
        $utf8
    )
    Set-CurrentUserFileAcl -Path $credentialFile
}
elseif (-not (Test-Path -LiteralPath $credentialFile -PathType Leaf)) {
    throw 'Cockpit administrator exists in Vault, but the local credential record is unavailable.'
}

$credentialContent = Get-Content -LiteralPath $credentialFile -Raw
$passwordMatch = [regex]::Match($credentialContent, '(?m)^Password:\s*(\S+)\s*$')
if (-not $passwordMatch.Success) {
    throw 'Cockpit credential record does not contain a usable password.'
}
$adminCredential = $passwordMatch.Groups[1].Value

& $traefikRunner
if ($LASTEXITCODE -notin @(0, $null)) {
    throw 'Traefik validation failed before Cockpit execution.'
}

& ssh.exe @options $controller `
    "install -d -m 0755 $remoteRoot/playbooks $remoteRoot/roles $remoteRoot/inventories/validation/group_vars/all; sudo chown -R automation:automation $remoteRoot/roles"
if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare controller.' }

foreach ($copy in @(
    @{ Source = $playbook; Target = "$remoteRoot/playbooks/cockpit.yml" }
    @{ Source = $inventory; Target = "$remoteRoot/inventories/validation/hosts.yml" }
    @{ Source = $groupVars; Target = "$remoteRoot/inventories/validation/group_vars/all/main.yml" }
    @{ Source = $vaultFile; Target = "$remoteRoot/inventories/validation/group_vars/all/vault.yml" }
)) {
    & scp.exe @options $copy.Source "${controller}:$($copy.Target)"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage $($copy.Source)." }
}
foreach ($role in @($cockpitRole, $traefikRole)) {
    & scp.exe @options -r $role "${controller}:$remoteRoot/roles/"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage $role." }
}

$runs = if ($VerifyIdempotence) { 2 } else { 1 }
for ($run = 1; $run -le $runs; $run++) {
    & ssh.exe @options $controller `
        "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/cockpit.yml"
    if ($LASTEXITCODE -ne 0) { throw "Cockpit automation failed on pass $run." }
}

if ($VerifyPersistence) {
    Push-Location $vagrantRoot
    try {
        & vagrant.exe reload srv01-validation --no-provision
        if ($LASTEXITCODE -ne 0) { throw 'Failed to reload srv01-validation.' }
    }
    finally {
        Pop-Location
    }

    & ssh.exe @options $controller `
        "ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null automation@$($configuration.platform_ip) 'sudo systemctl is-enabled cockpit.socket && sudo systemctl is-active cockpit.socket && curl --fail --silent --show-error --insecure https://127.0.0.1:9091/ping >/dev/null'"
    if ($LASTEXITCODE -ne 0) {
        throw 'Cockpit persistence validation failed after VM reload.'
    }
}

& ssh.exe @options $controller `
    "ssh -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null automation@$($configuration.platform_ip) 'curl --fail --silent --show-error --insecure --retry 20 --retry-connrefused --retry-delay 3 --resolve cockpit.localhost:8443:127.0.0.1 https://cockpit.localhost:8443/ping >/dev/null'"
if ($LASTEXITCODE -ne 0) {
    throw 'Cockpit Traefik route validation failed.'
}

$platform = "automation@$($configuration.platform_ip)"
$loginValidationCommand = @'
IFS= read -r cockpit_password
cockpit_password=${cockpit_password%$'\r'}
auth=$(printf '%s:%s\0' 'cockpit-admin' "$cockpit_password" | base64 -w0)
response=$(
  printf 'header = "Authorization: Basic %s"\nheader = "X-Superuser: none"\n' "$auth" |
    curl --fail --silent --show-error --insecure --config - \
      --resolve cockpit.localhost:8443:127.0.0.1 \
      https://cockpit.localhost:8443/cockpit/login
)
printf '%s' "$response" | grep -Eq 'csrf-token|csrf_token'
'@
$adminCredential | & ssh.exe @options $platform $loginValidationCommand
if ($LASTEXITCODE -ne 0) {
    throw 'Cockpit administrator login validation failed.'
}

Write-Host "Cockpit initial credentials: $credentialFile"
Write-Warning 'Store the credential in a password manager and remove the local credential file.'
Write-Host 'Cockpit validation completed successfully.' -ForegroundColor Green
