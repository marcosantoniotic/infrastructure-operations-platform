[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$errors = [System.Collections.Generic.List[string]]::new()
$definitions = @{}

$defaultFiles = Get-ChildItem -Path (Join-Path $projectRoot 'roles') `
    -Recurse -Filter 'main.yml' |
    Where-Object { $_.FullName -match '[\\/]defaults[\\/]main\.yml$' }

foreach ($file in $defaultFiles) {
    $lines = Get-Content -LiteralPath $file.FullName
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -notmatch '^([A-Za-z][A-Za-z0-9_]*_image):\s*(.*)$') {
            continue
        }

        $variable = $Matches[1]
        $reference = $Matches[2].Trim().Trim('"', "'")
        if ($reference -in @('', '>-', '|-', '>', '|')) {
            if ($index + 1 -ge $lines.Count) {
                $errors.Add("$variable has no container image value in $($file.FullName)")
                continue
            }
            $reference = $lines[++$index].Trim().Trim('"', "'")
        }

        $definitions[$variable] = @{
            Reference = $reference
            File = $file.FullName
        }

        if ($reference -match '@sha256:[0-9a-fA-F]{64}$') {
            continue
        }

        $lastSegment = ($reference -split '/')[-1]
        if ($lastSegment -notmatch '^(?<name>[^:]+):(?<tag>[^:]+)$') {
            $errors.Add("$variable must use an explicit tag or sha256 digest: $reference")
            continue
        }
        if ($Matches['tag'] -eq 'latest') {
            $errors.Add("$variable must not use the mutable latest tag: $reference")
        }
    }
}

$templateFiles = Get-ChildItem -Path (Join-Path $projectRoot 'roles') `
    -Recurse -Filter '*.j2'
foreach ($file in $templateFiles) {
    $content = Get-Content -LiteralPath $file.FullName -Raw
    $matches = [regex]::Matches(
        $content,
        '{{\s*([A-Za-z][A-Za-z0-9_]*_image)\s*}}'
    )
    foreach ($match in $matches) {
        $variable = $match.Groups[1].Value
        if (-not $definitions.ContainsKey($variable)) {
            $errors.Add(
                "Image variable $variable used without a pinned default in $($file.FullName)"
            )
        }
    }
}

if ($definitions.Count -eq 0) {
    $errors.Add('No container image definitions were discovered.')
}

if ($errors.Count -gt 0) {
    $errors | Sort-Object -Unique | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host (
    "Container image validation completed: {0} pinned references." -f
    $definitions.Count
)
