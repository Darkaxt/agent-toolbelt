$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$rows = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -in @('java.exe', 'javaw.exe', 'cmd.exe', 'gradle.exe')
} | ForEach-Object {
    [ordered]@{ pid = [int]$_.ProcessId; name = $_.Name; command = $_.CommandLine;
        created = ([DateTimeOffset]$_.CreationDate).ToUnixTimeMilliseconds() / 1000.0 }
})
$known = $true
$connected = @()
try {
    $connected = @(Get-NetTCPConnection -ErrorAction Stop | Where-Object {
        $_.State -eq 'Established' -and [System.Net.IPAddress]::IsLoopback([System.Net.IPAddress]::Parse($_.RemoteAddress))
    } |
        Select-Object -ExpandProperty OwningProcess -Unique)
} catch { $known = $false }
[ordered]@{ processes = $rows; connected_pids = $connected; connections_known = $known } |
    ConvertTo-Json -Depth 6 -Compress
