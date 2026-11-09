param(
    [string]$TaskName = "CodexThreadRecallCollector",
    [int]$IntervalMinutes = 5,
    [int]$MaxThreads = 10,
    [int]$UpdatedWithinHours = 48,
    [int]$MaxRunSeconds = 90,
    [string]$CodexHome = "",
    [switch]$RefreshRuntime
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

if ($RefreshRuntime) {
    if (-not $noConsole) { throw 'A collector runtime refresh requires the selected no-console pythonw.exe.' }
    $tasks = @(Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Where-Object { $_.TaskName -ceq $TaskName })
    if ($tasks.Count -ne 1 -or @($tasks[0].Actions).Count -ne 1) { throw 'Resolve exactly one existing collector task/action before refresh.' }
    $task = $tasks[0]
    $previous = $task.Actions[0]
    if ($previous.Arguments -notmatch '^-m agent_toolbelt_codex_thread_recall\.cli collect(?:\s|$)') {
        throw 'Preserve an action that is not the existing recall collector.'
    }
    [xml]$beforeXml = Export-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath
    $action = [Microsoft.Management.Infrastructure.CimInstance]::new($previous)
    $action.Execute = $python
    Set-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath -Action @($action) | Out-Null
    $after = Get-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath
    [xml]$afterXml = Export-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath
    foreach ($section in @('Triggers','Settings','Principals')) {
        if ($beforeXml.Task.$section.OuterXml -cne $afterXml.Task.$section.OuterXml) {
            throw "Collector $section differs after the runtime-only refresh; preserve evidence and reconcile the exact task."
        }
    }
    if ($after.Actions[0].Execute -cne $python -or $after.Actions[0].Arguments -cne $previous.Arguments -or
        $after.Actions[0].WorkingDirectory -cne $previous.WorkingDirectory -or $after.Actions[0].Id -cne $previous.Id) {
        throw 'The collector action did not retain its original arguments, directory and identity.'
    }
    [pscustomobject]@{ok=$true;task_name=$task.TaskName;runtime_refreshed=$true;previous_python=$previous.Execute;python=$python;
        no_console=$true;triggers_preserved=$true;settings_preserved=$true;principal_preserved=$true;running_instances_stopped=$false;
        rollback='Restore the previous verified active runtime selection and rerun -RefreshRuntime.'} | ConvertTo-Json -Depth 4
    return
}

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
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

[pscustomobject]@{
    ok = $true
    task_name = $TaskName
    interval_minutes = $IntervalMinutes
    python = $python
    no_console = $noConsole
    hard_execution_timeout = $false
    warning = $(if ($noConsole) { $null } else { "pythonw.exe was unavailable; scheduled runs may open a console window." })
    arguments = $arguments
    json_log = $jsonLog
} | ConvertTo-Json -Depth 4
