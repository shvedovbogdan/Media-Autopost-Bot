param(
    [string]$Version = "1.6"
)

$ErrorActionPreference = "Stop"

$SourceRoot = $PSScriptRoot
$OutputRoot = Split-Path -Parent $SourceRoot
$ArchivePath = Join-Path $OutputRoot "Media_Autopost_Bot_Universal_v$Version.zip"
$StageRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("MediaAutopostRelease_" + [guid]::NewGuid().ToString("N"))
$PackageName = "Media_Autopost_Bot_v$Version"
$PackageRoot = Join-Path $StageRoot $PackageName

$Files = @(
    ".env.example",
    ".gitignore",
    "bot.py",
    "build_release.ps1",
    "channels.json",
    "config.py",
    "database.py",
    "diagnose.bat",
    "diagnose.py",
    "import_media.ps1",
    "install_task.ps1",
    "README.md",
    "requirements.txt",
    "server_start.bat",
    "setup.bat",
    "setup_config.py",
    "start.bat",
    "ІНСТРУКЦІЯ.md"
)

$CodeDirectories = @(
    "app",
    "caption_packs",
    "handlers",
    "keyboards",
    "services",
    "utils"
)

$RuntimeDirectories = @(
    "channels",
    "data",
    "stats",
    "caption_history",
    "logs"
)

try {
    New-Item -ItemType Directory -Force -Path $PackageRoot | Out-Null

    foreach ($File in $Files) {
        $Source = Join-Path $SourceRoot $File
        if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
            throw "Required file is missing: $File"
        }
        Copy-Item -LiteralPath $Source -Destination (Join-Path $PackageRoot $File) -Force
    }

    foreach ($Directory in $CodeDirectories) {
        $Source = Join-Path $SourceRoot $Directory
        if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
            throw "Required directory is missing: $Directory"
        }
        Copy-Item -LiteralPath $Source -Destination (Join-Path $PackageRoot $Directory) -Recurse -Force
        Get-ChildItem -LiteralPath (Join-Path $PackageRoot $Directory) -Directory -Filter "__pycache__" -Recurse |
            Remove-Item -Recurse -Force
        Get-ChildItem -LiteralPath (Join-Path $PackageRoot $Directory) -File -Include "*.pyc", "*.pyo" -Recurse |
            Remove-Item -Force
    }

    foreach ($Directory in $RuntimeDirectories) {
        $Destination = Join-Path $PackageRoot $Directory
        New-Item -ItemType Directory -Force -Path $Destination | Out-Null
        $Readme = Join-Path (Join-Path $SourceRoot $Directory) "README.txt"
        if (Test-Path -LiteralPath $Readme -PathType Leaf) {
            Copy-Item -LiteralPath $Readme -Destination (Join-Path $Destination "README.txt") -Force
        }
    }

    # A sale package must never contain a client's channels, tokens, media, logs or statistics.
    $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText((Join-Path $PackageRoot "channels.json"), "{}`r`n", $Utf8NoBom)

    Compress-Archive -LiteralPath $PackageRoot -DestinationPath $ArchivePath -CompressionLevel Optimal -Force
    Write-Host "Created clean sale package: $ArchivePath"
}
finally {
    if (Test-Path -LiteralPath $StageRoot) {
        Remove-Item -LiteralPath $StageRoot -Recurse -Force
    }
}
