[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$workflowRoot = Join-Path $projectRoot '.github\workflows'
$errors = [Collections.Generic.List[string]]::new()
$references = 0

Get-ChildItem -LiteralPath $workflowRoot -File |
    Where-Object { $_.Extension -in @('.yml', '.yaml') } |
    ForEach-Object {
        $file = $_
        $lineNumber = 0
        foreach ($line in Get-Content -LiteralPath $file.FullName) {
            $lineNumber++
            if ($line -notmatch '^\s*uses:\s*(?<reference>\S+)') {
                continue
            }
            $references++
            $reference = $Matches['reference']
            if ($reference.StartsWith('./') -or
                $reference.StartsWith('docker://')) {
                continue
            }
            if ($reference -notmatch '^[^@\s]+@[0-9a-fA-F]{40}$') {
                $errors.Add(
                    "$($file.Name):$lineNumber action is not pinned by commit SHA: $reference"
                )
            }
        }
    }

if ($references -eq 0) {
    $errors.Add('No GitHub Action references were discovered.')
}
if ($errors.Count -gt 0) {
    $errors | Sort-Object -Unique | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host "GitHub Actions validated: $references immutable references."
