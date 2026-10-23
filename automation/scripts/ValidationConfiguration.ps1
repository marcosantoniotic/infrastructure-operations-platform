# Pure configuration helpers; dot-sourcing this file never connects to a host.
function Get-ValidationServiceAddress {
    param([Parameter(Mandatory)]$Configuration,
          [Parameter(Mandatory)][ValidateSet('srv01-validation','srv02-standby')][string]$Machine)
    $fallback = if ($Machine -eq 'srv01-validation') { $Configuration.platform_ip } else { $Configuration.standby_ip }
    $cidr = $Configuration.infrastructure_network.addresses.$Machine
    if (-not $cidr) { return $fallback }
    $parts = "$cidr".Split('/')
    $ip = $null; $prefix = 0
    if ($parts.Count -ne 2 -or -not [Net.IPAddress]::TryParse($parts[0],[ref]$ip) -or
        $ip.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork -or
        -not [int]::TryParse($parts[1],[ref]$prefix) -or $prefix -lt 1 -or $prefix -gt 32) {
        throw 'Infrastructure service address must be an IPv4 CIDR.'
    }
    return $ip.ToString()
}

function Get-ValidationOverrideFiles {
    param([Parameter(Mandatory)][string]$ProjectRoot)
    $directory = Join-Path $ProjectRoot '.validation/ansible/group_vars/all'
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) { return }
    Get-ChildItem -LiteralPath $directory -File | Where-Object {
        $_.Name -match '^[A-Za-z0-9][A-Za-z0-9_.-]*\.ya?ml$' -and
        $_.Name -notmatch '^(main|vault)\.ya?ml$'
    } | Sort-Object Name | ForEach-Object {
        if ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Override links are not allowed.' }
        $_
    }
}

function Sync-ValidationOverrides {
    param([Parameter(Mandatory)][string]$ProjectRoot,
          [Parameter(Mandatory)][string]$Controller,
          [Parameter(Mandatory)][string]$RemoteRoot,
          [Parameter(Mandatory)][object[]]$SshOptions)
    if ($Controller -notmatch '^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+$' -or
        $RemoteRoot -notmatch '^/home/[A-Za-z0-9._-]+/infrastructure-operations-platform$') {
        throw 'Invalid validation staging destination.'
    }
    $filters = Join-Path $ProjectRoot 'filter_plugins'
    if (-not (Test-Path -LiteralPath $filters -PathType Container)) { throw 'Required validation safety filters are missing.' }
    & scp.exe @SshOptions -r $filters "${Controller}:$RemoteRoot/playbooks/"
    if ($LASTEXITCODE -ne 0) { throw 'Validation safety filter transfer failed; refusing to deploy.' }
    foreach ($file in @(Get-ValidationOverrideFiles -ProjectRoot $ProjectRoot)) {
        & scp.exe @SshOptions $file.FullName "${Controller}:$RemoteRoot/inventories/validation/group_vars/all/$($file.Name)"
        if ($LASTEXITCODE -ne 0) { throw 'Private validation override transfer failed; refusing to deploy.' }
    }
    # Never delete remote files automatically. Removing an override requires review.
}
