[CmdletBinding()]
param(
    [switch]$VerifyIdempotence
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$validationRoot = Join-Path $projectRoot '.validation'
$privateKey = Join-Path $validationRoot 'id_ed25519'
$vagrantConfig = Join-Path $validationRoot 'vagrant.json'
$ansibleRoot = Join-Path $validationRoot 'ansible'
$groupVarsRoot = Join-Path $ansibleRoot 'group_vars\all'
$groupVars = Join-Path $groupVarsRoot 'main.yml'
$requirements = Join-Path $projectRoot 'requirements.yml'
$playbook = Join-Path $projectRoot 'playbooks\docker.yml'
$role = Join-Path $projectRoot 'roles\docker_engine'
$preflightRunner = Join-Path $PSScriptRoot 'Run-ValidationPreflight.ps1'

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
if (-not (Test-Path -LiteralPath $role -PathType Container)) {
    throw "Required role not found: $role"
}

& $preflightRunner
if ($LASTEXITCODE -notin @(0, $null)) {
    throw 'Validation preflight failed before Docker execution.'
}

$configuration = Get-Content -LiteralPath $vagrantConfig -Raw | ConvertFrom-Json
$controllerAddress = $configuration.controller_ip
$adminUsername = 'automation'
$controller = "$adminUsername@$controllerAddress"
$remoteRoot = "/home/$adminUsername/infrastructure-operations-platform"

New-Item -ItemType Directory -Path $groupVarsRoot -Force | Out-Null
$groupVarsContent = @'
---
docker_users:
  - automation
docker_daemon_config:
  log-driver: json-file
  log-opts:
    max-size: 10m
    max-file: "3"
  live-restore: true
'@
$utf8WithoutBom = New-Object System.Text.UTF8Encoding -ArgumentList $false
[System.IO.File]::WriteAllText($groupVars, $groupVarsContent, $utf8WithoutBom)

$commonOptions = @(
    '-i', $privateKey,
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL',
    '-o', 'ConnectTimeout=10'
)

Write-Host 'Staging Docker automation on the controller.'
& ssh.exe @commonOptions $controller `
    "rm -f $remoteRoot/inventories/validation/group_vars/all.yml; install -d -m 0755 $remoteRoot/roles $remoteRoot/inventories/validation/group_vars/all"
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to prepare Docker directories on the controller.'
}

& scp.exe @commonOptions $requirements "${controller}:$remoteRoot/requirements.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage requirements.yml.' }
& scp.exe @commonOptions $playbook "${controller}:$remoteRoot/playbooks/docker.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Docker playbook.' }
& scp.exe @commonOptions $groupVars `
    "${controller}:$remoteRoot/inventories/validation/group_vars/all/main.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage Docker variables.' }
& scp.exe @commonOptions -r $role "${controller}:$remoteRoot/roles/"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the docker_engine role.' }

& ssh.exe @commonOptions $controller `
    "cd $remoteRoot && ansible-galaxy collection install -r requirements.yml"
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to install required Ansible collections.'
}

$runs = if ($VerifyIdempotence) { 2 } else { 1 }
for ($run = 1; $run -le $runs; $run++) {
    Write-Host "Executing Docker automation: pass $run of $runs."
    & ssh.exe @commonOptions $controller `
        "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook -i inventories/validation/hosts.yml playbooks/docker.yml"
    if ($LASTEXITCODE -ne 0) {
        throw "Docker automation failed on pass $run."
    }
}

Write-Host 'Docker validation completed successfully.' -ForegroundColor Green
