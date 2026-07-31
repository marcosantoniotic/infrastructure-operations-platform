[CmdletBinding()]
param([switch]$VerifyIdempotence)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$validationRoot = Join-Path $projectRoot '.validation'
$ansibleRoot = Join-Path $validationRoot 'ansible'
$groupVarsRoot = Join-Path $ansibleRoot 'group_vars\all'
$groupVars = Join-Path $groupVarsRoot 'main.yml'
$vaultFile = Join-Path $groupVarsRoot 'vault.yml'
$vaultPasswordFile = Join-Path $ansibleRoot 'vault-password.txt'
$additionsFile = Join-Path $ansibleRoot 'adguard-metrics-vault-additions.yml'
$mergeFile = Join-Path $ansibleRoot 'adguard-metrics-merge-vault.sh'
$credentialFile = Join-Path $validationRoot 'adguard-metrics-credentials.txt'
$privateKey = Join-Path $validationRoot 'id_ed25519'
$configurationFile = Join-Path $validationRoot 'vagrant.json'
$inventory = Join-Path $ansibleRoot 'hosts.yml'
$playbook = Join-Path $projectRoot 'playbooks\adguard-metrics.yml'
$userRole = Join-Path $projectRoot 'roles\adguard_metrics_user'
$collectorRole = Join-Path $projectRoot 'roles\adguard_metrics_collector'
$preflight = Join-Path $PSScriptRoot 'Run-ValidationPreflight.ps1'

foreach ($path in @($privateKey, $configurationFile, $inventory, $vaultPasswordFile, $playbook, $preflight)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file not found: $path" }
}
foreach ($path in @($userRole, $collectorRole)) {
    if (-not (Test-Path -LiteralPath $path -PathType Container)) { throw "Required role not found: $path" }
}

function New-RandomSecret {
    param([int]$ByteCount = 36)
    $bytes = New-Object byte[] $ByteCount
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function New-BcryptSalt {
    $alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789./'
    $bytes = New-Object byte[] 22
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    -join ($bytes | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
}

function Set-CurrentUserFileAcl {
    param([Parameter(Mandatory)][string]$Path)
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $Path /inheritance:r /grant:r "${identity}:(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to restrict local ACL: $Path" }
}

& $preflight -TargetGroup standby
if ($LASTEXITCODE -notin @(0, $null)) { throw 'Standby preflight failed.' }
& $preflight -TargetGroup platform
if ($LASTEXITCODE -notin @(0, $null)) { throw 'Platform preflight failed.' }

$configuration = Get-Content -LiteralPath $configurationFile -Raw | ConvertFrom-Json
$controller = "automation@$($configuration.controller_ip)"
$remoteRoot = '/home/automation/infrastructure-operations-platform'
$options = @('-i', $privateKey, '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=NUL', '-o', 'ConnectTimeout=10')
$utf8 = [Text.UTF8Encoding]::new($false)
New-Item -ItemType Directory -Path $groupVarsRoot -Force | Out-Null

$content = if (Test-Path -LiteralPath $groupVars) { Get-Content -LiteralPath $groupVars -Raw } else { "---`n" }
$pattern = '(?ms)^# BEGIN VALIDATION ADGUARD METRICS\r?\n.*?^# END VALIDATION ADGUARD METRICS\r?\n?'
$content = [regex]::Replace($content, $pattern, '')
$section = @"
# BEGIN VALIDATION ADGUARD METRICS
adguard_metrics_endpoint: "http://$($configuration.standby_ip)"
adguard_metrics_username: metrics
adguard_metrics_password: "{{ vault_adguard_metrics_password }}"
adguard_metrics_password_hash: "{{ vault_adguard_metrics_password_hash }}"
adguard_metrics_interval: 30s
# END VALIDATION ADGUARD METRICS
"@
[IO.File]::WriteAllText($groupVars, $content.TrimEnd() + "`n`n" + $section, $utf8)

$credentialValue = New-RandomSecret
$salt = New-BcryptSalt
[IO.File]::WriteAllText($additionsFile, "vault_adguard_metrics_password: `"$credentialValue`"`nvault_adguard_metrics_password_salt: `"$salt`"`n", $utf8)
Set-CurrentUserFileAcl $additionsFile

& ssh.exe @options $controller "install -d -m 0755 $remoteRoot/playbooks $remoteRoot/roles $remoteRoot/inventories/validation/group_vars/all; install -d -m 0700 /home/automation/.ansible; sudo chown -R automation:automation $remoteRoot/roles"
if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare the automation controller.' }
& scp.exe @options $vaultPasswordFile "${controller}:/tmp/platform-vault-password"
& scp.exe @options $additionsFile "${controller}:/tmp/adguard-metrics-vault-additions.yml"
if (Test-Path -LiteralPath $vaultFile) { & scp.exe @options $vaultFile "${controller}:/tmp/platform-vault.yml" }
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage Vault material.' }

$merge = @"
set -e
root=$remoteRoot
key=/home/automation/.ansible/vault-password
target=`$root/inventories/validation/group_vars/all/vault.yml
install -m 0600 /tmp/platform-vault-password `$key
if [ -s /tmp/platform-vault.yml ]; then
  ansible-vault decrypt /tmp/platform-vault.yml --vault-password-file `$key --output /tmp/platform-vault-plain.yml
else
  printf '%s\n' '---' > /tmp/platform-vault-plain.yml
fi
if ! grep -q '^vault_adguard_metrics_password:' /tmp/platform-vault-plain.yml; then
  cat /tmp/adguard-metrics-vault-additions.yml >> /tmp/platform-vault-plain.yml
  printf created > /tmp/adguard-metrics-secret-state
else
  printf existing > /tmp/adguard-metrics-secret-state
fi
if ! grep -q '^vault_adguard_metrics_password_hash:' /tmp/platform-vault-plain.yml; then
  python3 - /tmp/platform-vault-plain.yml <<'PY'
import crypt
import sys
import yaml

path = sys.argv[1]
with open(path, encoding='utf-8') as stream:
    values = yaml.safe_load(stream)
credential_value = values['vault_adguard_metrics_password']
salt = values['vault_adguard_metrics_password_salt']
credential_hash = crypt.crypt(credential_value, f'`$2b`$12`${salt}')
if not credential_hash.startswith('`$2b`$12`$'):
    raise SystemExit('bcrypt generation failed')
with open(path, 'a', encoding='utf-8') as stream:
    stream.write(f'vault_adguard_metrics_password_hash: "{credential_hash}"\n')
PY
fi
ansible-vault encrypt /tmp/platform-vault-plain.yml --vault-password-file `$key --output `$target
chmod 0600 `$target
rm -f /tmp/platform-vault.yml /tmp/platform-vault-plain.yml /tmp/platform-vault-password /tmp/adguard-metrics-vault-additions.yml
"@
[IO.File]::WriteAllText($mergeFile, ($merge -replace "`r`n", "`n"), $utf8)
Set-CurrentUserFileAcl $mergeFile
& scp.exe @options $mergeFile "${controller}:/tmp/adguard-metrics-merge-vault.sh"
& ssh.exe @options $controller 'bash /tmp/adguard-metrics-merge-vault.sh; rc=$?; rm -f /tmp/adguard-metrics-merge-vault.sh; exit $rc'
if ($LASTEXITCODE -ne 0) { throw 'Failed to merge the AdGuard metrics secret into Vault.' }
& scp.exe @options "${controller}:$remoteRoot/inventories/validation/group_vars/all/vault.yml" $vaultFile
if ($LASTEXITCODE -ne 0) { throw 'Failed to preserve encrypted Vault locally.' }
Set-CurrentUserFileAcl $vaultFile
$state = (& ssh.exe @options $controller 'cat /tmp/adguard-metrics-secret-state').Trim()
& ssh.exe @options $controller 'rm -f /tmp/adguard-metrics-secret-state'
Remove-Item -LiteralPath $additionsFile, $mergeFile -Force

if ($state -eq 'created') {
    [IO.File]::WriteAllText($credentialFile, "AdGuard URL: http://$($configuration.standby_ip)/`r`nUsername: metrics`r`nPassword: $credentialValue`r`nScope: administrative API capability; collector performs GET requests only.`r`n", $utf8)
    Set-CurrentUserFileAcl $credentialFile
} elseif (-not (Test-Path -LiteralPath $credentialFile)) {
    throw 'The metrics secret exists in Vault, but its local credential record is unavailable.'
}
$credentialValue = $null
$salt = $null

foreach ($copy in @(
    @{ Source = $playbook; Target = "$remoteRoot/playbooks/adguard-metrics.yml" },
    @{ Source = $inventory; Target = "$remoteRoot/inventories/validation/hosts.yml" },
    @{ Source = $groupVars; Target = "$remoteRoot/inventories/validation/group_vars/all/main.yml" }
)) {
    & scp.exe @options $copy.Source "${controller}:$($copy.Target)"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage $($copy.Source)." }
}
foreach ($role in @($userRole, $collectorRole)) {
    & scp.exe @options -r $role "${controller}:$remoteRoot/roles/"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage $role." }
}

$runs = if ($VerifyIdempotence) { 2 } else { 1 }
for ($run = 1; $run -le $runs; $run++) {
    Write-Host "Executing AdGuard metrics automation: pass $run of $runs."
    & ssh.exe @options $controller "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/adguard-metrics.yml"
    if ($LASTEXITCODE -ne 0) { throw "AdGuard metrics automation failed on pass $run." }
}

Write-Host "Technical identity record: $credentialFile"
Write-Warning 'Store this identity in the infrastructure password vault, then remove the local record.'
Write-Host 'AdGuard operational metrics validation completed successfully.' -ForegroundColor Green
