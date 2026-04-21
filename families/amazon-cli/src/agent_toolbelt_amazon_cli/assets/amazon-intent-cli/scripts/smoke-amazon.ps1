param(
    [string[]]$Marketplaces = @("de", "fr", "es")
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

# Exercises: amazon-cli search, amazon-cli get, amazon-cli reviews, amazon-cli session login.

function Invoke-AmazonCliJson {
    param([string[]]$Arguments)

    $output = & uv run amazon-cli @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "amazon-cli failed: amazon-cli $($Arguments -join ' ')`n$output"
    }
    return $output | ConvertFrom-Json
}

function Get-MicrowaveTerm {
    param([string]$Marketplace)

    switch ($Marketplace) {
        "de" { return "mikrowelle" }
        "fr" { return "micro-ondes" }
        "es" { return "microondas" }
        default { return "microwave" }
    }
}

foreach ($marketplace in $Marketplaces) {
    $sessionPath = Join-Path $env:LOCALAPPDATA "amazon-intent-cli\browser-sessions\$($marketplace)__retail.json"
    if (-not (Test-Path $sessionPath)) {
        Write-Warning "Missing managed session for $marketplace. Run: amazon-cli session login --marketplace $marketplace --portal retail"
        continue
    }

    Write-Host "== $marketplace microwave search under 100 =="
    $microwaveTerm = Get-MicrowaveTerm $marketplace
    $microwaves = Invoke-AmazonCliJson @("search", $microwaveTerm, "--marketplace", $marketplace, "--max-price", "100", "--pages", "1")
    if (-not $microwaves.results -or $microwaves.results.Count -eq 0) {
        throw "No microwave search results for $marketplace"
    }

    Write-Host "== $marketplace exact LG C4 search =="
    $search = Invoke-AmazonCliJson @("search", "tv", "--brand", "LG", "--model", "C4", "--marketplace", $marketplace, "--pages", "1")
    if (-not $search.results -or $search.results.Count -eq 0) {
        throw "No exact LG C4 search results for $marketplace"
    }

    $asin = $search.results[0].asin
    Write-Host "== $marketplace get $asin =="
    $item = Invoke-AmazonCliJson @("get", $asin, "--marketplace", $marketplace)
    if ($item.item.asin -ne $asin) {
        throw "Get returned unexpected ASIN for $marketplace. Expected $asin, got $($item.item.asin)"
    }

    Write-Host "== $marketplace reviews $asin limit 20 =="
    $reviews = Invoke-AmazonCliJson @("reviews", $asin, "--marketplace", $marketplace, "--portal", "retail", "--limit", "20")
    if (-not $reviews.comments_summary) {
        throw "Reviews output did not include comments_summary for $marketplace"
    }

    Write-Host "Smoke OK for $marketplace. Reviews extracted: $($reviews.comments_summary.extracted_review_count)"
}
