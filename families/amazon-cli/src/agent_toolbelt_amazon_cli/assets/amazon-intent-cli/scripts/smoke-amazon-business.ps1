param(
    [string[]]$Marketplaces = @("de"),
    [string]$Asin = "B0F2JCZPB4",
    [int]$Limit = 20
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

# Exercises: amazon-cli reviews, amazon-cli session login.

function Invoke-AmazonCliJson {
    param([string[]]$Arguments)

    $output = & uv run amazon-cli @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "amazon-cli failed: amazon-cli $($Arguments -join ' ')`n$output"
    }
    return $output | ConvertFrom-Json
}

foreach ($marketplace in $Marketplaces) {
    $sessionPath = Join-Path $env:LOCALAPPDATA "amazon-intent-cli\browser-sessions\$($marketplace)__business.json"
    if (-not (Test-Path $sessionPath)) {
        Write-Warning "Missing managed Business session for $marketplace. Run: amazon-cli session login --marketplace $marketplace --portal business"
        continue
    }

    Write-Host "== $marketplace Business reviews $Asin limit $Limit =="
    $reviews = Invoke-AmazonCliJson @("reviews", $Asin, "--marketplace", $marketplace, "--portal", "business", "--limit", "$Limit")
    if (-not $reviews.comments_summary) {
        throw "Reviews output did not include comments_summary for $marketplace"
    }
    if ($reviews.deep_reviews_available -ne $true) {
        throw "Deep reviews were not available for $marketplace. Reason: $($reviews.fallback_reason)"
    }

    Write-Host "Business smoke OK for $marketplace. Reviews extracted: $($reviews.comments_summary.extracted_review_count)"
}
