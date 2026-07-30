[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$catalogPath = Join-Path $projectRoot 'config\container-privilege-policy.json'
$errors = [Collections.Generic.List[string]]::new()
$findings = [Collections.Generic.List[object]]::new()

$catalog = Get-Content -LiteralPath $catalogPath -Raw | ConvertFrom-Json
if ($catalog.schema -ne 'container-privilege-policy-v1') {
    $errors.Add('Unsupported container privilege policy schema.')
}
if ($catalog.policy.default_decision -ne 'deny') {
    $errors.Add('Container privilege policy must deny unregistered findings.')
}

$templates = Get-ChildItem -Path (Join-Path $projectRoot 'roles') `
    -Recurse -Filter 'compose.yaml.j2'

foreach ($template in $templates) {
    $relativePath = $template.FullName.Substring($projectRoot.Length + 1).
        Replace('\', '/')
    $service = ''
    $inServices = $false
    $inCapAdd = $false

    foreach ($line in Get-Content -LiteralPath $template.FullName) {
        if ($line -match '^services:\s*$') {
            $inServices = $true
            continue
        }
        if ($inServices -and $line -match '^[A-Za-z][A-Za-z0-9_-]*:\s*$') {
            $inServices = $false
            $service = ''
            $inCapAdd = $false
            continue
        }
        if (-not $inServices) {
            continue
        }
        if ($line -match '^  ([A-Za-z0-9_-]+):\s*$') {
            $service = $Matches[1]
            $inCapAdd = $false
            continue
        }
        if ($line -match '^\s{4}cap_add:\s*$') {
            $inCapAdd = $true
            continue
        }
        if ($inCapAdd -and $line -notmatch '^\s{6}-\s+') {
            $inCapAdd = $false
        }

        $control = $null
        $source = $null
        if ($line -match '^\s+privileged:\s*true\s*$') {
            $control = 'privileged'
        } elseif ($line -match '^\s+pid:\s*host\s*$') {
            $control = 'host-pid'
        } elseif ($inCapAdd -and $line -match '^\s+-\s+NET_BIND_SERVICE\s*$') {
            $control = 'capability-net-bind-service'
        } elseif ($line -match '^\s+-\s+/var/run/docker\.sock:/var/run/docker\.sock(?<options>.*)$') {
            $mountOptions = $Matches['options'].TrimStart(':')
            $control = if ($mountOptions -match '(^|,)ro($|,)') {
                'docker-socket-read'
            } else {
                'docker-socket-write'
            }
        } elseif ($line -match '^\s+-\s+(?<source>/[^:]*):(?<target>/[^:]+):ro(?:,.*)?\s*$') {
            $control = 'host-bind-read'
            $source = $Matches['source']
        } elseif ($line -match '^\s+-\s+(?<source>/dev/[^:]+):/dev/[^:]+\s*$') {
            $control = 'host-device'
            $source = $Matches['source']
        }

        if ($control) {
            $findings.Add([pscustomobject]@{
                template = $relativePath
                service = $service
                control = $control
                source = $source
            })
        }
    }
}

$acceptedKeys = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::Ordinal
)
$ids = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::Ordinal
)

foreach ($accepted in $catalog.accepted_findings) {
    if (-not $ids.Add([string]$accepted.id)) {
        $errors.Add("Duplicate accepted finding id: $($accepted.id).")
    }
    if ([int]$accepted.review_days -lt 1 -or
        [int]$accepted.review_days -gt
        [int]$catalog.policy.maximum_review_days) {
        $errors.Add("$($accepted.id): invalid review_days.")
    }
    if ($accepted.compensating_controls.Count -lt 2) {
        $errors.Add("$($accepted.id): at least two compensating controls required.")
    }
    $source = if ($accepted.PSObject.Properties.Name -contains 'source') {
        [string]$accepted.source
    } else {
        ''
    }
    $key = '{0}|{1}|{2}|{3}' -f
        $accepted.template,
        $accepted.service,
        $accepted.control,
        $source
    if (-not $acceptedKeys.Add($key)) {
        $errors.Add("Duplicate accepted privilege finding: $key.")
    }
}

$discoveredKeys = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::Ordinal
)
foreach ($finding in $findings) {
    $key = '{0}|{1}|{2}|{3}' -f
        $finding.template,
        $finding.service,
        $finding.control,
        $finding.source
    [void]$discoveredKeys.Add($key)
    if (-not $acceptedKeys.Contains($key)) {
        $errors.Add("Unregistered container privilege finding: $key.")
    }
}
foreach ($key in $acceptedKeys) {
    if (-not $discoveredKeys.Contains($key)) {
        $errors.Add("Accepted finding no longer exists in templates: $key.")
    }
}

if ($errors.Count -gt 0) {
    $errors | Sort-Object -Unique | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host (
    "Container privilege policy validated: {0} registered findings." -f
    $findings.Count
)
