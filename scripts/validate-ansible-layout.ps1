[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$errors = [System.Collections.Generic.List[string]]::new()

$requiredPaths = @(
    'ansible.cfg',
    'requirements.yml',
    'inventories/example/hosts.yml',
    'inventories/example/group_vars/all.yml',
    'inventories/example/group_vars/vault.example.yml',
    'inventories/validation/.gitkeep',
    'inventories/production/.gitkeep',
    'playbooks/preflight.yml',
    'playbooks/bootstrap-rhel.yml',
    'playbooks/docker.yml',
    'playbooks/netbox.yml',
    'playbooks/platform.yml',
    'roles/rhel_baseline/defaults/main.yml',
    'roles/rhel_baseline/tasks/main.yml',
    'roles/docker_engine/defaults/main.yml',
    'roles/docker_engine/tasks/main.yml',
    'roles/netbox/defaults/main.yml',
    'roles/netbox/tasks/main.yml',
    'roles/netbox/templates/compose.yaml.j2'
)

foreach ($relativePath in $requiredPaths) {
    $fullPath = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $fullPath)) {
        $errors.Add("Caminho obrigatório ausente: $relativePath")
    }
}

$yamlFiles = Get-ChildItem -LiteralPath $projectRoot -Recurse -File |
    Where-Object { $_.Extension -in @('.yml', '.yaml') }

foreach ($file in $yamlFiles) {
    $content = Get-Content -LiteralPath $file.FullName -Raw
    if ($content -match "`t") {
        $errors.Add("Tabulação encontrada em YAML: $($file.FullName)")
    }
    if (-not $content.TrimStart().StartsWith('---') -and $file.Name -ne 'compose.yaml.j2') {
        $errors.Add("YAML sem marcador inicial ---: $($file.FullName)")
    }
}

$exampleVars = @(
    Get-Content -LiteralPath (
        Join-Path $projectRoot 'inventories/example/hosts.yml'
    ) -Raw
    Get-Content -LiteralPath (
        Join-Path $projectRoot 'inventories/example/group_vars/all.yml'
    ) -Raw
    Get-Content -LiteralPath (
        Join-Path $projectRoot 'inventories/example/group_vars/vault.example.yml'
    ) -Raw
) -join "`n"

$requiredPlaceholders = @(
    '<VALIDATION_SERVER_ADDRESS>',
    '<ADMIN_USER>',
    '<BASE_DOMAIN>',
    '<NETBOX_SECRET_KEY>',
    '<POSTGRES_PASSWORD>',
    '<REDIS_PASSWORD>',
    '<REDIS_CACHE_PASSWORD>',
    '<NETBOX_ADMIN_PASSWORD>'
)

foreach ($placeholder in $requiredPlaceholders) {
    if (-not $exampleVars.Contains($placeholder)) {
        $errors.Add("Placeholder público obrigatório ausente: $placeholder")
    }
}

if ($errors.Count -gt 0) {
    $errors | Sort-Object -Unique | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host "Estrutura Ansible validada."
