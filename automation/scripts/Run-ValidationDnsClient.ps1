[CmdletBinding()]
param([switch]$VerifyIdempotence)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$validationRoot = Join-Path $projectRoot '.validation'
$privateKey = Join-Path $validationRoot 'id_ed25519'
$configPath = Join-Path $validationRoot 'vagrant.json'
$ansibleRoot = Join-Path $validationRoot 'ansible'
$groupVarsRoot = Join-Path $ansibleRoot 'group_vars\all'
$groupVars = Join-Path $groupVarsRoot 'main.yml'
$playbook = Join-Path $projectRoot 'playbooks\dns-client.yml'
$role = Join-Path $projectRoot 'roles\dns_client'
$preflight = Join-Path $PSScriptRoot 'Run-ValidationPreflight.ps1'

foreach ($path in @($privateKey, $configPath, $playbook, $preflight)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required file not found: $path"
    }
}
if (-not (Test-Path -LiteralPath $role -PathType Container)) {
    throw "Required role not found: $role"
}

& $preflight -TargetGroup platform
if ($LASTEXITCODE -notin @(0, $null)) { throw 'Platform preflight failed.' }

$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$controller = "automation@$($config.controller_ip)"
$remoteRoot = '/home/automation/infrastructure-operations-platform'
$options = @(
    '-i', $privateKey,
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL',
    '-o', 'ConnectTimeout=10'
)

New-Item -ItemType Directory -Path $groupVarsRoot -Force | Out-Null
$vars = @"
---
dns_client_connection_name: "System ens192"
dns_client_interface: ens192
dns_client_servers:
  - "$($config.standby_ip)"
dns_client_priority: -50
dns_client_ignore_auto_dns: true
dns_client_resolution_test_name: example.com
dns_client_block_test_name: doubleclick.net
"@
[IO.File]::WriteAllText($groupVars, $vars, [Text.UTF8Encoding]::new($false))

& ssh.exe @options $controller `
    "install -d -m 0755 $remoteRoot/roles $remoteRoot/playbooks $remoteRoot/inventories/validation/group_vars/all"
if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare the controller.' }
& scp.exe @options $playbook "${controller}:$remoteRoot/playbooks/dns-client.yml"
& scp.exe @options $groupVars "${controller}:$remoteRoot/inventories/validation/group_vars/all/main.yml"
& scp.exe @options -r $role "${controller}:$remoteRoot/roles/"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage managed DNS client automation.' }

$runs = if ($VerifyIdempotence) { 2 } else { 1 }
for ($run = 1; $run -le $runs; $run++) {
    Write-Host "Executing managed DNS client automation: pass $run of $runs."
    $remote = @"
set -e
cd $remoteRoot
if [ -f /home/automation/.ansible/vault-password ]; then
  ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/dns-client.yml
else
  ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook -i inventories/validation/hosts.yml playbooks/dns-client.yml
fi
"@
    & ssh.exe @options $controller ($remote -replace "`r`n", "`n")
    if ($LASTEXITCODE -ne 0) { throw "Managed DNS client automation failed on pass $run." }
}
