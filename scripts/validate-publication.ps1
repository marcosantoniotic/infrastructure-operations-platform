[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

$forbiddenFilePatterns = @(
    '*.key',
    '*.pem',
    '*.p12',
    '*.pfx',
    '*.sql',
    '*.dump',
    'acme.json',
    '.env'
)

$forbiddenContentPatterns = @(
    '(?i)-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----',
    '(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*["'']?[A-Za-z0-9+/_.-]{12,}',
    '(?i)cf_api_token\s*[:=]',
    '(?i)authorization:\s*bearer\s+',
    '\b(?:\d{1,3}\.){3}\d{1,3}\b',
    '@(?:gmail|hotmail|outlook|msn)\.'
)

$errors = [System.Collections.Generic.List[string]]::new()
$publishablePaths = & git -C $projectRoot ls-files --cached --others --exclude-standard
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to enumerate publishable files with Git.'
}

$files = foreach ($relativePath in $publishablePaths) {
    $fullPath = Join-Path $projectRoot $relativePath
    if (Test-Path -LiteralPath $fullPath -PathType Leaf) {
        Get-Item -LiteralPath $fullPath -Force
    }
}

foreach ($pattern in $forbiddenFilePatterns) {
    foreach ($file in $files | Where-Object { $_.Name -like $pattern }) {
        if ($file.Name -eq '.env.example') {
            continue
        }
        $errors.Add("Arquivo proibido: $($file.FullName)")
    }
}

foreach ($file in $files) {
    $content = Get-Content -LiteralPath $file.FullName -Raw -ErrorAction SilentlyContinue
    if ($null -eq $content) {
        continue
    }
    foreach ($pattern in $forbiddenContentPatterns) {
        $contentToInspect = $content
        if ($pattern -eq '\b(?:\d{1,3}\.){3}\d{1,3}\b') {
            # Loopback is a public implementation constant, not infrastructure data.
            $contentToInspect = $contentToInspect -replace '\b127(?:\.\d{1,3}){3}\b', '<LOOPBACK>'
        }
        if ($pattern -match 'password\|passwd') {
            # HCL variable references are wiring, not embedded secret values.
            $contentToInspect = $contentToInspect -replace (
                '(?i)((?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*)' +
                'var\.[A-Za-z_][A-Za-z0-9_]*'
            ), '$1<VARIABLE_REFERENCE>'
        }
        if ($contentToInspect -match $pattern) {
            $errors.Add("Conteúdo potencialmente sensível em: $($file.FullName) (padrão: $pattern)")
        }
    }
}

$markdownFiles = $files | Where-Object { $_.Extension -eq '.md' }
foreach ($file in $markdownFiles) {
    $content = Get-Content -LiteralPath $file.FullName -Raw
    $matches = [regex]::Matches($content, '\[[^\]]+\]\(([^)]+)\)')
    foreach ($match in $matches) {
        $target = $match.Groups[1].Value
        if (
            $target -match '^(https?://|mailto:|#)' -or
            $target -match '^<' -or
            $target.Contains('#')
        ) {
            continue
        }

        $resolved = Join-Path $file.DirectoryName $target
        if (-not (Test-Path -LiteralPath $resolved)) {
            $errors.Add("Link relativo inexistente em $($file.FullName): $target")
        }
    }
}

if ($errors.Count -gt 0) {
    $errors | Sort-Object -Unique | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host "Validação concluída: nenhum indicador sensível conhecido foi encontrado."
