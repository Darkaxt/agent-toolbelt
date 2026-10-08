$ErrorActionPreference = 'Stop'
$wrapperPid = [int]$env:GRADLE_GATE_SUPPORT_WRAPPER_PID
$filter = "ProcessId = $wrapperPid OR Name = 'java.exe' OR Name = 'javaw.exe' OR Name = 'cmd.exe'"
$rows = @(Get-CimInstance Win32_Process -Filter $filter | ForEach-Object {
    $start = 0
    try { $start = (Get-Process -Id $_.ProcessId -ErrorAction Stop).StartTime.ToUniversalTime().ToFileTimeUtc() } catch {}
    # CIM timestamps have microsecond precision. Reject a replaced identity;
    # retain the exact native GetProcessTimes-backed StartTime for later checks.
    if (-not $_.CreationDate -or [Math]::Abs($start - $_.CreationDate.ToUniversalTime().ToFileTimeUtc()) -ge 10) { $start = 0 }
    [pscustomobject]@{
        pid = [int]$_.ProcessId
        parent_pid = [int]$_.ParentProcessId
        created_ticks = $start
        executable = $_.ExecutablePath
        name = $_.Name
        gradle_daemon = $_.CommandLine -like '*org.gradle.launcher.daemon.bootstrap.GradleDaemon*'
        gradle_client = ($_.CommandLine -like '*org.gradle.wrapper.GradleWrapperMain*' -or $_.CommandLine -like '*org.gradle.launcher.GradleMain*')
    }
})
$connections = @()
try {
    $connections = @(Get-NetTCPConnection -State Established -ErrorAction Stop | ForEach-Object {
        [pscustomobject]@{ pid = [int]$_.OwningProcess; local_address = $_.LocalAddress; local_port = [int]$_.LocalPort;
            remote_address = $_.RemoteAddress; remote_port = [int]$_.RemotePort }
    })
} catch {}
ConvertTo-Json -InputObject @{processes=$rows; connections=$connections} -Compress -Depth 4
