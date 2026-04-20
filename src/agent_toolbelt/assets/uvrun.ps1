[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Script,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ScriptArgs = @()
)

$ErrorActionPreference = "Stop"

$helperPath = Join-Path $PSScriptRoot "uvrun_helper.py"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Error: 'uv' not found in PATH"
    Write-Host "Please install uv: https://docs.astral.sh/uv/"
    exit 1
}

if (-not (Test-Path -LiteralPath $Script)) {
    Write-Host "Error: Script not found: $Script"
    exit 1
}

if (-not (Test-Path -LiteralPath $helperPath)) {
    Write-Host "Error: uvrun_helper.py not found!"
    Write-Host ""
    Write-Host "Looking for: $helperPath"
    Write-Host ""
    Write-Host "Please ensure uvrun_helper.py is in the same folder as uvrun.ps1"
    exit 1
}

& python $helperPath $Script
$helperExitCode = $LASTEXITCODE
if ($helperExitCode -ne 0) {
    Write-Host "Failed to prepare script"
    exit $helperExitCode
}

Write-Host ""
Write-Host "Running with uv..."
& uv run $Script @ScriptArgs
exit $LASTEXITCODE
