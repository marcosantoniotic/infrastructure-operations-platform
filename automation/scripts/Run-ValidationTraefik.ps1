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
$inventory = Join-Path $ansibleRoot 'hosts.yml'
$groupVarsRoot = Join-Path $ansibleRoot 'group_vars\all'
$groupVars = Join-Path $groupVarsRoot 'main.yml'
$vaultFile = Join-Path $groupVarsRoot 'vault.yml'
$vaultPasswordFile = Join-Path $ansibleRoot 'vault-password.txt'
$credentialFile = Join-Path $validationRoot 'traefik-initial-credentials.txt'
$requirements = Join-Path $projectRoot 'requirements.yml'
$playbook = Join-Path $projectRoot 'playbooks\traefik.yml'
$dockerRole = Join-Path $projectRoot 'roles\docker_engine'
$traefikRole = Join-Path $projectRoot 'roles\traefik'
$preflightRunner = Join-Path $PSScriptRoot 'Run-ValidationPreflight.ps1'

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
foreach ($path in @($dockerRole, $traefikRole)) {
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

function New-HtpasswdShaCredential {
    param(
        [Parameter(Mandatory)][string]$Username,
        [Parameter(Mandatory)][string]$Password
    )
    $sha1 = [Security.Cryptography.SHA1]::Create()
    try {
        $digest = $sha1.ComputeHash([Text.Encoding]::UTF8.GetBytes($Password))
    }
    finally {
        $sha1.Dispose()
    }
    return "${Username}:{SHA}$([Convert]::ToBase64String($digest))"
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
    throw 'Validation preflight failed before Traefik execution.'
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
$groupVarsContent = if (Test-Path -LiteralPath $groupVars) {
    Get-Content -LiteralPath $groupVars -Raw
}
else {
    "---`n"
}

$sectionPattern = '(?ms)^# BEGIN VALIDATION TRAEFIK\r?\n.*?^# END VALIDATION TRAEFIK\r?\n?'
$existingSection = [regex]::Match($groupVarsContent, $sectionPattern)
$existingHash = [regex]::Match(
    $existingSection.Value,
    '(?m)^traefik_dashboard_basic_auth:\s*[''"]?([^''"\r\n]+)'
)

if ($existingHash.Success) {
    $dashboardCredential = $existingHash.Groups[1].Value
}
else {
    $initialCredential = New-RandomSecret
    $dashboardCredential = New-HtpasswdShaCredential `
        -Username 'admin' `
        -Password $initialCredential
    [IO.File]::WriteAllText(
        $credentialFile,
        "URL (via SSH tunnel): http://traefik.localhost:8080/dashboard/`r`nUsername: admin`r`nPassword: $initialCredential`r`n",
        $utf8WithoutBom
    )
    Set-CurrentUserFileAcl -Path $credentialFile
}

$groupVarsContent = [regex]::Replace($groupVarsContent, $sectionPattern, '')
$traefikSection = @"
# BEGIN VALIDATION TRAEFIK
traefik_project_dir: /opt/traefik
traefik_image: traefik:v3.7.1
traefik_socket_proxy_image: >-
  ghcr.io/tecnativa/docker-socket-proxy@sha256:1f5038b54f06c3e18422902cf00ba21803d1c97805aae032e5e6673d532d3459
traefik_validation_image: traefik/whoami:v1.11.0
traefik_bind_address: 127.0.0.1
traefik_http_port: 8080
traefik_https_port: 8443
traefik_metrics_port: 8082
traefik_dashboard_hostname: traefik.localhost
traefik_validation_hostname: whoami.localhost
traefik_dashboard_basic_auth: '$dashboardCredential'
traefik_proxy_network: proxy
traefik_socket_network: socket-proxy
traefik_enable_https: false
traefik_redirect_http_to_https: false
traefik_enable_validation_service: true
# END VALIDATION TRAEFIK
"@
[IO.File]::WriteAllText(
    $groupVars,
    $groupVarsContent.TrimEnd() + "`n`n" + $traefikSection,
    $utf8WithoutBom
)

Write-Host 'Staging the Traefik module on AUTOMATION-CONTROLLER.'
& ssh.exe @commonOptions $controller `
    "install -d -m 0755 $remoteRoot/playbooks $remoteRoot/roles $remoteRoot/inventories/validation/group_vars/all"
if ($LASTEXITCODE -ne 0) { throw 'Failed to prepare remote directories.' }

& scp.exe @commonOptions $requirements "${controller}:$remoteRoot/requirements.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage requirements.yml.' }
& scp.exe @commonOptions $playbook "${controller}:$remoteRoot/playbooks/traefik.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the Traefik playbook.' }
& scp.exe @commonOptions $inventory "${controller}:$remoteRoot/inventories/validation/hosts.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the validation inventory.' }
& scp.exe @commonOptions $groupVars "${controller}:$remoteRoot/inventories/validation/group_vars/all/main.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to stage validation variables.' }

$vaultArgument = ''
if (
    (Test-Path -LiteralPath $vaultFile -PathType Leaf) -and
    (Test-Path -LiteralPath $vaultPasswordFile -PathType Leaf)
) {
    & scp.exe @commonOptions $vaultFile "${controller}:$remoteRoot/inventories/validation/group_vars/all/vault.yml"
    if ($LASTEXITCODE -ne 0) { throw 'Failed to stage the encrypted Vault.' }
    $vaultArgument = '--vault-password-file /home/automation/.ansible/vault-password'
}

foreach ($role in @($dockerRole, $traefikRole)) {
    & scp.exe @commonOptions -r $role "${controller}:$remoteRoot/roles/"
    if ($LASTEXITCODE -ne 0) { throw "Failed to stage role: $role" }
}

& ssh.exe @commonOptions $controller `
    "cd $remoteRoot && ansible-galaxy collection install -r requirements.yml"
if ($LASTEXITCODE -ne 0) { throw 'Failed to install required Ansible collections.' }

$runs = if ($VerifyIdempotence) { 2 } else { 1 }
for ($run = 1; $run -le $runs; $run++) {
    Write-Host "Executing Traefik automation: pass $run of $runs."
    & ssh.exe @commonOptions $controller `
        "cd $remoteRoot && ANSIBLE_ROLES_PATH=$remoteRoot/roles ansible-playbook $vaultArgument -i inventories/validation/hosts.yml playbooks/traefik.yml"
    if ($LASTEXITCODE -ne 0) {
        throw "Traefik automation failed on pass $run."
    }
}

if (Test-Path -LiteralPath $credentialFile) {
    Write-Host "Traefik initial credentials: $credentialFile"
    Write-Warning 'Store the credential in a password manager and remove the local credential file.'
}
Write-Host 'Traefik validation completed successfully.' -ForegroundColor Green
