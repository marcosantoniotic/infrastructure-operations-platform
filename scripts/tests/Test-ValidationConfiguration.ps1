$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../../automation/scripts/ValidationConfiguration.ps1')
function Assert([bool]$Value,[string]$Message){if(-not $Value){throw $Message}}
function Must-Fail([scriptblock]$Action){$failed=$false;try{& $Action}catch{$failed=$true};Assert $failed 'Expected refusal did not occur'}
$config=[pscustomobject]@{platform_ip='192.0.2.10';standby_ip='192.0.2.11'}
Assert ((Get-ValidationServiceAddress $config 'srv01-validation') -eq '192.0.2.10') 'Legacy address changed'
$config | Add-Member infrastructure_network ([pscustomobject]@{addresses=[pscustomobject]@{'srv01-validation'='198.51.100.20/24'}})
Assert ((Get-ValidationServiceAddress $config 'srv01-validation') -eq '198.51.100.20') 'Service address not selected'
Assert ((Get-ValidationServiceAddress $config 'srv02-standby') -eq '192.0.2.11') 'Absent optional service address changed standby'
foreach($bad in @('not-an-ip/24','198.51.100.20/99','198.51.100.20','::1/64')){
 $config.infrastructure_network.addresses.'srv01-validation'=$bad
 Must-Fail {Get-ValidationServiceAddress $config 'srv01-validation'}
}
$root=Join-Path ([IO.Path]::GetTempPath()) ('iop-config-test-'+[guid]::NewGuid().ToString('N'))
$dir=Join-Path $root '.validation/ansible/group_vars/all'
New-Item -ItemType Directory -Path $dir,(Join-Path $root 'filter_plugins') | Out-Null
try{
 foreach($name in @('main.yml','vault.yml','vault.yaml','20-storage.yml','zz-security.yaml','notes.txt')){
  'enabled: true' | Out-File -LiteralPath (Join-Path $dir $name) -Encoding utf8
 }
 $files=@(Get-ValidationOverrideFiles $root)
 Assert ($files.Count -eq 2 -and $files[0].Name -eq '20-storage.yml' -and $files[1].Name -eq 'zz-security.yaml') 'Override allowlist/order failed'
 $script:Copies=@();$script:FailTransfer=$false
 function global:scp.exe {
  param([Parameter(ValueFromRemainingArguments)][object[]]$Arguments)
  $script:Copies+=,@($Arguments);$global:LASTEXITCODE=if($script:FailTransfer){1}else{0}
 }
 Sync-ValidationOverrides $root 'automation@controller.example.test' '/home/automation/infrastructure-operations-platform' @('-o','StrictHostKeyChecking=yes')
 Assert ($script:Copies.Count -eq 3) 'Safety filters/overrides not staged'
 Assert ((@($script:Copies | ForEach-Object {$_ -join ' '}) -join ';') -notmatch '/(main|vault)\.ya?ml') 'Generated vars/Vault leaked into override staging'
 $script:FailTransfer=$true
 Must-Fail {Sync-ValidationOverrides $root 'automation@controller.example.test' '/home/automation/infrastructure-operations-platform' @('-o','BatchMode=yes')}
 Must-Fail {Sync-ValidationOverrides $root 'invalid;destination' '/home/automation/infrastructure-operations-platform' @('-o','BatchMode=yes')}
 Write-Output 'VALIDATION_CONFIGURATION_TESTS_PASSED (no network connections)'
}finally{
 Remove-Item Function:\scp.exe -ErrorAction SilentlyContinue
 # Generated fixture only, checked against its exact unique temporary directory.
 $resolved=[IO.Path]::GetFullPath($root)
 if($resolved -ne $root -or (Split-Path $root -Leaf) -notmatch '^iop-config-test-[a-f0-9]{32}$'){throw 'Unsafe fixture cleanup path'}
 Remove-Item -LiteralPath $resolved -Recurse -Force
}
# Expected mocked transfer failures must not become the pwsh process exit code.
$global:LASTEXITCODE = 0
