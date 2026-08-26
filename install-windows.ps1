[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [string]$SourceRoot = ""
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$RepositoryArchive = "https://github.com/delu543/weixin-replay-to-mp3/archive/refs/heads/main.zip"
$MinimumPython = "3.10"
$PreferredPythonPackage = "Python.Python.3.12"

function Test-WindowsHost {
    return [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
}

function Refresh-ProcessPath {
    $machinePath = [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = (($machinePath, $userPath) | Where-Object { $_ }) -join ";"
}

function Invoke-PythonProbe {
    param(
        [string]$Executable,
        [string[]]$PrefixArguments = @()
    )

    if ([string]::IsNullOrWhiteSpace($Executable)) {
        return $null
    }
    try {
        $arguments = @()
        $arguments += $PrefixArguments
        $arguments += @(
            "-c",
            "import platform,sys; print(sys.executable + '|' + platform.python_version()); raise SystemExit(0 if sys.version_info >= (3,10) else 3)"
        )
        $probe = & $Executable @arguments 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $probe) {
            return $null
        }
        $parts = ([string]$probe).Trim() -split '\|', 2
        if ($parts.Count -ne 2) {
            return $null
        }
        return [PSCustomObject]@{
            executable = $Executable
            prefix_arguments = @($PrefixArguments)
            resolved_executable = $parts[0]
            version = $parts[1]
        }
    }
    catch {
        return $null
    }
}

function Find-CompatiblePython {
    $localPrograms = Join-Path $env:LOCALAPPDATA "Programs\Python"
    foreach ($suffix in @("314", "313", "312", "311", "310")) {
        $candidate = Join-Path $localPrograms ("Python{0}\python.exe" -f $suffix)
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $probe = Invoke-PythonProbe -Executable $candidate
            if ($probe) {
                return $probe
            }
        }
    }

    $launcher = Get-Command "py.exe" -ErrorAction SilentlyContinue
    if ($launcher) {
        foreach ($selector in @("-3.14", "-3.13", "-3.12", "-3.11", "-3.10", "-3")) {
            $probe = Invoke-PythonProbe -Executable $launcher.Source -PrefixArguments @($selector)
            if ($probe) {
                return $probe
            }
        }
    }

    foreach ($name in @("python.exe", "python3.exe")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            $probe = Invoke-PythonProbe -Executable $command.Source
            if ($probe) {
                return $probe
            }
        }
    }
    return $null
}

function Find-LocalSourceRoot {
    param([string]$RequestedRoot)

    $candidates = @()
    if (-not [string]::IsNullOrWhiteSpace($RequestedRoot)) {
        $candidates += $RequestedRoot
    }
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        $candidates += $PSScriptRoot
    }
    foreach ($candidate in $candidates) {
        $bootstrap = Join-Path $candidate "scripts\bootstrap.py"
        $agents = Join-Path $candidate "AGENTS.md"
        if ((Test-Path -LiteralPath $bootstrap -PathType Leaf) -and
            (Test-Path -LiteralPath $agents -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return ""
}

function Get-CurrentSourceArchive {
    $downloadRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
        "WeixinReplayToMP3-source-{0}" -f [System.Guid]::NewGuid().ToString("N")
    )
    New-Item -ItemType Directory -Path $downloadRoot | Out-Null
    $archive = Join-Path $downloadRoot "source.zip"
    Invoke-WebRequest -UseBasicParsing -Uri $RepositoryArchive -OutFile $archive
    Expand-Archive -LiteralPath $archive -DestinationPath $downloadRoot -Force
    $expanded = Join-Path $downloadRoot "weixin-replay-to-mp3-main"
    foreach ($required in @("AGENTS.md", "VERSION", "scripts\bootstrap.py")) {
        if (-not (Test-Path -LiteralPath (Join-Path $expanded $required) -PathType Leaf)) {
            throw "Downloaded GitHub source archive is missing required file: $required"
        }
    }
    return $expanded
}

function Install-CompatiblePython {
    $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw (
            "Python $MinimumPython or newer is missing and Windows Package Manager (winget) " +
            "is unavailable. Install Microsoft App Installer, then rerun this installer."
        )
    }

    $baseArguments = @(
        "install", "--id", $PreferredPythonPackage, "--exact", "--source", "winget",
        "--accept-package-agreements", "--accept-source-agreements", "--silent"
    )
    & $winget.Source @baseArguments "--scope" "user"
    if ($LASTEXITCODE -ne 0) {
        throw "winget could not install $PreferredPythonPackage. Exit code: $LASTEXITCODE"
    }
    Refresh-ProcessPath
}

function Invoke-WithPython {
    param(
        [PSCustomObject]$Python,
        [string[]]$Arguments
    )
    $allArguments = @()
    $allArguments += $Python.prefix_arguments
    $allArguments += $Arguments
    & $Python.executable @allArguments | ForEach-Object { Write-Host $_ }
    $exitCode = $LASTEXITCODE
    return [int]$exitCode
}

try {
    if (-not (Test-WindowsHost)) {
        throw "install-windows.ps1 must run on a native Windows host."
    }

    $python = Find-CompatiblePython
    $winget = Get-Command "winget.exe" -ErrorAction SilentlyContinue
    $git = Get-Command "git.exe" -ErrorAction SilentlyContinue
    $localSource = Find-LocalSourceRoot -RequestedRoot $SourceRoot

    if ($CheckOnly) {
        [PSCustomObject]@{
            status = "checked"
            platform = "Windows"
            python_ready = [bool]$python
            python_version = $(if ($python) { $python.version } else { "" })
            winget_ready = [bool]$winget
            git_available = [bool]$git
            git_required = $false
            ffmpeg_installed_by_private_runtime = $true
            local_source_ready = -not [string]::IsNullOrWhiteSpace($localSource)
            source_strategy = $(
                if ($localSource) { "local_repository" } else { "github_archive_without_git" }
            )
        } | ConvertTo-Json -Depth 4
        exit 0
    }

    if (-not $python) {
        Write-Host "Python $MinimumPython+ is missing; installing a current user-local Python runtime."
        Install-CompatiblePython
        $python = Find-CompatiblePython
        if (-not $python) {
            throw "Python installation completed but no compatible interpreter was discovered."
        }
    }

    $resolvedSource = $localSource
    $sourceStrategy = "local_repository"
    if ([string]::IsNullOrWhiteSpace($resolvedSource)) {
        Write-Host "A working Git clone is not required; downloading the current GitHub source archive."
        $resolvedSource = Get-CurrentSourceArchive
        $sourceStrategy = "github_archive_without_git"
    }

    $bootstrap = Join-Path $resolvedSource "scripts\bootstrap.py"
    $installExit = Invoke-WithPython -Python $python -Arguments @($bootstrap, "install")
    if ($installExit -ne 0) {
        throw "Private runtime installation failed with exit code $installExit."
    }

    $doctorExit = Invoke-WithPython -Python $python -Arguments @($bootstrap, "doctor")
    if ($doctorExit -ne 0) {
        throw "Post-install readiness check failed with exit code $doctorExit."
    }

    [PSCustomObject]@{
        status = "ready"
        platform = "Windows"
        python_version = $python.version
        source_strategy = $sourceStrategy
        git_required = $false
        ffmpeg_strategy = "pinned_private_runtime"
    } | ConvertTo-Json -Depth 4
    Write-Output "READY: you can send a link now"
    exit 0
}
catch {
    [Console]::Error.WriteLine("ERROR: " + $_.Exception.Message)
    exit 1
}
