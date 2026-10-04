$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$objects = @()
try {
    $pids = @()
    foreach ($process in @(Get-Process | Where-Object ProcessName -in @('java', 'javaw', 'cmd', 'gradle'))) {
        try {
            $process.EnableRaisingEvents = $true
            Register-ObjectEvent $process Exited -SourceIdentifier "gradle-process-$($process.Id)" | Out-Null
            $pids += $process.Id
            $objects += $process
        } catch {
            if (-not $process.HasExited) { throw }
        }
    }
    foreach ($gradleHome in ($env:GRADLE_GATE_WATCH_ROOTS | ConvertFrom-Json)) {
        $root = Join-Path $gradleHome 'daemon'
        while (-not (Test-Path -LiteralPath $root -PathType Container)) {
            $parent = Split-Path -Parent $root
            if (-not $parent -or $parent -eq $root) { throw "No readable ancestor for $gradleHome" }
            $root = $parent
        }
        $watcher = New-Object System.IO.FileSystemWatcher($root, '*.out.log')
        $watcher.IncludeSubdirectories = $true
        $watcher.NotifyFilter = [System.IO.NotifyFilters]'FileName, LastWrite, Size'
        $id = [guid]::NewGuid().ToString()
        foreach ($event in @('Changed', 'Created', 'Deleted', 'Renamed', 'Error')) {
            Register-ObjectEvent $watcher $event -SourceIdentifier "gradle-log-$id-$event" | Out-Null
        }
        $watcher.EnableRaisingEvents = $true
        $objects += $watcher
    }
    [Console]::WriteLine('ready:' + (ConvertTo-Json -InputObject @($pids) -Compress))
    while ($true) {
        $event = Wait-Event
        if ($event.SourceIdentifier -like '*-Error') { throw 'Log watcher lost events; refusing unsafe launch' }
        Remove-Event -EventIdentifier $event.EventIdentifier
        [Console]::WriteLine('changed')
    }
} finally {
    Get-EventSubscriber | Unregister-Event
    foreach ($watcher in $objects) { $watcher.Dispose() }
}
