param([Parameter(Mandatory=$true)][string]$SourceExe,
      [Parameter(Mandatory=$true)][string]$ExpectedSha256)
$ErrorActionPreference='Stop'
if (-not [Environment]::Is64BitProcess) { throw '64-bit elevated PowerShell required' }
$identity=[Security.Principal.WindowsIdentity]::GetCurrent()
$principal=[Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Administrator token required' }
if ($ExpectedSha256 -notmatch '^[a-f0-9]{64}$') { throw 'Invalid release digest' }
$source=(Resolve-Path -LiteralPath $SourceExe).Path
if ((Get-Item -LiteralPath $source).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Redirected source is unsupported' }
if ((Get-FileHash -LiteralPath $source).Hash -ine $ExpectedSha256) { throw 'Source binary changed' }
$programFiles=[Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFiles)
$root=Join-Path $programFiles 'Darka.WindowsElevationGate'
$release=Join-Path (Join-Path $root 'releases') $ExpectedSha256.Substring(0,16)
$target=Join-Path $release 'WindowsElevationBroker.exe'
foreach ($process in Get-CimInstance Win32_Process -Filter "Name='WindowsElevationBroker.exe'") {
    if ($process.ExecutablePath -and $process.ExecutablePath.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)) {
        throw 'Existing broker must be stopped through its tray/stop interface before activation'
    }
}
$admins=[Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
$system=[Security.Principal.SecurityIdentifier]::new('S-1-5-18')
$users=[Security.Principal.SecurityIdentifier]::new('S-1-5-32-545')
function Protect-Object([string]$Path) {
    $item=Get-Item -LiteralPath $Path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Redirected installation path: $Path" }
    $acl=Get-Acl -LiteralPath $Path
    $acl.SetOwner($admins)
    $acl.SetAccessRuleProtection($true,$false)
    foreach ($rule in @($acl.Access)) { [void]$acl.RemoveAccessRuleSpecific($rule) }
    $inheritance=if ($item.PSIsContainer) { [Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit' } else { [Security.AccessControl.InheritanceFlags]::None }
    foreach ($sid in @($admins,$system)) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($sid,'FullControl',$inheritance,'None','Allow'))
    }
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($users,'ReadAndExecute',$inheritance,'None','Allow'))
    Set-Acl -LiteralPath $Path -AclObject $acl
}
foreach ($directory in @($root,(Join-Path $root 'releases'),$release)) {
    if (-not [IO.Path]::GetFullPath($directory).StartsWith($programFiles+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Installation escaped Program Files' }
    if (-not (Test-Path -LiteralPath $directory)) { [void](New-Item -ItemType Directory -Path $directory) }
    Protect-Object $directory
}
if (Test-Path -LiteralPath $target) {
    if ((Get-Item -LiteralPath $target).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Redirected broker executable' }
    if ((Get-FileHash -LiteralPath $target).Hash -ine $ExpectedSha256) { throw 'Immutable protected release differs' }
} else { Copy-Item -LiteralPath $source -Destination $target }
Protect-Object $target
if ((Get-FileHash -LiteralPath $target).Hash -ine $ExpectedSha256) { throw 'Protected copy hash mismatch' }
$active=Join-Path $root 'active.json'
if (Test-Path -LiteralPath $active) {
    if ((Get-Item -LiteralPath $active).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Redirected active pointer' }
}
$pending=Join-Path $root ([Guid]::NewGuid().ToString('N')+'.pending.json')
@{version='0.2.2';release=$ExpectedSha256.Substring(0,16);sha256=$ExpectedSha256} | ConvertTo-Json | Set-Content -LiteralPath $pending -Encoding UTF8
Protect-Object $pending
Move-Item -LiteralPath $pending -Destination $active -Force
Protect-Object $active
@{ok=$true;operation='install-broker';broker=$target;sha256=$ExpectedSha256;owner='Administrators';unelevated_write=$false} | ConvertTo-Json
