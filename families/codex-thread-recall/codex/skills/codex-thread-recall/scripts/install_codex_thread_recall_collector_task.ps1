param(
    [string]$TaskName = "CodexThreadRecallCollector",
    [int]$IntervalMinutes = 5,
    [int]$MaxThreads = 10,
    [int]$UpdatedWithinHours = 48,
    [int]$MaxRunSeconds = 90,
    [string]$CodexHome = ""
)

$ErrorActionPreference = "Stop"

if (-not $CodexHome) {
    if ($env:CODEX_HOME) {
        $CodexHome = $env:CODEX_HOME
    } else {
        $CodexHome = Join-Path $env:USERPROFILE ".codex"
    }
}

$runtimeRoot = Join-Path $CodexHome "tools\codex-thread-recall"
$activeManifest = Join-Path $runtimeRoot "active.json"
if (-not (Test-Path -LiteralPath $activeManifest)) {
    throw "Missing codex-thread-recall active runtime manifest: $activeManifest"
}

$active = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
$releaseRoot = [string]$active.release_root
if (-not $releaseRoot) {
    throw "active.json does not contain release_root."
}

$pythonCandidates = @(
    (Join-Path $releaseRoot ".venv\Scripts\pythonw.exe"),
    (Join-Path $releaseRoot ".venv\Scripts\python.exe"),
    (Join-Path $releaseRoot ".venv\Scripts\python"),
    (Join-Path $releaseRoot ".venv\bin\python")
)
$python = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $python) {
    throw "Could not find staged codex-thread-recall runtime Python under $releaseRoot"
}
$noConsole = [System.IO.Path]::GetFileName($python).Equals("pythonw.exe", [System.StringComparison]::OrdinalIgnoreCase)

$collectorDir = Join-Path $CodexHome "cache\codex-thread-recall\collector"
New-Item -ItemType Directory -Path $collectorDir -Force | Out-Null
$jsonLog = Join-Path $collectorDir "collector.jsonl"

$arguments = @(
    "-m", "agent_toolbelt_codex_thread_recall.cli",
    "collect",
    "--thread-source", "recent",
    "--max-threads", "$MaxThreads",
    "--updated-within-hours", "$UpdatedWithinHours",
    "--max-run-seconds", "$MaxRunSeconds",
    "--json-log", "`"$jsonLog`""
) -join " "

$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $CodexHome
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

[pscustomobject]@{
    ok = $true
    task_name = $TaskName
    interval_minutes = $IntervalMinutes
    python = $python
    no_console = $noConsole
    warning = $(if ($noConsole) { $null } else { "pythonw.exe was unavailable; scheduled runs may open a console window." })
    arguments = $arguments
    json_log = $jsonLog
} | ConvertTo-Json -Depth 4
