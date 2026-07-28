<#
.SYNOPSIS
Prepara uma estação Windows reutilizável para projetos de infraestrutura como código.

.DESCRIPTION
Bootstrap autônomo e idempotente para VMware Workstation, Packer, Vagrant,
Vagrant VMware Utility, provider vagrant-vmware-desktop, OpenSSH e Ansible
executado em WSL/Ubuntu.

Não depende de repositório, ISO, sistema operacional convidado ou projeto.
Não cria imagens, boxes, redes ou máquinas virtuais.

.PARAMETER AuditOnly
Somente audita. Não instala, atualiza, habilita recurso ou inicia serviço.

.PARAMETER SkipVmware
Não instala nem valida a cadeia VMware/Vagrant. Útil para uma estação somente Ansible.

.PARAMETER SkipAnsible
Não instala nem valida WSL, Ubuntu e Ansible.

.PARAMETER InstallVmware
Autoriza a instalação do VMware Workstation via WinGet quando ausente.
Sem esta opção, uma instalação ausente é reportada com orientação.

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-InfrastructureWorkstation.ps1 -InstallVmware

.EXAMPLE
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-InfrastructureWorkstation.ps1 -AuditOnly
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$PackerVersion = '1.16.0',
    [string]$VagrantVersion = '2.4.9',
    [string]$VmwareUtilityVersion = '1.0.24',
    [string]$PackerDirectory = (Join-Path $env:LOCALAPPDATA 'Programs\HashiCorp\Packer'),
    [string]$WslDistribution = 'Ubuntu',
    [switch]$InstallVmware,
    [switch]$SkipVmware,
    [switch]$SkipAnsible,
    [switch]$AuditOnly,
    [switch]$KeepDownloads
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$downloadRoot = Join-Path $env:TEMP 'infrastructure-workstation-bootstrap'
$restartRequired = $false
$results = [System.Collections.Generic.List[object]]::new()

function Write-Step {
    param([Parameter(Mandatory)][string]$Message)
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Add-Result {
    param(
        [Parameter(Mandatory)][string]$Component,
        [Parameter(Mandatory)][string]$Status,
        [Parameter(Mandatory)][string]$Details
    )
    $script:results.Add([pscustomobject]@{
        Component = $Component
        Status    = $Status
        Details   = $Details
    })
}

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machinePath;$userPath"
}

function Add-UserPathEntry {
    param([Parameter(Mandatory)][string]$Path)
    $normalizedPath = $Path.TrimEnd('\')
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = @($userPath -split ';' | Where-Object { $_ })

    if (@($entries | ForEach-Object { $_.TrimEnd('\') }) -notcontains $normalizedPath) {
        [Environment]::SetEnvironmentVariable(
            'Path',
            ((@($entries) + $normalizedPath) -join ';'),
            'User'
        )
    }
    Refresh-ProcessPath
}

function Get-InstalledApplication {
    param([Parameter(Mandatory)][string]$NamePattern)
    Get-ItemProperty `
        'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', `
        'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*', `
        'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' `
        -ErrorAction SilentlyContinue |
        Where-Object { $_.DisplayName -match $NamePattern } |
        Select-Object -First 1
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-VerifiedDownload {
    param(
        [Parameter(Mandatory)][string]$ArtifactUrl,
        [Parameter(Mandatory)][string]$ChecksumUrl,
        [Parameter(Mandatory)][string]$ArtifactName,
        [Parameter(Mandatory)][string]$DestinationDirectory
    )

    New-Item -ItemType Directory -Path $DestinationDirectory -Force | Out-Null
    $artifactPath = Join-Path $DestinationDirectory $ArtifactName
    $checksumPath = Join-Path $DestinationDirectory 'SHA256SUMS'
    Invoke-WebRequest -UseBasicParsing -Uri $ArtifactUrl -OutFile $artifactPath
    Invoke-WebRequest -UseBasicParsing -Uri $ChecksumUrl -OutFile $checksumPath

    $entry = Select-String -LiteralPath $checksumPath `
        -Pattern ("{0}$" -f [regex]::Escape($ArtifactName)) |
        Select-Object -First 1
    if (-not $entry) {
        throw "Checksum não publicado para $ArtifactName."
    }

    $expected = $entry.Line.Split()[0].ToUpperInvariant()
    $actual = (Get-FileHash -LiteralPath $artifactPath -Algorithm SHA256).Hash
    if ($actual.ToUpperInvariant() -ne $expected) {
        throw "Checksum inválido para $ArtifactName."
    }
    return $artifactPath
}

function Install-MsiPackage {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$ProductName
    )
    $process = Start-Process msiexec.exe `
        -ArgumentList "/i `"$Path`" /passive /norestart" `
        -Verb RunAs -Wait -PassThru
    if ($process.ExitCode -notin @(0, 3010)) {
        throw "Falha na instalação de $ProductName. Código: $($process.ExitCode)."
    }
    if ($process.ExitCode -eq 3010) {
        $script:restartRequired = $true
    }
}

function Enable-OpenSshClient {
    $ssh = Get-Command ssh.exe -ErrorAction SilentlyContinue
    $keygen = Get-Command ssh-keygen.exe -ErrorAction SilentlyContinue
    if ($ssh -and $keygen) {
        Add-Result OpenSSH Ready 'ssh.exe e ssh-keygen.exe disponíveis'
        return
    }
    if ($AuditOnly) {
        Add-Result OpenSSH Missing 'OpenSSH Client não está instalado'
        return
    }
    if (-not (Test-IsAdministrator)) {
        throw 'Abra o PowerShell como administrador para habilitar o OpenSSH Client.'
    }
    $openSshCapability = 'OpenSSH.Client~~~~' + '0.0.' + '1.0'
    Add-WindowsCapability -Online -Name $openSshCapability | Out-Null
    Add-Result OpenSSH Installed 'OpenSSH Client habilitado'
}

function Install-Packer {
    $command = Get-Command packer.exe -ErrorAction SilentlyContinue
    $version = if ($command) {
        ((& $command.Source version | Select-Object -First 1) -replace '^Packer v', '').Trim()
    }
    if ($version -eq $PackerVersion) {
        Add-Result Packer Ready $version
        return
    }
    if ($AuditOnly) {
        Add-Result Packer Missing "Esperado $PackerVersion; encontrado $version"
        return
    }

    $artifact = "packer_${PackerVersion}_windows_amd64.zip"
    $zip = Get-VerifiedDownload `
        -ArtifactUrl "https://releases.hashicorp.com/packer/$PackerVersion/$artifact" `
        -ChecksumUrl "https://releases.hashicorp.com/packer/$PackerVersion/packer_${PackerVersion}_SHA256SUMS" `
        -ArtifactName $artifact `
        -DestinationDirectory (Join-Path $downloadRoot 'packer')
    New-Item -ItemType Directory -Path $PackerDirectory -Force | Out-Null
    Expand-Archive -LiteralPath $zip -DestinationPath $PackerDirectory -Force
    Add-UserPathEntry $PackerDirectory
    Add-Result Packer Installed $PackerVersion
}

function Install-Vagrant {
    $command = Get-Command vagrant.exe -ErrorAction SilentlyContinue
    $version = if ($command) {
        ((& $command.Source --version) -replace '^Vagrant ', '').Trim()
    }
    if ($version -eq $VagrantVersion) {
        Add-Result Vagrant Ready $version
        return
    }
    if ($AuditOnly) {
        Add-Result Vagrant Missing "Esperado $VagrantVersion; encontrado $version"
        return
    }

    $artifact = "vagrant_${VagrantVersion}_windows_amd64.msi"
    $msi = Get-VerifiedDownload `
        -ArtifactUrl "https://releases.hashicorp.com/vagrant/$VagrantVersion/$artifact" `
        -ChecksumUrl "https://releases.hashicorp.com/vagrant/$VagrantVersion/vagrant_${VagrantVersion}_SHA256SUMS" `
        -ArtifactName $artifact `
        -DestinationDirectory (Join-Path $downloadRoot 'vagrant')
    Install-MsiPackage $msi 'Vagrant'
    Refresh-ProcessPath
    Add-Result Vagrant Installed $VagrantVersion
}

function Install-VmwareWorkstation {
    $vmware = Get-InstalledApplication '^VMware Workstation( Pro)?$'
    if ($vmware) {
        Add-Result 'VMware Workstation' Ready $vmware.DisplayVersion
        return
    }
    if ($AuditOnly) {
        Add-Result 'VMware Workstation' Missing 'Não instalado'
        return
    }
    if (-not $InstallVmware) {
        Add-Result 'VMware Workstation' ManualAction `
            'Instale-o manualmente ou execute novamente com -InstallVmware'
        return
    }
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw 'WinGet não encontrado. Instale o App Installer ou o VMware manualmente.'
    }
    & $winget.Source install --id VMware.WorkstationPro --exact `
        --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw 'A instalação do VMware Workstation via WinGet falhou.'
    }
    Add-Result 'VMware Workstation' Installed 'Instalado via WinGet'
}

function Install-VmwareUtility {
    $utility = Get-InstalledApplication 'Vagrant VMware Utility|vagrant-vmware-utility'
    if ($utility -and $utility.DisplayVersion -eq $VmwareUtilityVersion) {
        $service = Get-Service VagrantVMware -ErrorAction SilentlyContinue
        Add-Result 'Vagrant VMware Utility' Ready `
            "$($utility.DisplayVersion); serviço $($service.Status)"
        return
    }
    if ($AuditOnly) {
        Add-Result 'Vagrant VMware Utility' Missing "Esperado $VmwareUtilityVersion"
        return
    }
    $artifact = "vagrant-vmware-utility_${VmwareUtilityVersion}_windows_amd64.msi"
    $msi = Get-VerifiedDownload `
        -ArtifactUrl "https://releases.hashicorp.com/vagrant-vmware-utility/$VmwareUtilityVersion/$artifact" `
        -ChecksumUrl "https://releases.hashicorp.com/vagrant-vmware-utility/$VmwareUtilityVersion/vagrant-vmware-utility_${VmwareUtilityVersion}_SHA256SUMS" `
        -ArtifactName $artifact `
        -DestinationDirectory (Join-Path $downloadRoot 'vmware-utility')
    Install-MsiPackage $msi 'Vagrant VMware Utility'
    $service = Get-Service VagrantVMware -ErrorAction Stop
    if ($service.Status -ne 'Running') {
        Start-Service VagrantVMware
    }
    Add-Result 'Vagrant VMware Utility' Installed $VmwareUtilityVersion
}

function Install-VagrantVmwarePlugin {
    if (-not (Get-Command vagrant.exe -ErrorAction SilentlyContinue)) {
        Add-Result 'Vagrant VMware provider' Blocked 'Vagrant indisponível'
        return
    }
    $plugins = & vagrant.exe plugin list 2>&1
    if ($LASTEXITCODE -eq 0 -and $plugins -match '(?m)^vagrant-vmware-desktop\s') {
        $line = $plugins | Select-String '^vagrant-vmware-desktop\s' | Select-Object -First 1
        Add-Result 'Vagrant VMware provider' Ready $line.Line
        return
    }
    if ($AuditOnly) {
        Add-Result 'Vagrant VMware provider' Missing 'Plugin não instalado'
        return
    }
    & vagrant.exe plugin install vagrant-vmware-desktop
    if ($LASTEXITCODE -ne 0) {
        throw 'Falha ao instalar o plugin vagrant-vmware-desktop.'
    }
    Add-Result 'Vagrant VMware provider' Installed 'vagrant-vmware-desktop'
}

function Install-AnsibleOnWsl {
    $wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
    if (-not $wsl) {
        if ($AuditOnly) {
            Add-Result WSL Missing 'WSL não está disponível'
            Add-Result Ansible Blocked 'WSL não está disponível'
            return
        }
        if (-not (Test-IsAdministrator)) {
            throw 'Abra o PowerShell como administrador para habilitar o WSL.'
        }
        & dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux `
            /all /norestart | Out-Null
        & dism.exe /online /enable-feature /featurename:VirtualMachinePlatform `
            /all /norestart | Out-Null
        $script:restartRequired = $true
        Add-Result WSL Installed 'Recursos habilitados; reinicialização necessária'
        Add-Result Ansible Blocked 'Execute novamente após reiniciar'
        return
    }

    $distributions = @(& wsl.exe --list --quiet 2>$null) |
        ForEach-Object { ($_ -replace "`0", '').Trim() } |
        Where-Object { $_ }
    if ($distributions -notcontains $WslDistribution) {
        if ($AuditOnly) {
            Add-Result WSL Missing "Distribuição $WslDistribution não instalada"
            Add-Result Ansible Blocked 'Distribuição WSL ausente'
            return
        }
        & wsl.exe --install --distribution $WslDistribution --no-launch
        if ($LASTEXITCODE -ne 0) {
            throw "Falha ao instalar a distribuição WSL $WslDistribution."
        }
        Add-Result WSL Installed $WslDistribution
    }
    else {
        Add-Result WSL Ready $WslDistribution
    }

    & wsl.exe --distribution $WslDistribution --user root -- `
        bash -lc 'command -v ansible-playbook >/dev/null 2>&1'
    if ($LASTEXITCODE -eq 0) {
        $ansibleVersion = & wsl.exe --distribution $WslDistribution -- `
            bash -lc 'ansible-playbook --version | head -n 1'
        Add-Result Ansible Ready (($ansibleVersion -replace "`0", '').Trim())
        return
    }
    if ($AuditOnly) {
        Add-Result Ansible Missing 'ansible-playbook não encontrado no WSL'
        return
    }

    & wsl.exe --distribution $WslDistribution --user root -- `
        bash -lc 'apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y ansible'
    if ($LASTEXITCODE -ne 0) {
        throw 'Falha ao instalar Ansible dentro do WSL.'
    }
    $ansibleVersion = & wsl.exe --distribution $WslDistribution -- `
        bash -lc 'ansible-playbook --version | head -n 1'
    Add-Result Ansible Installed (($ansibleVersion -replace "`0", '').Trim())
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'Este bootstrap é destinado a estações Windows.'
}

Write-Step 'Windows, PowerShell e OpenSSH'
Add-Result Windows Ready ([Environment]::OSVersion.VersionString)
Add-Result PowerShell Ready $PSVersionTable.PSVersion.ToString()
Enable-OpenSshClient

if (-not $SkipVmware) {
    Write-Step 'VMware, Packer e Vagrant'
    Install-VmwareWorkstation
    Install-Packer
    Install-Vagrant
    Install-VmwareUtility
    Install-VagrantVmwarePlugin
}

if (-not $SkipAnsible) {
    Write-Step 'WSL e Ansible'
    Install-AnsibleOnWsl
}

if (-not $KeepDownloads -and (Test-Path -LiteralPath $downloadRoot)) {
    $resolved = (Resolve-Path -LiteralPath $downloadRoot).Path
    $temp = (Resolve-Path -LiteralPath $env:TEMP).Path
    if (-not $resolved.StartsWith($temp, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Recusa ao remover diretório fora de TEMP: $resolved"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

Write-Step 'Relatório da estação'
$results | Format-Table -AutoSize

$problems = @($results | Where-Object {
    $_.Status -in @('Missing', 'Blocked', 'ManualAction')
})
if ($restartRequired) {
    Write-Warning 'Reinicie o Windows e execute o script novamente.'
}
if ($problems.Count -gt 0) {
    Write-Warning 'A estação ainda possui requisitos pendentes.'
    exit 2
}

$readyComponents = [System.Collections.Generic.List[string]]::new()
if (-not $SkipVmware) {
    @('VMware', 'Packer', 'Vagrant') | ForEach-Object {
        $readyComponents.Add($_)
    }
}
if (-not $SkipAnsible) {
    $readyComponents.Add('Ansible')
}
Write-Host (
    "`nEstação pronta para projetos com {0}." -f ($readyComponents -join ' + ')
) -ForegroundColor Green
Write-Host 'Nenhuma imagem, box ou máquina virtual foi criada.'
