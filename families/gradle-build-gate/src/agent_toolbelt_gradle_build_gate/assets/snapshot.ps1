$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$rows = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -in @('java.exe', 'javaw.exe', 'cmd.exe', 'gradle.exe')
} | ForEach-Object {
    [ordered]@{ pid = [int]$_.ProcessId; parent_pid = [int]$_.ParentProcessId;
        name = $_.Name; command = $_.CommandLine;
        executable = $_.ExecutablePath; session = [int]$_.SessionId;
        created = ([DateTimeOffset]$_.CreationDate).ToUnixTimeMilliseconds() / 1000.0 }
})
$known = $true
$connected = @()
$connections = @()
try {
    $connections = @(Get-NetTCPConnection -ErrorAction Stop | Where-Object {
        $_.State -eq 'Established' -and [System.Net.IPAddress]::IsLoopback([System.Net.IPAddress]::Parse($_.RemoteAddress))
    } | ForEach-Object {
        [ordered]@{ pid = [int]$_.OwningProcess; local_address = $_.LocalAddress;
            local_port = [int]$_.LocalPort; remote_address = $_.RemoteAddress;
            remote_port = [int]$_.RemotePort }
    })
    $connected = @($connections | ForEach-Object { $_.pid } | Select-Object -Unique)
} catch { $known = $false }
# Cleanup bindings need the same process identities across the TCP observation.
# This does not relax or replace the build gate's existing activity classification.
$cleanupIdentityKnown = $true
try {
    $fresh = @{}
    Get-CimInstance Win32_Process | Where-Object {
        $_.Name -in @('java.exe', 'javaw.exe', 'cmd.exe', 'gradle.exe')
    } | ForEach-Object {
        $fresh[[int]$_.ProcessId] = ([DateTimeOffset]$_.CreationDate).ToUnixTimeMilliseconds() / 1000.0
    }
    if ($fresh.Count -ne $rows.Count) { $cleanupIdentityKnown = $false }
    foreach ($row in $rows) {
        if (-not $fresh.ContainsKey($row.pid) -or $fresh[$row.pid] -ne $row.created) {
            $cleanupIdentityKnown = $false
        }
    }
} catch { $cleanupIdentityKnown = $false }
[ordered]@{ processes = $rows; connected_pids = $connected; connections = $connections; connections_known = $known;
    cleanup_identity_known = $cleanupIdentityKnown;
    session = [System.Diagnostics.Process]::GetCurrentProcess().SessionId } |
    ConvertTo-Json -Depth 6 -Compress
