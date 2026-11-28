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
$requirements = Join-Path $projectRoot 'requirements.yml'
$playbook = Join-Path $projectRoot 'playbooks\dns-standby.yml'
$role = Join-Path $projectRoot 'roles\dns_standby'
$preflight = Join-Path $PSScriptRoot 'Run-ValidationPreflight.ps1'
$bootstrapPolicy = Join-Path $validationRoot 'dns-bootstrap-policy.json'

foreach ($path in @($privateKey, $configPath, $requirements, $playbook, $preflight)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file not found: $path" }
}
if (-not (Test-Path -LiteralPath $role -PathType Container)) { throw "Required role not found: $role" }

& $preflight -TargetGroup standby
if ($LASTEXITCODE -notin @(0, $null)) { throw 'Standby preflight failed.' }

$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$standbyIp = [Net.IPAddress]::Parse($config.standby_ip)
$octets = $standbyIp.GetAddressBytes()
$allowedNetwork = "$($octets[0]).$($octets[1]).$($octets[2]).0/24"
$controller = "automation@$($config.controller_ip)"
$remoteRoot = '/home/automation/infrastructure-operations-platform'
$options = @('-i', $privateKey, '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=NUL')

New-Item -ItemType Directory -Path $groupVarsRoot -Force | Out-Null
$vars = @"
---
dns_standby_allowed_networks:
  - "$allowedNetwork"
dns_standby_admin_networks:
  - "$allowedNetwork"
"@
if (Test-Path -LiteralPath $bootstrapPolicy) {
    $policy = Get-Content -LiteralPath $bootstrapPolicy -Raw | ConvertFrom-Json
    if ($policy.enabled -ne $true -or @($policy.resolvers).Count -eq 0) {
        throw 'Invalid private bootstrap policy. Do not silently disable an installed guard.'
    }
    $resolverLines = foreach ($resolver in $policy.resolvers) {
        $address = [Net.IPAddress]::Parse([string]$resolver)
        if ($address.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
            throw 'This validation bootstrap policy requires IPv4 resolver addresses.'
        }
        "  - '$address'"
    }
    $vars += "`ndns_standby_bootstrap_guard: true`ndns_standby_expected_bootstrap_dns:`n" + ($resolverLines -join "`n") + "`n"
}
[IO.File]::WriteAllText($groupVars, $vars, [Text.UTF8Encoding]::new($false))

& ssh.exe @options $controller "install -d -m 0755 $remoteRoot/roles $remoteRoot/playbooks $remoteRoot/inventories/validation/group_vars/all"
if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare controller.' }
& scp.exe @options $requirements "${controller}:$remoteRoot/requirements.yml"
& scp.exe @options $playbook "${controller}:$remoteRoot/playbooks/dns-standby.yml"
& scp.exe @options $groupVars "${controller}:$remoteRoot/inventories/validation/group_vars/all/main.yml"
& scp.exe @options -r $role "${controller}:$remoteRoot/roles/"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage standby DNS automation.' }

$runs = if ($VerifyIdempotence) { 2 } else { 1 }
for ($run = 1; $run -le $runs; $run++) {
    $remote = @"
set -e
cd $remoteRoot
if [ -f /home/automation/.ansible/vault-password ]; then
  ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook --vault-password-file /home/automation/.ansible/vault-password -i inventories/validation/hosts.yml playbooks/dns-standby.yml
else
  ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook -i inventories/validation/hosts.yml playbooks/dns-standby.yml
fi
"@
    & ssh.exe @options $controller ($remote -replace "`r`n", "`n")
    if ($LASTEXITCODE -ne 0) { throw "Standby DNS deployment failed on pass $run." }
}
