$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$objects = @()
function New-ExitSignal([int]$ProcessId) {
    # Waits on a SYNCHRONIZE-only handle, which elevated processes still grant
    # to a medium-integrity watcher, and raises Exited like Process does.
    if (-not ('GradleGateExitSignal' -as [type])) {
        Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Threading;
using Microsoft.Win32.SafeHandles;
public sealed class GradleGateExitSignal : IDisposable {
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
    const uint SYNCHRONIZE = 0x00100000;
    readonly ManualResetEvent handle;
    RegisteredWaitHandle registration;
    public event EventHandler Exited;
    GradleGateExitSignal(IntPtr raw) {
        handle = new ManualResetEvent(false);
        handle.SafeWaitHandle = new SafeWaitHandle(raw, true);
    }
    public static GradleGateExitSignal TryOpen(int pid) {
        IntPtr raw = OpenProcess(SYNCHRONIZE, false, pid);
        return raw == IntPtr.Zero ? null : new GradleGateExitSignal(raw);
    }
    // Armed after the PowerShell subscription, so an exit is never missed.
    public void Arm() {
        registration = ThreadPool.RegisterWaitForSingleObject(handle, delegate {
            EventHandler exited = Exited;
            if (exited != null) exited(this, EventArgs.Empty);
        }, null, Timeout.Infinite, true);
    }
    public void Dispose() {
        if (registration != null) registration.Unregister(null);
        handle.Dispose();
    }
}
"@
    }
    return [GradleGateExitSignal]::TryOpen($ProcessId)
}
try {
    $pids = @()
    $polled = @()
    foreach ($process in @(Get-Process | Where-Object ProcessName -in @('java', 'javaw', 'cmd', 'gradle'))) {
        try {
            $process.EnableRaisingEvents = $true
            Register-ObjectEvent $process Exited -SourceIdentifier "gradle-process-$($process.Id)" | Out-Null
            $pids += $process.Id
            $objects += $process
        } catch {
            # A process running elevated or as another user (e.g. an installer's
            # cmd.exe) denies an exit subscription. Report it instead of
            # refusing every build; the gate decides whether it matters.
            $win32 = $_.Exception.InnerException -as [System.ComponentModel.Win32Exception]
            if ($win32 -and $win32.NativeErrorCode -eq 5) {
                $signal = New-ExitSignal $process.Id
                if ($signal) {
                    Register-ObjectEvent $signal Exited -SourceIdentifier "gradle-process-$($process.Id)" | Out-Null
                    $signal.Arm()
                    $pids += $process.Id
                    $objects += $signal
                } else {
                    # Not even SYNCHRONIZE: re-inspect on a timer instead.
                    $polled += $process.Id
                }
            }
            elseif (-not $process.HasExited) { throw }
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
    $ready = [ordered]@{ watched = @($pids); polled = @($polled) }
    [Console]::WriteLine('ready:' + (ConvertTo-Json -InputObject $ready -Compress))
    while ($true) {
        if ($polled.Count) {
            $event = Wait-Event -Timeout 5
            if (-not $event) { [Console]::WriteLine('changed'); continue }
        } else {
            $event = Wait-Event
        }
        if ($event.SourceIdentifier -like '*-Error') { throw 'Log watcher lost events; refusing unsafe launch' }
        Remove-Event -EventIdentifier $event.EventIdentifier
        [Console]::WriteLine('changed')
    }
} finally {
    Get-EventSubscriber | Unregister-Event
    foreach ($watcher in $objects) { $watcher.Dispose() }
}
