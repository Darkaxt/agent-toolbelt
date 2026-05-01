param(
    [string]$TaskName = "CodexThreadRecallCollector"
)

$ErrorActionPreference = "Stop"

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $task) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

[pscustomobject]@{
    ok = $true
    task_name = $TaskName
    removed = ($null -ne $task)
} | ConvertTo-Json -Depth 3
