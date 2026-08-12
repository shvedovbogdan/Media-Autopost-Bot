param(
    [string]$HotGirlsSource = "",
    [string]$HotPuppySource = "",
    [string]$HotYaoiSource = "",
    [string]$HotboysSource = ""
)

$ErrorActionPreference = "Stop"
$DestinationRoot = Join-Path $PSScriptRoot "channels"

function Copy-MediaQueue {
    param(
        [string]$Source,
        [string]$TargetKey
    )

    if ([string]::IsNullOrWhiteSpace($Source)) {
        Write-Host "SKIP $TargetKey - source path not provided"
        return
    }

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
        if ($null -eq $Found) { continue }

        $Destination = Join-Path $TargetRoot $Mapping.Destination
        New-Item -ItemType Directory -Force -Path $Destination | Out-Null
        $Items = Get-ChildItem -LiteralPath $Found -Force
        if ($Items) {
            $Items | Copy-Item -Destination $Destination -Recurse -Force
        }
        Write-Host "COPIED $Found -> $Destination"
    }
}

Copy-MediaQueue -Source $HotGirlsSource -TargetKey "hot_girls"
Copy-MediaQueue -Source $HotPuppySource -TargetKey "hot_puppy"
Copy-MediaQueue -Source $HotYaoiSource -TargetKey "hot_yaoi"
Copy-MediaQueue -Source $HotboysSource -TargetKey "hotboys"

Write-Host "Done. Original files were not deleted."
