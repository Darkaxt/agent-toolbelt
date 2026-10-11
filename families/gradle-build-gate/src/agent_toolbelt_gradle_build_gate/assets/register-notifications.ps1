Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Text;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

public static class GradleNotificationIdentity {
    [StructLayout(LayoutKind.Sequential)]
    struct PropertyKey { public Guid format; public uint id; }
    [StructLayout(LayoutKind.Explicit, Size=24)]
    struct Variant {
        [FieldOffset(0)] public ushort type;
        [FieldOffset(8)] public IntPtr text;
    }
    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IPropertyStore {
        [PreserveSig] int GetCount(out uint count);
        [PreserveSig] int GetAt(uint index, out PropertyKey key);
        [PreserveSig] int GetValue(ref PropertyKey key, out Variant value);
        [PreserveSig] int SetValue(ref PropertyKey key, ref Variant value);
        [PreserveSig] int Commit();
    }
    [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    interface IShellLink {
        [PreserveSig] int GetPath(StringBuilder path, int length, IntPtr data, uint flags);
        [PreserveSig] int GetIDList(out IntPtr list);
        [PreserveSig] int SetIDList(IntPtr list);
        [PreserveSig] int GetDescription(StringBuilder text, int length);
        [PreserveSig] int SetDescription([MarshalAs(UnmanagedType.LPWStr)] string text);
        [PreserveSig] int GetWorkingDirectory(StringBuilder path, int length);
        [PreserveSig] int SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string path);
        [PreserveSig] int GetArguments(StringBuilder text, int length);
        [PreserveSig] int SetArguments([MarshalAs(UnmanagedType.LPWStr)] string text);
        [PreserveSig] int GetHotkey(out short key);
        [PreserveSig] int SetHotkey(short key);
        [PreserveSig] int GetShowCmd(out int command);
        [PreserveSig] int SetShowCmd(int command);
        [PreserveSig] int GetIconLocation(StringBuilder path, int length, out int index);
        [PreserveSig] int SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string path, int index);
        [PreserveSig] int SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string path, uint reserved);
        [PreserveSig] int Resolve(IntPtr window, uint flags);
        [PreserveSig] int SetPath([MarshalAs(UnmanagedType.LPWStr)] string path);
    }
    [DllImport("ole32.dll")] static extern int PropVariantClear(ref Variant value);
    [DllImport("shell32.dll", CharSet=CharSet.Unicode)]
    static extern void SHChangeNotify(uint change, uint flags, string item, IntPtr other);

    public static void Register(string path, string executable, string appId) {
        object instance = Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("00021401-0000-0000-C000-000000000046")));
        Variant value = new Variant();
        try {
            var file = (IPersistFile)instance;
            var store = (IPropertyStore)instance;
            var key = new PropertyKey { format = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), id = 5 };
            if (File.Exists(path)) {
                file.Load(path, 0);
                Marshal.ThrowExceptionForHR(store.GetValue(ref key, out value));
                if (value.type != 31 || Marshal.PtrToStringUni(value.text) != appId)
                    throw new InvalidOperationException("Existing shortcut belongs to another identity");
                return;
            }
            var link = (IShellLink)instance;
            Marshal.ThrowExceptionForHR(link.SetPath(executable));
            Marshal.ThrowExceptionForHR(link.SetArguments("-NoProfile -NonInteractive -WindowStyle Hidden -Command exit"));
            Marshal.ThrowExceptionForHR(link.SetDescription("Silent task and project ownership notifications for the Gradle build gate"));
            Marshal.ThrowExceptionForHR(link.SetShowCmd(7));
            value.type = 31;
            value.text = Marshal.StringToCoTaskMemUni(appId);
            Marshal.ThrowExceptionForHR(store.SetValue(ref key, ref value));
            Marshal.ThrowExceptionForHR(store.Commit());
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            file.Save(path, true);
            SHChangeNotify(2, 0x1005, path, IntPtr.Zero);
        } finally {
            PropVariantClear(ref value);
            Marshal.FinalReleaseComObject(instance);
        }
    }
}
'@
$shortcut = Join-Path $env:APPDATA 'Microsoft/Windows/Start Menu/Programs/Gradle Build Gate.lnk'
$executable = Join-Path $env:SystemRoot 'System32/WindowsPowerShell/v1.0/powershell.exe'
[GradleNotificationIdentity]::Register($shortcut, $executable, 'Darka.GradleBuildGate')
$identity = 'HKCU:\Software\Classes\AppUserModelId\Darka.GradleBuildGate'
New-Item -Path $identity -Force | Out-Null
New-ItemProperty -LiteralPath $identity -Name DisplayName -Value 'Gradle Build Gate' -PropertyType String -Force | Out-Null
New-ItemProperty -LiteralPath $identity -Name IconUri -Value $executable -PropertyType String -Force | Out-Null
@{ state = 'registered' } | ConvertTo-Json -Compress
