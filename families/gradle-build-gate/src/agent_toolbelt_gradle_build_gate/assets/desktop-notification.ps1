$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
try {
    $step = 'request'
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    if ($request.action -eq 'register') {
        $step = 'register'
        . (Join-Path $PSScriptRoot 'register-notifications.ps1')
        exit
    }
    $appId = 'Darka.GradleBuildGate'
    $step = 'identity'
    $shortcut = Join-Path $env:APPDATA 'Microsoft/Windows/Start Menu/Programs/Gradle Build Gate.lnk'
    if (-not (Test-Path -LiteralPath $shortcut -PathType Leaf)) {
        throw 'Gradle gate notification identity is not registered'
    }
    $step = 'winrt'
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
    [Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
    [Windows.UI.Notifications.ToastNotifier, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
    [Windows.UI.Notifications.NotificationSetting, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] | Out-Null
    if ($request.action -eq 'remove') {
        $step = 'remove'
        [Windows.UI.Notifications.ToastNotificationManager]::History.Remove($request.tag, $request.group, $appId)
        @{ state = 'removed' } | ConvertTo-Json -Compress
    } elseif ($request.action -eq 'show') {
        $step = 'notifier'
        $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId)
        $step = 'content'
        $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xml.LoadXml($request.xml)
        $toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
        $toast.Tag = $request.tag
        $toast.Group = $request.group
        $step = 'show'
        $notifier.Show($toast)
        # The first submission can initialize Windows' notification record;
        # querying Setting beforehand can raise element-not-found on a new ID.
        $setting = 'unknown'
        try { $setting = $notifier.get_Setting().ToString() } catch { }
        $state = if ($setting -eq 'unknown' -or $setting -eq 'Enabled') { 'submitted' } else { 'disabled_by_windows' }
        @{ state = $state; setting = $setting } | ConvertTo-Json -Compress
    } else {
        throw 'Unsupported notification operation'
    }
} catch {
    # Do not expose arbitrary host, account or COM exception content.
    @{ state = 'unavailable'; failure_kind = 'windows_notification_error'; step = $step;
       hresult = $_.Exception.GetBaseException().HResult } | ConvertTo-Json -Compress
}
