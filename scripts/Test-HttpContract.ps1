[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$ContractPath,

    [string]$EvidencePath
)

$ErrorActionPreference = 'Stop'
$contract = Get-Content -LiteralPath $ContractPath -Raw | ConvertFrom-Json
$errors = [Collections.Generic.List[string]]::new()
$evidence = [Collections.Generic.List[object]]::new()

if ($contract.schema -ne 'http-contract-v1') {
    throw 'Unsupported HTTP contract schema.'
}
if ($contract.endpoints.Count -eq 0) {
    throw 'The HTTP contract contains no endpoints.'
}

$curlCommand = Get-Command curl.exe -ErrorAction SilentlyContinue
if (-not $curlCommand) {
    $curlCommand = Get-Command curl -ErrorAction SilentlyContinue
}
if (-not $curlCommand) {
    throw 'curl is required to validate the HTTP contract.'
}

$temporaryRoot = Join-Path (
    [IO.Path]::GetTempPath()
) ("http-contract-" + [guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory -Path $temporaryRoot)

try {
    foreach ($endpoint in $contract.endpoints) {
        $safeName = ([string]$endpoint.name) -replace '[^A-Za-z0-9_-]', '_'
        $headerPath = Join-Path $temporaryRoot "$safeName.headers"
        $nullDevice = if ($IsLinux -or $IsMacOS) { '/dev/null' } else { 'NUL' }

        $timeoutSeconds = if (
            $endpoint.PSObject.Properties.Name -contains 'timeout_seconds'
        ) {
            [int]$endpoint.timeout_seconds
        } else {
            [int]$contract.defaults.timeout_seconds
        }
        $followRedirects = if (
            $endpoint.PSObject.Properties.Name -contains 'follow_redirects'
        ) {
            [bool]$endpoint.follow_redirects
        } else {
            [bool]$contract.defaults.follow_redirects
        }
        $tlsInsecure = if (
            $endpoint.PSObject.Properties.Name -contains 'tls_insecure'
        ) {
            [bool]$endpoint.tls_insecure
        } else {
            [bool]$contract.defaults.tls_insecure
        }

        $curlArguments = @(
            '--silent',
            '--show-error',
            '--max-time', [string]$timeoutSeconds,
            '--dump-header', $headerPath,
            '--output', $nullDevice,
            '--write-out', '%{http_code}'
        )
        if ($followRedirects) {
            $curlArguments += '--location'
        } else {
            $curlArguments += '--max-redirs'
            $curlArguments += '0'
        }
        if ($tlsInsecure) {
            $curlArguments += '--insecure'
        }
        $curlArguments += [string]$endpoint.url

        $statusOutput = & $curlCommand.Source @curlArguments
        $curlExitCode = $LASTEXITCODE
        $observedStatus = 0
        [void][int]::TryParse(
            ([string]$statusOutput).Trim(),
            [ref]$observedStatus
        )

        $headers = @{}
        if (Test-Path -LiteralPath $headerPath) {
            foreach ($line in Get-Content -LiteralPath $headerPath) {
                if ($line -match '^(?<name>[^:]+):\s*(?<value>.*)$') {
                    $headers[$Matches['name'].ToLowerInvariant()] =
                        $Matches['value'].Trim()
                }
            }
        }

        $checks = [ordered]@{
            curl_exit = ($curlExitCode -eq 0)
            status = ($observedStatus -in $endpoint.expected_status_codes)
            headers = $true
            redirect = $true
        }

        foreach ($requiredHeader in $endpoint.required_headers) {
            $headerName = ([string]$requiredHeader.name).ToLowerInvariant()
            if (-not $headers.ContainsKey($headerName) -or
                $headers[$headerName] -notmatch [string]$requiredHeader.pattern) {
                $checks.headers = $false
                $errors.Add(
                    "$($endpoint.name): required header failed: $headerName."
                )
            }
        }

        if ($endpoint.PSObject.Properties.Name -contains
            'expected_location_pattern') {
            $location = if ($headers.ContainsKey('location')) {
                [string]$headers['location']
            } else {
                ''
            }
            if ($location -notmatch [string]$endpoint.expected_location_pattern) {
                $checks.redirect = $false
                $errors.Add("$($endpoint.name): redirect location failed.")
            }
        }

        if (-not $checks.curl_exit) {
            $errors.Add("$($endpoint.name): curl failed with code $curlExitCode.")
        }
        if (-not $checks.status) {
            $errors.Add(
                "$($endpoint.name): unexpected HTTP status $observedStatus."
            )
        }

        $passed = -not ($checks.Values -contains $false)
        $evidence.Add([pscustomobject]@{
            name = [string]$endpoint.name
            observed_status = $observedStatus
            passed = $passed
            checks = $checks
        })
    }
} finally {
    if ($temporaryRoot.StartsWith([IO.Path]::GetTempPath())) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}

if ($EvidencePath) {
    $evidenceDirectory = Split-Path -Parent $EvidencePath
    if ($evidenceDirectory) {
        [void](New-Item -ItemType Directory -Path $evidenceDirectory -Force)
    }
    [ordered]@{
        schema = 'http-contract-evidence-v1'
        generated_at = [DateTime]::UtcNow.ToString('o')
        passed = ($errors.Count -eq 0)
        endpoints = $evidence
    } | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath $EvidencePath -Encoding utf8
}

if ($errors.Count -gt 0) {
    $errors | Sort-Object -Unique | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host "HTTP contract validated: $($evidence.Count) endpoints."
