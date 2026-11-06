[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('baseline','create-seed','start-agent','clean-running','clean-stopped','crash-alpha','quick-clean','restart-agent','beta-manual','beta-auto','beta-remove','beta-recreate','pending-alpha','firewall-block','firewall-allow','custom-emit','custom-rotate','custom-deny','custom-restore','export','stop-owned')][string]$Action,
    [Parameter(Mandatory)][ValidatePattern('^[0-9]{4}$')][string]$Sequence,
    [Parameter(Mandatory)][ValidatePattern('^wsp-native-[a-f0-9]{16}$')][string]$Owner
)
$ErrorActionPreference='Stop'
$work='C:\IOPWspNative'
if ($env:COMPUTERNAME -ne 'IOP-WSP-NATIVE' -or (Get-CimInstance Win32_ComputerSystem).PartOfDomain) { throw 'Not the owned, non-domain disposable Windows VM.' }
$inputData=Get-Content -LiteralPath "$work\fixture-input.private.json" -Raw | ConvertFrom-Json
if ($inputData.RunId -ne $Owner) { throw 'Fixture ownership mismatch.' }
$allowed=@('IOPWspNativeAlpha','IOPWspNativeBeta')
$exe="$work\NativeServiceFixture.exe"
$agent=(Get-Content -LiteralPath "$work\agent-path.txt" -Raw).Trim()
$record=@{Action=$Action;Sequence=$Sequence;Owner=$Owner;StartedUtc=[DateTime]::UtcNow.ToString('o');Success=$false}
$evidence="$work\evidence"
New-Item -ItemType Directory -Path $evidence -Force | Out-Null
function Owned-Service([string]$name) {
    if ($name -notin $allowed) { throw 'Unapproved service name.' }
    $s=Get-CimInstance Win32_Service -Filter "Name='$name'"
    if ($s -and ($s.PathName -ne ('"'+$exe+'" '+$name) -or $s.Description -ne $Owner)) { throw 'Existing service is not owned by this fixture.' }
    return $s
}
function Set-Mode([string]$name,[string]$mode) {
    $null=Owned-Service $name
    $mode | Set-Content -LiteralPath "$work\$name.mode" -Encoding ASCII
}
function Start-Owned([string]$name,[string]$mode) {
    $s=Owned-Service $name
    if (-not $s) { throw 'Owned service missing.' }
    if ($s.State -ne 'Stopped') { Stop-Service -Name $name -ErrorAction Stop }
    Set-Mode $name $mode
    & sc.exe start $name | Out-File -LiteralPath "$evidence\sc-start-$Sequence-$name.txt"
    if ($LASTEXITCODE -ne 0) { throw 'Owned fixture start rejected.' }
}
function Stop-Owned([string]$name) {
    $s=Owned-Service $name
    if ($s -and $s.State -ne 'Stopped') { Stop-Service -Name $name -ErrorAction Stop }
}
function Create-Owned([string]$name,[string]$display) {
    if (Owned-Service $name) { throw 'Refusing to overwrite an existing owned service.' }
    Set-Mode $name 'clean'
    New-Service -Name $name -BinaryPathName ('"'+$exe+'" '+$name) -DisplayName $display -Description $Owner -StartupType Automatic | Out-Null
}
function Owned-Agent {
    $s=Get-CimInstance Win32_Service -Filter "Name='Zabbix Agent 2'"
    if ($s -and ($s.PathName -notlike '*IOPWspNative*' -or $s.StartName -ne 'LocalSystem')) { throw 'Not the fixture agent.' }
    return $s
}
function Emit-Owned([string]$message) {
    if (-not [Diagnostics.EventLog]::SourceExists('IOPWspNativeSource')) { throw 'Owned event source missing.' }
    [Diagnostics.EventLog]::WriteEntry('IOPWspNativeSource',$message,[Diagnostics.EventLogEntryType]::Information,1201)
}
try {
    switch ($Action) {
        'baseline' {
            $record.System=(Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber,OSArchitecture)
            $record.Protected=Get-CimInstance Win32_Service -Filter "Name='AppXSvc' OR Name='InventorySvc'" | Select-Object Name,DisplayName,State,StartMode,ExitCode,ServiceSpecificExitCode,StartName
            $record.Network=Get-NetIPConfiguration | Select-Object InterfaceAlias,IPv4Address,IPv4DefaultGateway,DNSServer
            $record.DefaultRoutes=@(Get-NetRoute -AddressFamily IPv4 | Where-Object DestinationPrefix -eq '0.0.0.0/0').Count
            if ($record.DefaultRoutes -ne 0) { throw 'Unexpected default route.' }
        }
        'create-seed' {
            if (-not (Test-Path -LiteralPath $exe)) {
                $compiler="$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
                & $compiler /nologo /target:exe "/out:$exe" /reference:System.ServiceProcess.dll "$work\NativeServiceFixture.cs" | Out-File "$evidence\compile.txt"
                if ($LASTEXITCODE -ne 0) { throw 'Owned service compilation failed.' }
            }
            $alpha='IOP Synthetic [Alpha] (a'+[char]0xe7+[char]0xe3+'o) +'
            $beta='IOP Synthetic (Beta) ['+[char]0xe9+'] ?'
            Create-Owned $allowed[0] $alpha; Create-Owned $allowed[1] $beta
            if ([Diagnostics.EventLog]::SourceExists('IOPWspNativeSource') -or [Diagnostics.EventLog]::Exists('IOPWspNative')) { throw 'Refusing existing event log/source.' }
            New-EventLog -LogName IOPWspNative -Source IOPWspNativeSource
            Emit-Owned ('IOP fixture '+$Owner+' old event before skip')
            Start-Owned $allowed[0] 'crash'
            Start-Sleep -Seconds 11
            $record.SeedEvents=@(Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='Service Control Manager';Id=7031,7034,7023,7024} -ErrorAction SilentlyContinue | Where-Object Message -match 'IOP Synthetic' | Select-Object Id,RecordId,TimeCreated,ProviderName,Message)
            if ($record.SeedEvents.Count -lt 1) { throw 'No genuine SCM seed failure observed.' }
            $record.Synthetic=Get-CimInstance Win32_Service -Filter "Name='IOPWspNativeAlpha' OR Name='IOPWspNativeBeta'" | Select-Object Name,DisplayName,State,StartMode,ExitCode,ServiceSpecificExitCode
        }
        'start-agent' {
            if (Owned-Agent) { throw 'Agent already installed.' }
            & $agent -i -c "$work\agent.conf" 2>&1 | Out-File "$evidence\agent-install.txt"
            if ($LASTEXITCODE -ne 0) { throw 'Native agent installation failed.' }
            $null=Owned-Agent
            Start-Service -Name 'Zabbix Agent 2'
        }
        'clean-running' { foreach ($name in $allowed) { Start-Owned $name 'clean' } }
        'clean-stopped' { foreach ($name in $allowed) { Stop-Owned $name } }
        'crash-alpha' { Start-Owned $allowed[0] 'crash' }
        'quick-clean' { Start-Owned $allowed[0] 'clean'; Stop-Owned $allowed[0] }
        'restart-agent' { if (-not (Owned-Agent)) { throw 'Agent missing.' }; Restart-Service -Name 'Zabbix Agent 2' }
        'beta-manual' { $null=Owned-Service $allowed[1]; Set-Service -Name $allowed[1] -StartupType Manual }
        'beta-auto' { $null=Owned-Service $allowed[1]; Set-Service -Name $allowed[1] -StartupType Automatic }
        'beta-remove' { Stop-Owned $allowed[1]; $s=Owned-Service $allowed[1]; if (-not $s) { throw 'Owned beta missing.' }; & sc.exe delete $allowed[1] | Out-File "$evidence\beta-delete.txt"; if ($LASTEXITCODE -ne 0) { throw 'Owned beta deletion failed.' } }
        'beta-recreate' { Create-Owned $allowed[1] ('IOP Synthetic (Beta) ['+[char]0xe9+'] ?') }
        'pending-alpha' { Start-Owned $allowed[0] 'pending' }
        'firewall-block' { Disable-NetFirewallRule -DisplayName 'IOP owned fixture Agent active PSK only' }
        'firewall-allow' { Enable-NetFirewallRule -DisplayName 'IOP owned fixture Agent active PSK only' }
        'custom-emit' { Emit-Owned ('IOP fixture '+$Owner+' new '+$Sequence) }
        'custom-rotate' {
            if (-not [Diagnostics.EventLog]::Exists('IOPWspNative')) { throw 'Owned log missing.' }
            & wevtutil.exe epl IOPWspNative "$evidence\owned-before-rotation.evtx"
            if ($LASTEXITCODE -ne 0) { throw 'Owned log export failed.' }
            $record.ArchiveSha256=(Get-FileHash "$evidence\owned-before-rotation.evtx").Hash
            $record.ArchiveRecords=@(Get-WinEvent -Path "$evidence\owned-before-rotation.evtx" -ErrorAction Stop).Count
            if ($record.ArchiveRecords -lt 1) { throw 'Owned log archive is empty.' }
            & wevtutil.exe cl IOPWspNative
            if ($LASTEXITCODE -ne 0) { throw 'Owned log rotation failed.' }
            Emit-Owned ('IOP fixture '+$Owner+' after rotation '+$Sequence)
        }
        'custom-deny' {
            $log=Get-WinEvent -ListLog IOPWspNative
            $log.SecurityDescriptor | Set-Content -LiteralPath "$work\owned-channel-original.sddl" -Encoding ASCII
            & wevtutil.exe sl IOPWspNative '/ca:O:BAG:SYD:(D;;0x1;;;SY)(A;;0x7;;;BA)'
            if ($LASTEXITCODE -ne 0) { throw 'Owned log ACL change failed.' }
            if (-not (Owned-Agent)) { throw 'Owned agent missing.' }; Restart-Service 'Zabbix Agent 2'
        }
        'custom-restore' {
            $sddl=(Get-Content "$work\owned-channel-original.sddl" -Raw).Trim()
            & wevtutil.exe sl IOPWspNative "/ca:$sddl"
            if ($LASTEXITCODE -ne 0) { throw 'Owned log ACL restoration failed.' }
            if (-not (Owned-Agent)) { throw 'Owned agent missing.' }; Restart-Service 'Zabbix Agent 2'
            Emit-Owned ('IOP fixture '+$Owner+' access restored '+$Sequence)
        }
        'export' {
            foreach ($log in @('System','IOPWspNative')) {
                & wevtutil.exe epl $log "$evidence\$log-final.evtx"
                if ($LASTEXITCODE -ne 0) { throw 'Native event history export failed.' }
            }
            Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='Service Control Manager';Id=7000,7001,7009,7011,7022,7023,7024,7031,7034,7036} -ErrorAction SilentlyContinue |
                Where-Object Message -match 'IOP Synthetic' | Select-Object Id,RecordId,TimeCreated,ProviderName,Message |
                ConvertTo-Json -Depth 5 | Set-Content "$evidence\genuine-scm-events.json" -Encoding UTF8
            $record.EventArchives=Get-ChildItem $evidence -Filter '*.evtx' | Get-FileHash -Algorithm SHA256
            $record.Agent=Owned-Agent | Select-Object Name,StartName,State,PathName
            $record.Protected=Get-CimInstance Win32_Service -Filter "Name='AppXSvc' OR Name='InventorySvc'" | Select-Object Name,DisplayName,State,StartMode,ExitCode,ServiceSpecificExitCode
        }
        'stop-owned' {
            Enable-NetFirewallRule -DisplayName 'IOP owned fixture Agent active PSK only'
            if (Test-Path "$work\owned-channel-original.sddl") {
                $sddl=(Get-Content "$work\owned-channel-original.sddl" -Raw).Trim(); & wevtutil.exe sl IOPWspNative "/ca:$sddl"
                if ($LASTEXITCODE -ne 0) { throw 'Owned log ACL cleanup failed.' }
            }
            foreach ($name in $allowed) { Stop-Owned $name }
            if (Owned-Agent) { Stop-Service -Name 'Zabbix Agent 2' }
        }
    }
    $record.Success=$true
} catch { $record.Error=$_.Exception.Message; throw }
finally {
    $record.FinishedUtc=[DateTime]::UtcNow.ToString('o')
    $record | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath "$evidence\action-$Sequence.json" -Encoding UTF8
}
