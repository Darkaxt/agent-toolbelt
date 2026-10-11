param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$MutexName,
    [switch]$Probe
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type -ReferencedAssemblies System.Windows.Forms,System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using System.Windows.Forms;
public static class GradleTrayNative {
    [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
    [DllImport("kernel32.dll")] static extern bool GetProcessTimes(IntPtr h, out long created, out long exit, out long kernel, out long user);
    [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr h, uint wait);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    [DllImport("user32.dll")] static extern bool DestroyIcon(IntPtr h);
    public static string Identity(int pid, long ticks) {
        IntPtr h = OpenProcess(0x101000, false, pid);
        if (h == IntPtr.Zero) return Marshal.GetLastWin32Error() == 87 ? "exited" : "unknown";
        try {
            uint wait = WaitForSingleObject(h, 0);
            if (wait == 0) return "exited";
            if (wait != 258) return "unknown";
            long c,e,k,u;
            if (!GetProcessTimes(h,out c,out e,out k,out u)) return "unknown";
            return c == ticks ? "live" : "exited";
        } finally { CloseHandle(h); }
    }
    // Original local elephant silhouette referencing Gradle, not a stock icon.
    public static Icon Elephant(string state) {
        using (Bitmap bitmap = new Bitmap(32,32)) {
            using (Graphics g = Graphics.FromImage(bitmap)) {
                g.SmoothingMode = SmoothingMode.AntiAlias;
                g.Clear(Color.Transparent);
                Color color = state == "busy" ? Color.FromArgb(249,181,65) :
                              state == "uncertain" ? Color.FromArgb(240,110,95) : Color.FromArgb(66,201,163);
                using (SolidBrush brush = new SolidBrush(color)) {
                    g.FillEllipse(brush,3,8,22,16); // body and head
                    g.FillEllipse(brush,19,6,11,13);
                    g.FillRectangle(brush,6,20,5,9);
                    g.FillRectangle(brush,17,20,5,9);
                    using (GraphicsPath trunk = new GraphicsPath()) {
                        trunk.AddBezier(25,10,34,12,32,27,24,28);
                        trunk.AddLine(24,28,23,24);
                        trunk.AddBezier(23,24,28,24,28,18,25,17);
                        trunk.CloseFigure(); g.FillPath(brush,trunk);
                    }
                }
                using (SolidBrush dark = new SolidBrush(Color.FromArgb(17,47,49))) {
                    g.FillEllipse(dark,17,10,7,10); // recognisable elephant ear
                    g.FillEllipse(dark,25,10,2,2);
                }
            }
            IntPtr handle = bitmap.GetHicon();
            try { using (Icon borrowed = Icon.FromHandle(handle)) return (Icon)borrowed.Clone(); }
            finally { DestroyIcon(handle); }
        }
    }
}
public class GradleHoverCard : Form {
    protected override bool ShowWithoutActivation { get { return true; } }
    protected override CreateParams CreateParams {
        get { CreateParams p = base.CreateParams; p.ExStyle |= 0x08000000; return p; }
    }
}
'@

function Read-Json([string]$Name) {
    $path = Join-Path $Root $Name
    if (-not [IO.File]::Exists($path)) { return $null }
    # No queue or build mutex: a transient atomic-replacement conflict is unknown.
    $stream = [IO.FileStream]::new($path, [IO.FileMode]::Open, [IO.FileAccess]::Read,
                                 ([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
    $reader = [IO.StreamReader]::new($stream, [Text.Encoding]::UTF8)
    try { return ($reader.ReadToEnd() | ConvertFrom-Json) }
    finally { $reader.Dispose(); $stream.Dispose() }
}
function Elapsed($Start) {
    if ($null -eq $Start) { return 0 }
    return [Math]::Max(0, [DateTimeOffset]::UtcNow.ToUnixTimeSeconds() - [double]$Start)
}
function Duration($Seconds) {
    return [TimeSpan]::FromSeconds([Math]::Max(0,[double]$Seconds)).ToString('d\.hh\:mm\:ss')
}
function Get-View {
    try {
        $queue = Read-Json 'queue.json'
        $data = Read-Json 'telemetry.json'
        if ($queue -and ($queue.schema -ne 1 -or $null -eq $queue.tickets)) { throw 'Invalid queue' }
        if ($data -and ($data.schema -ne 1 -or $null -eq $data.live -or $null -eq $data.stats)) { throw 'Invalid telemetry' }
        $tickets = @()
        $uncertain = $false
        foreach ($ticket in @($queue.tickets)) {
            if ($null -eq $ticket) { continue }
            if ($ticket.id -notmatch '^[a-f0-9]{32}$' -or $ticket.pid -lt 1 -or $ticket.created_ticks -lt 1) { throw 'Invalid ticket' }
            $identity = [GradleTrayNative]::Identity($ticket.pid, $ticket.created_ticks)
            if ($identity -ne 'exited') {
                $tickets += $ticket
                if ($identity -eq 'unknown') { $uncertain = $true }
            }
        }
        $owners = @()
        $rows = @()
        foreach ($ticket in $tickets) {
            $row = if ($data) { $data.live.PSObject.Properties[$ticket.id].Value } else { $null }
            $identity = [GradleTrayNative]::Identity($ticket.pid, $ticket.created_ticks)
            if ($row -and $row.pid -eq $ticket.pid -and $row.created_ticks -eq $ticket.created_ticks) {
                $rows += $row
                if ($row.acquired_at -and $row.phase -notin @('queued','released') -and $identity -eq 'live') {
                    $owners += $row
                }
            } else {
                $rows += [pscustomobject]@{ owner_task='Unknown / older helper'; project='Unknown'; phase='unobserved'; number=$ticket.number }
            }
        }
        if ($owners.Count -gt 1) { $uncertain = $true; $owners = @() }
        $owner = if ($owners.Count -eq 1) { $owners[0] } else { $null }
        $waiting = $tickets.Count - $owners.Count
        if (-not $owner -and @($rows | Where-Object { $_.phase -eq 'unobserved' }).Count) { $waiting = $null }
        $state = if ($uncertain) { 'uncertain' } elseif ($owner) { 'busy' } elseif ($tickets.Count) { 'uncertain' } else { 'idle' }
        $gateElapsed = if ($owner) { Elapsed $owner.acquired_at } else { 0 }
        $buildElapsed = if ($owner -and $owner.build_started_at) {
            if ($owner.build_finished_at) { [Math]::Max(0, $owner.build_finished_at - $owner.build_started_at) }
            else { Elapsed $owner.build_started_at }
        } else { 0 }
        $stats = if ($data) { $data.stats } else { [pscustomobject]@{
            builds=0; failures=0; aborted=0; abandoned=0; admissions=0; gate_seconds=0; build_seconds=0; queue_seconds=0
        } }
        $builds = if ($stats) { [int]$stats.builds } else { 0 }
        $admissions = if ($stats) { [int]$stats.admissions } else { 0 }
        $avgBuild = if ($builds) { $stats.build_seconds / $builds } else { 0 }
        $avgWait = if ($admissions) { $stats.queue_seconds / $admissions } else { 0 }
        $lines = @('GRADLE BUILD GATE', '')
        if ($owner) {
            $lines += @("Task: $($owner.owner_task)", "Project: $($owner.project)", "Phase: $($owner.phase)",
                        "Gate held: $(Duration $gateElapsed)   Build: $(Duration $buildElapsed)")
        } elseif ($tickets.Count) {
            $lines += @('Owner: unknown / waiting for gate', 'A FIFO head is not proof of mutex ownership.')
        } else {
            $lines += 'No participating owner observed.'
        }
        if ($uncertain) { $lines += 'Identity/snapshot uncertain; this is not launch clearance.' }
        $queueLabel = if ($null -eq $waiting) { "Registered requests: $($tickets.Count) (waiting count unknown)" }
                      else { "Waiting requests: $waiting" }
        $lines += @($queueLabel, '', 'OBSERVED USAGE (updated helpers only)',
                    "Builds: $builds   Failed: $($stats.failures)   Aborted: $($stats.aborted)",
                    "Exited without final result: $($stats.abandoned)",
                    "Total gate use: $(Duration $stats.gate_seconds)   Build time: $(Duration $stats.build_seconds)",
                    "Average queue wait: $(Duration $avgWait)   Build: $(Duration $avgBuild)")
        if ($data.since) { $lines += "Since: $([DateTimeOffset]::FromUnixTimeSeconds([long]$data.since).ToLocalTime().ToString('yyyy-MM-dd HH:mm'))" }
        $lines += @('', 'QUEUE')
        foreach ($row in $rows) {
            $lines += "#$($row.number) $($row.owner_task) | $($row.project) [$($row.phase)]"
        }
        if (-not $rows.Count) { $lines += '(empty)' }
        $lines += @('', 'Informational only. External builds are not inspected here.', 'Click the elephant for full details. Exit tray never stops a build.')
        $text = $lines -join "`r`n"
        $short = if ($owner) { "Gradle | Q:$waiting | $(Duration $gateElapsed) | $($owner.owner_task)" }
                 elseif ($null -eq $waiting) { "Gradle | owner unknown | Requests:$($tickets.Count)" }
                 else { "Gradle | $state | Waiting:$waiting | Builds:$builds" }
        if ($short.Length -gt 63) { $short = $short.Substring(0,60) + '...' }
        return @{ state=$state; icon_style='local_gradle_elephant'; waiting=$waiting; registered_requests=$tickets.Count;
                  owner=$owner; gate_elapsed_seconds=$gateElapsed;
                  build_elapsed_seconds=$buildElapsed; stats=$stats; queue=$rows; text=$text; tooltip=$short }
    } catch {
        return @{ state='uncertain'; waiting=$null; owner=$null; stats=$null; queue=@();
                  text="GRADLE BUILD GATE`r`nSnapshot unavailable; no execution conclusion.`r`nRead-only observer; builds are unaffected.";
                  tooltip='Gradle | snapshot unavailable' }
    }
}

if ($Probe) { Get-View | ConvertTo-Json -Depth 10 -Compress; exit }

$mutex = New-Object Threading.Mutex($false, $MutexName)
$owned = $false
try {
    try { $owned = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $owned = $true }
    if (-not $owned) { exit }
    $stop = New-Object Threading.EventWaitHandle($false, [Threading.EventResetMode]::ManualReset, ($MutexName + '.Stop'))
    $stop.Reset() | Out-Null
    $ready = New-Object Threading.EventWaitHandle($false, [Threading.EventResetMode]::ManualReset, ($MutexName + '.Ready'))
    $context = New-Object Windows.Forms.ApplicationContext
    $tray = New-Object Windows.Forms.NotifyIcon
    $icons = @{}
    foreach ($state in @('idle','busy','uncertain')) { $icons[$state] = [GradleTrayNative]::Elephant($state) }
    $tray.Icon = $icons.idle
    $tray.Text = 'Gradle build gate'
    $menu = New-Object Windows.Forms.ContextMenuStrip
    $detailsItem = $menu.Items.Add('Show task / queue / usage')
    $exitItem = $menu.Items.Add('Exit tray (builds continue)')
    $tray.ContextMenuStrip = $menu

    $details = New-Object Windows.Forms.Form
    $details.Text = 'Gradle build gate - task, queue and usage'
    $details.Size = New-Object Drawing.Size(750,640)
    $details.MinimumSize = New-Object Drawing.Size(520,380)
    $details.StartPosition = 'CenterScreen'
    $details.Icon = $icons.idle
    $box = New-Object Windows.Forms.TextBox
    $box.Multiline=$true; $box.ReadOnly=$true; $box.ScrollBars='Both'; $box.WordWrap=$false; $box.Dock='Fill'
    $box.Font = New-Object Drawing.Font('Consolas',10)
    $details.Controls.Add($box)
    $details.Add_FormClosing({ param($sender,$event) $event.Cancel=$true; $details.Hide() })

    $hover = New-Object GradleHoverCard
    $hover.FormBorderStyle='FixedToolWindow'; $hover.ControlBox=$false; $hover.ShowInTaskbar=$false; $hover.TopMost=$true
    $hover.Size = New-Object Drawing.Size(590,440)
    $hover.BackColor = [Drawing.Color]::FromArgb(17,47,49)
    $hoverLabel = New-Object Windows.Forms.Label
    $hoverLabel.Dock='Fill'; $hoverLabel.Padding=New-Object Windows.Forms.Padding(14)
    $hoverLabel.ForeColor=[Drawing.Color]::FromArgb(230,248,239)
    $hoverLabel.Font=New-Object Drawing.Font('Segoe UI',10)
    $hoverLabel.AutoEllipsis=$true
    $hover.Controls.Add($hoverLabel)
    $script:anchor = [Drawing.Rectangle]::Empty
    $script:lastState = ''
    function Refresh-View {
        $view = Get-View
        $tray.Text = $view.tooltip
        if ($view.state -ne $script:lastState) {
            $tray.Icon = $icons[$view.state]
            $script:lastState = $view.state
        }
        $box.Text = $view.text
        $hoverLabel.Text = $view.text
    }
    $showDetails = { $hover.Hide(); Refresh-View; $details.Show(); $details.Activate() }
    $detailsItem.Add_Click($showDetails)
    $tray.Add_MouseClick({ param($sender,$event) if ($event.Button -eq 'Left') { & $showDetails } })
    $tray.Add_MouseMove({
        if ($details.Visible -or $menu.Visible -or $hover.Visible) { return }
        Refresh-View
        $cursor = [Windows.Forms.Cursor]::Position
        $script:anchor = New-Object Drawing.Rectangle(($cursor.X-18),($cursor.Y-18),36,36)
        $area = [Windows.Forms.Screen]::FromPoint($cursor).WorkingArea
        $x = [Math]::Max($area.Left, [Math]::Min($cursor.X, $area.Right-$hover.Width))
        $y = [Math]::Max($area.Top, [Math]::Min($cursor.Y-$hover.Height-8, $area.Bottom-$hover.Height))
        $hover.Location = New-Object Drawing.Point($x,$y)
        $hover.Show()
    })
    $menu.Add_Opening({ $hover.Hide(); Refresh-View })
    $exitItem.Add_Click({ $context.ExitThread() })
    $timer = New-Object Windows.Forms.Timer
    $timer.Interval = 1000
    $timer.Add_Tick({
        if ($stop.WaitOne(0)) { $context.ExitThread(); return }
        Refresh-View
        if ($hover.Visible) {
            $cursor = [Windows.Forms.Cursor]::Position
            if (-not $script:anchor.Contains($cursor) -and -not $hover.Bounds.Contains($cursor)) { $hover.Hide() }
        }
    })
    Refresh-View
    $tray.Visible = $true
    $timer.Start()
    $ready.Set() | Out-Null
    [Windows.Forms.Application]::Run($context)
} finally {
    if ($timer) { $timer.Stop(); $timer.Dispose() }
    if ($tray) { $tray.Visible=$false; $tray.Dispose() }
    if ($hover) { $hover.Dispose() }
    if ($details) { $details.Dispose() }
    if ($icons) { foreach ($icon in $icons.Values) { $icon.Dispose() } }
    if ($menu) { $menu.Dispose() }
    if ($ready) { $ready.Dispose() }
    if ($stop) { $stop.Dispose() }
    if ($owned) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
