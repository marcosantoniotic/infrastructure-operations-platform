[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$catalogPath = Join-Path $projectRoot 'config\credential-catalog.json'
$vaultExamplePath = Join-Path (
    $projectRoot
) 'inventories\example\group_vars\all\vault.example.yml'
$errors = [Collections.Generic.List[string]]::new()

$catalog = Get-Content -LiteralPath $catalogPath -Raw |
    ConvertFrom-Json
$vaultExample = Get-Content -LiteralPath $vaultExamplePath -Raw

if ($catalog.schema -ne 'infrastructure-credential-catalog-v1') {
    $errors.Add('Unsupported credential catalog schema.')
}
if ($catalog.policy.values_permitted -ne $false) {
    $errors.Add('The public credential catalog must prohibit secret values.')
}

$requiredProperties = @(
    'id',
    'vault_variable',
    'system',
    'kind',
    'owner_role',
    'purpose',
    'privilege',
    'rotation',
    'materialization',
    'restart_required'
)
$ids = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::Ordinal
)
$catalogVaultVariables = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::Ordinal
)

foreach ($credential in $catalog.managed_credentials) {
    foreach ($property in $requiredProperties) {
        if (-not $credential.PSObject.Properties.Name.Contains($property)) {
            $errors.Add("$($credential.id): missing property $property.")
        }
    }
    if (-not $ids.Add([string]$credential.id)) {
        $errors.Add("Duplicate credential id: $($credential.id).")
    }
    if (-not $catalogVaultVariables.Add([string]$credential.vault_variable)) {
        $errors.Add("Duplicate Vault variable: $($credential.vault_variable).")
    }
    if ($credential.vault_variable -notmatch '^vault_[a-z0-9_]+$') {
        $errors.Add("$($credential.id): invalid Vault variable name.")
    }
    if ($credential.rotation.mode -notin @(
        'periodic',
        'event-driven',
        'provider-managed'
    )) {
        $errors.Add("$($credential.id): invalid rotation mode.")
    }
    if ([int]$credential.rotation.review_days -lt 1 -or
        [int]$credential.rotation.review_days -gt 365) {
        $errors.Add("$($credential.id): review_days must be between 1 and 365.")
    }
    if ($credential.rotation.mode -eq 'periodic' -and (
        [int]$credential.rotation.max_age_days -lt 1 -or
        [int]$credential.rotation.max_age_days -gt
        [int]$catalog.policy.maximum_periodic_rotation_days
    )) {
        $errors.Add("$($credential.id): invalid periodic max_age_days.")
    }
}

$declaredVaultVariables = [regex]::Matches(
    $vaultExample,
    '(?m)^(vault_[a-z0-9_]+):'
) | ForEach-Object { $_.Groups[1].Value }

foreach ($vaultVariable in $declaredVaultVariables) {
    if (-not $catalogVaultVariables.Contains($vaultVariable)) {
        $errors.Add("Vault variable is missing from catalog: $vaultVariable.")
    }
}
foreach ($vaultVariable in $catalogVaultVariables) {
    if ($vaultVariable -notin $declaredVaultVariables) {
        $errors.Add("Catalog variable is absent from Vault example: $vaultVariable.")
    }
}

$forbiddenPropertyNames = @(
    'value',
    'password',
    'token',
    'secret',
    'client_secret',
    'refresh_token'
)
$catalog.managed_credentials + $catalog.external_credentials |
    ForEach-Object {
        foreach ($propertyName in $_.PSObject.Properties.Name) {
            if ($propertyName -in $forbiddenPropertyNames) {
                $errors.Add(
                    "$($_.id): forbidden value-bearing property $propertyName."
                )
            }
        }
    }

if ($errors.Count -gt 0) {
    $errors | Sort-Object -Unique | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host (
    "Credential governance validated: {0} managed, {1} external metadata records." -f
    $catalog.managed_credentials.Count,
    $catalog.external_credentials.Count
)
