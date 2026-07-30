[CmdletBinding()]
param(
    [switch]$WriteGitHubOutput
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$images = [Collections.Generic.HashSet[string]]::new(
    [StringComparer]::Ordinal
)

$defaultFiles = Get-ChildItem -Path (Join-Path $projectRoot 'roles') `
    -Recurse -Filter 'main.yml' |
    Where-Object { $_.FullName -match '[\\/]defaults[\\/]main\.yml$' }

foreach ($file in $defaultFiles) {
    $lines = Get-Content -LiteralPath $file.FullName
    for ($index = 0; $index -lt $lines.Count; $index++) {
        if ($lines[$index] -notmatch '^[A-Za-z][A-Za-z0-9_]*_image:\s*(.*)$') {
            continue
        }

        $reference = $Matches[1].Trim().Trim('"', "'")
        if ($reference -in @('', '>-', '|-', '>', '|')) {
            if ($index + 1 -ge $lines.Count) {
                throw "Image reference has no value in $($file.FullName)."
            }
            $reference = $lines[++$index].Trim().Trim('"', "'")
        }
        if ($reference -notmatch '(:[^/]+|@sha256:[0-9a-fA-F]{64})$') {
            throw "Image reference is not pinned: $reference."
        }
        [void]$images.Add($reference)
    }
}

if ($images.Count -eq 0) {
    throw 'No container image references were discovered.'
}

$orderedImages = @($images | Sort-Object)
$json = ConvertTo-Json -InputObject $orderedImages -Compress

if ($WriteGitHubOutput) {
    if ([string]::IsNullOrWhiteSpace($env:GITHUB_OUTPUT)) {
        throw 'GITHUB_OUTPUT is required with -WriteGitHubOutput.'
    }
    "images=$json" | Out-File -LiteralPath $env:GITHUB_OUTPUT `
        -Encoding utf8 -Append
}

Write-Output $json
