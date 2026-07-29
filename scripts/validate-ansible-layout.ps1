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
    'automation/packer/rhel9/rhel9.pkr.hcl',
    'automation/packer/rhel9/variables.pkr.hcl',
    'automation/packer/rhel9/http/kickstart.cfg.pkrtpl',
    'automation/vagrant/Vagrantfile',
    'automation/scripts/Test-ValidationPrerequisites.ps1',
    'automation/scripts/Install-ValidationPrerequisites.ps1',
    'automation/scripts/Install-InfrastructureWorkstation.ps1',
    'automation/scripts/Run-ValidationPreflight.ps1',
    'automation/scripts/Run-ValidationBaseline.ps1',
    'automation/scripts/Run-ValidationDocker.ps1',
    'automation/scripts/Run-ValidationNetBox.ps1',
    'automation/scripts/Run-ValidationNetBoxBackup.ps1',
    'automation/scripts/Run-ValidationTraefik.ps1',
    'automation/scripts/Run-ValidationZabbix.ps1',
    'automation/scripts/Run-ValidationPortainer.ps1',
    'automation/scripts/Run-ValidationObservability.ps1',
    'automation/scripts/Initialize-Validation.ps1',
    'automation/scripts/Build-RhelBox.ps1',
    'automation/scripts/Register-RhelBox.ps1',
    'automation/scripts/Start-ValidationEnvironment.ps1',
    'playbooks/preflight.yml',
    'playbooks/bootstrap-rhel.yml',
    'playbooks/docker.yml',
    'playbooks/netbox.yml',
    'playbooks/netbox-backup.yml',
    'playbooks/traefik.yml',
    'playbooks/zabbix.yml',
    'playbooks/portainer.yml',
    'playbooks/observability.yml',
    'playbooks/platform.yml',
    'roles/rhel_baseline/defaults/main.yml',
    'roles/rhel_baseline/tasks/main.yml',
    'roles/docker_engine/defaults/main.yml',
    'roles/docker_engine/tasks/main.yml',
    'roles/netbox/defaults/main.yml',
    'roles/netbox/tasks/main.yml',
    'roles/netbox/templates/compose.yaml.j2',
    'roles/netbox_backup/defaults/main.yml',
    'roles/netbox_backup/tasks/main.yml',
    'roles/netbox_backup/templates/netbox-backup.sh.j2',
    'roles/traefik/defaults/main.yml',
    'roles/traefik/tasks/main.yml',
    'roles/traefik/README.md',
    'roles/traefik/templates/compose.yaml.j2',
    'roles/traefik/templates/traefik.yml.j2',
    'roles/traefik/templates/dynamic-security.yml.j2',
    'roles/zabbix/defaults/main.yml',
    'roles/zabbix/tasks/main.yml',
    'roles/zabbix/templates/compose.yaml.j2',
    'roles/zabbix/README.md',
    'roles/portainer/defaults/main.yml',
    'roles/portainer/tasks/main.yml',
    'roles/portainer/templates/compose.yaml.j2',
    'roles/portainer/README.md',
    'roles/observability/defaults/main.yml',
    'roles/observability/tasks/main.yml',
    'roles/observability/templates/compose.yaml.j2',
    'roles/observability/templates/prometheus.yml.j2',
    'roles/observability/templates/grafana-datasource.yml.j2',
    'roles/observability/templates/grafana-dashboards.yml.j2',
    'roles/observability/templates/infrastructure-host-containers.json.j2',
    'roles/observability/README.md'
)

foreach ($relativePath in $requiredPaths) {
    $fullPath = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $fullPath)) {
        $errors.Add("Caminho obrigatório ausente: $relativePath")
    }
}

$publishablePaths = & git -C $projectRoot ls-files --cached --others --exclude-standard
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to enumerate publishable files with Git.'
}

$yamlFiles = foreach ($relativePath in $publishablePaths) {
    if ([System.IO.Path]::GetExtension($relativePath) -in @('.yml', '.yaml')) {
        $fullPath = Join-Path $projectRoot $relativePath
        if (Test-Path -LiteralPath $fullPath -PathType Leaf) {
            Get-Item -LiteralPath $fullPath
        }
    }
}

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
    '<NETBOX_API_TOKEN_PEPPER>',
    '<POSTGRES_PASSWORD>',
    '<REDIS_PASSWORD>',
    '<REDIS_CACHE_PASSWORD>',
    '<NETBOX_ADMIN_PASSWORD>',
    '<TRAEFIK_DASHBOARD_BASIC_AUTH>',
    '<ZABBIX_DATABASE_PASSWORD>',
    '<ZABBIX_DATABASE_ROOT_PASSWORD>',
    '<ZABBIX_ADMIN_PASSWORD>',
    '<PORTAINER_ADMIN_PASSWORD>',
    '<GRAFANA_ADMIN_PASSWORD>'
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
