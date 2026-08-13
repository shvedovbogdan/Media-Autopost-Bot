param(
    [Parameter(Mandatory = $true)]
    [string]$Source,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-zA-Z0-9_-]{1,32}$')]
    [string]$TargetKey
)

$ErrorActionPreference = "Stop"
$DestinationRoot = Join-Path $PSScriptRoot "channels"
$ResolvedSource = (Resolve-Path -LiteralPath $Source).Path
$TargetRoot = Join-Path $DestinationRoot $TargetKey

$Mappings = @(
    @{ Names = @("photos"); Destination = "photos" },
    @{ Names = @("videos", "video"); Destination = "videos" },
    @{ Names = @("archive"); Destination = "archive" }
)

foreach ($Mapping in $Mappings) {
    $Found = $null
    foreach ($Name in $Mapping.Names) {
        $Candidate = Join-Path $ResolvedSource $Name
        if (Test-Path -LiteralPath $Candidate -PathType Container) {
            $Found = $Candidate
            break
        }
    }

    if ($null -eq $Found) {
        continue
    }

    $Destination = Join-Path $TargetRoot $Mapping.Destination
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $Items = Get-ChildItem -LiteralPath $Found -Force
    if ($Items) {
        $Items | Copy-Item -Destination $Destination -Recurse -Force
    }
    Write-Host "COPIED $Found -> $Destination"
}

Write-Host "Done. Original files were not deleted."
