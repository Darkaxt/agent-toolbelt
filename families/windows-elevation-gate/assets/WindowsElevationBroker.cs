// Standalone elevated approval owner. Clients submit requests, never consent.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Pipes;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32.SafeHandles;

namespace DarkaElevation {
    static class TrayArtwork {
        [DllImport("user32.dll")] static extern bool DestroyIcon(IntPtr icon);
        public static Icon WhiteShield() {
            using(var bitmap=new Bitmap(32,32)) {
                using(var graphics=Graphics.FromImage(bitmap)) {
                    graphics.SmoothingMode=System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
                    using(var shape=new System.Drawing.Drawing2D.GraphicsPath()) {
                        shape.AddPolygon(new[]{new PointF(16,2),new PointF(28,6),new PointF(27,18),new PointF(23,25),new PointF(16,30),new PointF(9,25),new PointF(5,18),new PointF(4,6)});
                        graphics.FillPath(Brushes.White,shape);
                    }
                    // Transparent quadrant seams keep the small shield recognizable.
                    graphics.CompositingMode=System.Drawing.Drawing2D.CompositingMode.SourceCopy;
                    using(var gap=new Pen(Color.Transparent,2)) {
                        graphics.DrawLine(gap,16,2,16,30);
                        graphics.DrawLine(gap,5,15,27,15);
                    }
                }
                IntPtr handle=bitmap.GetHicon();
                try {using(var borrowed=Icon.FromHandle(handle))return (Icon)borrowed.Clone();}
                finally {DestroyIcon(handle);}
            }
        }
    }

    static class SessionLaunch {
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool IsProcessInJob(IntPtr process, IntPtr job, out bool member);
        [DllImport("kernel32.dll")] static extern IntPtr GetCurrentProcess();
        [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(uint access,bool inherit,uint pid);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetProcessTimes(IntPtr process,out long created,out long exited,out long kernel,out long user);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool QueryFullProcessImageName(IntPtr process,uint flags,StringBuilder path,ref int size);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool QueryInformationJobObject(IntPtr job,int kind,IntPtr buffer,uint size,out uint length);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool CreateProcess(string application,StringBuilder command,IntPtr processSecurity,IntPtr threadSecurity,bool inherit,uint flags,IntPtr environment,string directory,ref StartupInfo startup,out ProcessInfo process);
        [DllImport("kernel32.dll", SetLastError=true)] static extern uint WaitForSingleObject(IntPtr handle,uint milliseconds);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetExitCodeProcess(IntPtr handle,out uint code);
        [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct StartupInfo {
            public int Size; public string Reserved,Desktop,Title; public uint X,Y,Width,Height,CharsX,CharsY,Fill,Flags; public ushort Show,ReservedSize; public IntPtr ReservedBytes,Input,Output,Error;
        }
        [StructLayout(LayoutKind.Sequential)] struct ProcessInfo { public IntPtr Process,Thread; public uint ProcessId,ThreadId; }
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool CloseHandle(IntPtr handle);
        [DllImport("kernel32.dll", SetLastError=true)] static extern uint WaitForMultipleObjects(uint count, IntPtr[] handles, bool all, uint milliseconds);
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern SafePipeHandle CreateFile(string path, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);
        [DllImport("user32.dll")] static extern IntPtr GetShellWindow();
        [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr window, out uint process);
        [DllImport("shell32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern bool ShellExecuteEx(ref ShellInfo info);
        [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct ShellInfo {
            public int Size; public uint Mask; public IntPtr Window;
            public string Verb, File, Parameters, Directory; public int Show;
            public IntPtr Instance, IdList; public string Class; public IntPtr ClassKey;
            public uint HotKey; public IntPtr Icon, Process;
        }
        static string PipePrefix { get { return "Darka.WindowsElevation.Startup."+WindowsIdentity.GetCurrent().User.Value+"."+Process.GetCurrentProcess().SessionId+"."; } }
        public static bool InJob(IntPtr process) {
            bool member;
            if(!IsProcessInJob(process,IntPtr.Zero,out member))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            return member;
        }
        public static bool InJob() { return InJob(GetCurrentProcess()); }
        public static int LaunchFromDesktop() {
            try {
                string pipeName=PipePrefix+Guid.NewGuid().ToString("N");
                var security=Broker.PipePolicy(WindowsIdentity.GetCurrent().User.Value);
                using(var pipe=new NamedPipeServerStream(pipeName,PipeDirection.InOut,1,PipeTransmissionMode.Byte,PipeOptions.None,4096,4096,security)) {
                    uint shellPid; IntPtr shellWindow=GetShellWindow();
                    if(shellWindow==IntPtr.Zero || GetWindowThreadProcessId(shellWindow,out shellPid)==0)throw new IOException("Interactive desktop Explorer is unavailable");
                    using(var shellProcess=Process.GetProcessById((int)shellPid)) {
                        string expected=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),"explorer.exe");
                        if(!String.Equals(shellProcess.MainModule.FileName,expected,StringComparison.OrdinalIgnoreCase) || shellProcess.SessionId!=Process.GetCurrentProcess().SessionId || InJob(shellProcess.Handle))throw new IOException("Desktop shell is not an independent Explorer in this session");
                    }
                    object windows=null,desktop=null,application=null;
                    try {
                        windows=Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("9BA05972-F6A8-11CF-A442-00A0C90A8F39"),true));
                        dynamic shellWindows=windows; object location=0,root=0; int desktopWindow;
                        desktop=shellWindows.FindWindowSW(ref location,ref root,8,out desktopWindow,1);
                        if(desktop==null || unchecked((uint)desktopWindow)!=unchecked((uint)shellWindow.ToInt64()))throw new IOException("Desktop automation identity mismatch");
                        application=((dynamic)desktop).Document.Application;
                        string exe=Process.GetCurrentProcess().MainModule.FileName;
                        ((dynamic)application).ShellExecute(exe,"--session-bootstrap "+pipeName,Path.GetDirectoryName(exe),"open",1);
                    } finally {
                        foreach(object value in new[]{application,desktop,windows})if(value!=null && Marshal.IsComObject(value))Marshal.FinalReleaseComObject(value);
                    }
                    pipe.WaitForConnection();
                    var result=Wire.Receive(pipe);
                    Console.WriteLine(Wire.Json().Serialize(result));
                    return result.ContainsKey("ok") && result["ok"] is bool && (bool)result["ok"]?0:1;
                }
            } catch(Exception error) {
                Console.WriteLine(Wire.Json().Serialize(Wire.Failure("desktop_launch_failed",error.Message)));
                return 1;
            }
        }
        public static int BreakAway(string value,bool elevatedBroker=false) {
            // Explorer may put each launch in its own explicitly breakaway-enabled job.
            IntPtr buffer=Marshal.AllocHGlobal(144);
            try {
                uint length;
                if(!QueryInformationJobObject(IntPtr.Zero,9,buffer,144,out length))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
                uint flags=unchecked((uint)Marshal.ReadInt32(buffer,16));
                if((flags & 0x1800)==0)throw new IOException("Desktop launch job does not permit session bootstrap breakaway");
            } finally {Marshal.FreeHGlobal(buffer);}
            string exe=Process.GetCurrentProcess().MainModule.FileName;
            var startup=new StartupInfo {Size=Marshal.SizeOf(typeof(StartupInfo))}; ProcessInfo process;
            string mode=elevatedBroker?" --detached-ready-event ":" --detached-session-bootstrap ";
            if(!CreateProcess(exe,new StringBuilder(Request.Quote(exe)+mode+Request.Quote(value)),IntPtr.Zero,IntPtr.Zero,false,0x09000000,IntPtr.Zero,Path.GetDirectoryName(exe),ref startup,out process))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
            try {
                if(elevatedBroker) {
                    using(var ready=EventWaitHandle.OpenExisting(value)) {
                        if(WaitForMultipleObjects(2,new[]{ready.SafeWaitHandle.DangerousGetHandle(),process.Process},false,0xffffffff)!=0)throw new IOException("Detached elevated broker exited before readiness");
                        if(InJob(process.Process))throw new IOException("Detached elevated broker remains job-attached");
                        return 0;
                    }
                }
                if(WaitForSingleObject(process.Process,0xffffffff)!=0)throw new IOException("Detached bootstrap wait failed");
                uint code;if(!GetExitCodeProcess(process.Process,out code))throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
                return unchecked((int)code);
            } finally {CloseHandle(process.Thread);CloseHandle(process.Process);}
        }
        public static int Bootstrap(string pipeName,bool allowBreakaway=true) {
            Guid nonce;
            if(!pipeName.StartsWith(PipePrefix,StringComparison.Ordinal) || !Guid.TryParseExact(pipeName.Substring(PipePrefix.Length),"N",out nonce))return 2;
            Exception detachError=null;
            if(allowBreakaway && InJob()) {
                try {return BreakAway(pipeName);} catch(Exception error) {detachError=error;}
            }
            using(var handle=CreateFile(@"\\.\pipe\"+pipeName,0x100003,0,IntPtr.Zero,3,0x110000,IntPtr.Zero)) {
                if(handle.IsInvalid)return 2;
                using(var stream=new NamedPipeClientStream(PipeDirection.InOut,false,true,handle)) {
                    Dictionary<string,object> result;
                    try {
                        if(detachError!=null)throw detachError;
                        if(InJob())throw new IOException("Desktop bootstrap is unexpectedly job-attached; refusing elevation");
                        string exe=Process.GetCurrentProcess().MainModule.FileName;
                        string readyName=@"Local\Darka.WindowsElevation.BrokerReady."+nonce.ToString("N");
                        using(var ready=new EventWaitHandle(false,EventResetMode.ManualReset,readyName)) {
                            var info=new ShellInfo {Size=Marshal.SizeOf(typeof(ShellInfo)),Mask=0x140,Verb="runas",File=exe,Parameters="--ready-event "+readyName,Directory=Path.GetDirectoryName(exe),Show=1};
                            if(!ShellExecuteEx(ref info)) {
                                int error=Marshal.GetLastWin32Error();
                                result=Wire.Failure(error==1223?"uac_declined":"broker_start_failed",new System.ComponentModel.Win32Exception(error).Message);
                            } else {
                                if(info.Process==IntPtr.Zero)throw new IOException("Native UAC returned no supervised process handle");
                                try {
                                    uint state=WaitForMultipleObjects(2,new[]{ready.SafeWaitHandle.DangerousGetHandle(),info.Process},false,0xffffffff);
                                    if(state!=0)throw new IOException("Broker exited or readiness wait failed before startup verification");
                                    string record=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),"Darka.WindowsElevationGate","session-"+WindowsIdentity.GetCurrent().User.Value+"-"+Process.GetCurrentProcess().SessionId+".json");
                                    if(!Program.Protected(record))throw new IOException("Broker identity record is unprotected");
                                    var identity=Wire.Json().DeserializeObject(File.ReadAllText(record)) as Dictionary<string,object>;
                                    IntPtr actual=OpenProcess(0x1000,false,Convert.ToUInt32(identity["pid"]));
                                    if(actual==IntPtr.Zero)throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
                                    try {
                                        long created,exited,kernel,user;var path=new StringBuilder(32768);int length=path.Capacity;
                                        if(!GetProcessTimes(actual,out created,out exited,out kernel,out user) || !QueryFullProcessImageName(actual,0,path,ref length) || created!=Convert.ToInt64(identity["ticks"]) || !String.Equals(path.ToString(),exe,StringComparison.OrdinalIgnoreCase) || InJob(actual))throw new IOException("Ready broker identity/job verification failed");
                                    } finally {CloseHandle(actual);}
                                    result=new Dictionary<string,object>{{"ok",true},{"operation","broker-start"},{"launch_owner","desktop_explorer"},{"in_job",false}};
                                } finally {CloseHandle(info.Process);}
                            }
                        }
                    } catch(Exception error) {result=Wire.Failure("broker_start_failed",error.Message);}
                    Wire.Send(stream,result);
                    return (bool)result["ok"]?0:1;
                }
            }
        }
    }

    static class Wire {
        public static JavaScriptSerializer Json() { return new JavaScriptSerializer { MaxJsonLength = 262144, RecursionLimit = 24 }; }
        public static byte[] Read(Stream stream, int count) {
            var bytes = new byte[count]; int offset = 0;
            while (offset < count) { int got = stream.Read(bytes, offset, count - offset); if (got == 0) throw new EndOfStreamException(); offset += got; }
            return bytes;
        }
        public static Dictionary<string, object> Receive(Stream stream) {
            int count = BitConverter.ToInt32(Read(stream, 4), 0);
            if (count < 2 || count > 32000) throw new InvalidDataException("Request exceeds bounded protocol");
            return (Dictionary<string, object>)Json().DeserializeObject(new UTF8Encoding(false, true).GetString(Read(stream, count)));
        }
        public static void Send(Stream stream, object value) {
            byte[] bytes = Encoding.UTF8.GetBytes(Json().Serialize(value));
            if (bytes.Length > 240000) throw new InvalidDataException("Response exceeds bounded protocol");
            stream.Write(BitConverter.GetBytes(bytes.Length), 0, 4); stream.Write(bytes, 0, bytes.Length); stream.Flush();
        }
        public static void Only(Dictionary<string, object> data, params string[] keys) {
            if (data.Keys.Any(k => !keys.Contains(k))) throw new InvalidDataException("Unknown fields; clients cannot supply approval or execution state");
        }
        public static Dictionary<string, object> Failure(string kind, string error) {
            return new Dictionary<string, object> { {"ok", false}, {"launched", false}, {"failure_kind", kind}, {"error", error} };
        }
    }

    sealed class Request {
        public readonly string TaskName, ThreadName, Reason, Changes, Cwd;
        public readonly string[] Targets, Command;
        public readonly Dictionary<string, string> Bindings;
        static string Text(Dictionary<string, object> data, string name, int max) {
            object value; if (!data.TryGetValue(name, out value) || !(value is string) || String.IsNullOrWhiteSpace((string)value) || ((string)value).Length > max)
                throw new InvalidDataException("Invalid " + name);
            return (string)value;
        }
        static string[] Strings(object value) {
            var values = value as object[];
            if (values == null || values.Length == 0 || values.Length > 128 || values.Any(v => !(v is string))) throw new InvalidDataException("Invalid string array");
            return values.Cast<string>().ToArray();
        }
        public static string PathName(string value) {
            if (value.Length < 3 || value[1] != ':' || (value[2] != '\\' && value[2] != '/') || value.Substring(2).Contains(':')) throw new InvalidDataException("Absolute local paths without alternate streams required");
            return Path.GetFullPath(value);
        }
        public Request(Dictionary<string, object> data) {
            Wire.Only(data, "schema", "task", "thread_name", "reason", "changes", "cwd", "targets", "command", "bindings", "elevation_host");
            if (Convert.ToInt32(data["schema"]) != 1) throw new InvalidDataException("Unsupported schema");
            TaskName = Text(data, "task", 2000); ThreadName = Text(data, "thread_name", 2000);
            Reason = Text(data, "reason", 2000); Changes = Text(data, "changes", 2000);
            Cwd = PathName(Text(data, "cwd", 32000)); if (!Directory.Exists(Cwd)) throw new InvalidDataException("Working directory missing");
            Targets = Strings(data["targets"]); if (Targets.Any(t => String.IsNullOrWhiteSpace(t) || t.Length > 2000)) throw new InvalidDataException("Invalid target");
            Command = Strings(data["command"]); Command[0] = PathName(Command[0]);
            if(Command.Any(c=>c.IndexOf('\0')>=0))throw new InvalidDataException("NUL in command argument");
            if (!Command[0].EndsWith(".exe", StringComparison.OrdinalIgnoreCase) || !File.Exists(Command[0]) || String.Join(" ", Command).Length > 16000) throw new InvalidDataException("Exact executable required");
            var bindings = data["bindings"] as Dictionary<string, object>;
            if (bindings == null || bindings.Count > 128) throw new InvalidDataException("Invalid bindings");
            Bindings = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (var pair in bindings) {
                string hash = pair.Value as string;
                if (hash == null || hash.Length != 64 || hash.Any(c => !Uri.IsHexDigit(c))) throw new InvalidDataException("Invalid content digest");
                Bindings.Add(PathName(pair.Key), hash.ToLowerInvariant());
            }
            var required = new List<string> { Command[0] };
            for (int i = 1; i < Command.Length; ++i) {
                string value = Command[i].ToLowerInvariant();
                if (value == "-file" || value == "-f" || value == "--file") { if (i + 1 >= Command.Length) throw new InvalidDataException("Missing script path"); required.Add(Command[i + 1]); }
                else if (new[] {".ps1", ".py", ".cmd", ".bat"}.Any(s => value.EndsWith(s))) required.Add(Command[i]);
            }
            foreach (string name in required) {
                string path = PathName(Path.IsPathRooted(name) ? name : Path.Combine(Cwd, name));
                if (!Bindings.ContainsKey(path)) throw new InvalidDataException("Executable/script binding missing; use --bind-file");
            }
        }
        public static string Quote(string value) {
            if (value.Length > 0 && !value.Any(c => Char.IsWhiteSpace(c) || c == '"')) return value;
            var result = new StringBuilder("\""); int slashes = 0;
            foreach (char c in value) {
                if (c == '\\') { ++slashes; continue; }
                result.Append('\\', c == '"' ? slashes * 2 + 1 : slashes); result.Append(c); slashes = 0;
            }
            return result.Append('\\', slashes * 2).Append('"').ToString();
        }
        public string CommandText { get { return String.Join(" ", Command.Select(Quote)); } }
    }

    sealed class BindingLease : IDisposable {
        readonly List<IDisposable> handles = new List<IDisposable>();
        [StructLayout(LayoutKind.Sequential)] struct Info {
            public uint Attributes, CreatedLow, CreatedHigh, AccessLow, AccessHigh, WriteLow, WriteHigh, Volume, SizeHigh, SizeLow, Links, IndexHigh, IndexLow;
        }
        [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)] static extern SafeFileHandle CreateFile(string path, uint access, uint share, IntPtr security, uint creation, uint flags, IntPtr template);
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetFileInformationByHandle(SafeFileHandle handle, out Info info);
        void GuardDirectory(string path) {
            var handle = CreateFile(path, 0x80, 3, IntPtr.Zero, 3, 0x02200000, IntPtr.Zero);
            handles.Add(handle); Info info;
            if (handle.IsInvalid || !GetFileInformationByHandle(handle, out info) || (info.Attributes & 0x400) != 0) throw new IOException("Directory unavailable or redirected");
        }
        public BindingLease(Request request) {
            try {
                var directories = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (string path in request.Bindings.Keys.Concat(new[] {Path.Combine(request.Cwd, "_")})) {
                    var chain = new Stack<string>(); var directory = Directory.GetParent(path);
                    while (directory != null) { chain.Push(directory.FullName); directory = directory.Parent; }
                    while (chain.Count > 0) { string name = chain.Pop(); if (directories.Add(name)) GuardDirectory(name); }
                }
                foreach (var pair in request.Bindings) {
                    var opened=CreateFile(pair.Key,0x80000000,1,IntPtr.Zero,3,0x00200000,IntPtr.Zero); Info info;
                    if(opened.IsInvalid || !GetFileInformationByHandle(opened,out info) || (info.Attributes & 0x410)!=0) {opened.Dispose();throw new IOException("Input unavailable, redirected or not a regular file");}
                    var file = new FileStream(opened,FileAccess.Read);
                    handles.Add(file);
                    string actual; using (var hash = SHA256.Create()) actual = BitConverter.ToString(hash.ComputeHash(file)).Replace("-", "").ToLowerInvariant();
                    if (actual != pair.Value) throw new IOException("input_changed: executable or declared file differs from submitted bytes");
                }
            } catch { Dispose(); throw; }
        }
        public void Dispose() { for (int i = handles.Count - 1; i >= 0; --i) handles[i].Dispose(); handles.Clear(); }
    }

    sealed class ApprovalForm : Form {
        public readonly TextBox Feedback = new TextBox { Multiline=true, MaxLength=4000, ScrollBars=ScrollBars.Vertical, Height=80, Dock=DockStyle.Top };
        readonly Color ink = Color.FromArgb(20, 33, 58);
        Control Card(string title, string value, int height, bool mono=false) {
            var card = new Panel { Dock=DockStyle.Top, Height=height + 48, Padding=new Padding(14), BackColor=Color.White, Margin=new Padding(0,0,0,12) };
            var text = new TextBox { Text=value, ReadOnly=true, Multiline=true, ScrollBars=ScrollBars.Both, WordWrap=!mono, BorderStyle=BorderStyle.None, BackColor=Color.White, ForeColor=ink, Dock=DockStyle.Fill, Font=new Font(mono ? "Consolas" : "Segoe UI", mono ? 10 : 11) };
            var label = new Label { Text=title, Dock=DockStyle.Top, Height=25, ForeColor=Color.FromArgb(20,88,189), Font=new Font("Segoe UI", 10, FontStyle.Bold) };
            card.Controls.Add(text); card.Controls.Add(label); return card;
        }
        public ApprovalForm(Request request, bool preview=false, bool stop=false) {
            Text = (preview ? "Preview - " : "Administrator action - ") + request.ThreadName;
            TopMost=true; StartPosition=FormStartPosition.CenterScreen; BackColor=Color.FromArgb(241,244,250); Font=new Font("Segoe UI",11); AutoScaleMode=AutoScaleMode.Dpi;
            var area=Screen.PrimaryScreen.WorkingArea; ClientSize=new Size(Math.Min(860,area.Width-64),Math.Min(870,area.Height-90)); MinimumSize=new Size(580,460);
            var layout=new TableLayoutPanel { Dock=DockStyle.Fill, ColumnCount=1, RowCount=3, Padding=new Padding(18) };
            layout.RowStyles.Add(new RowStyle(SizeType.Absolute,88)); layout.RowStyles.Add(new RowStyle(SizeType.Percent,100)); layout.RowStyles.Add(new RowStyle(SizeType.Absolute,104));
            var header=new Label { Text=(preview ? "DESIGN PREVIEW" : "ADMINISTRATOR EXECUTION")+"\r\n"+(preview ? "No approval, elevation or command will run." : "This broker is already elevated. Only your acceptance runs this action."), Dock=DockStyle.Fill, ForeColor=ink, Font=new Font("Segoe UI",13,FontStyle.Bold) };
            var body=new FlowLayoutPanel { Dock=DockStyle.Fill, FlowDirection=FlowDirection.TopDown, WrapContents=false, AutoScroll=true, Padding=new Padding(0,0,16,0) };
            var cards=new List<Control> { Card("TASK & THREAD",request.TaskName+"\r\n"+request.ThreadName,64), Card("WHY / EXPECTED CHANGES",request.Reason+"\r\n\r\n"+request.Changes,112), Card("EXACT TARGETS",String.Join("\r\n",request.Targets),70) };
            if(stop) cards.Add(Card("INTERNAL BROKER CONTROL","Stop accepting requests, cancel pending approvals and drain started commands. No external command is executed.",90));
            else {
                cards.Add(Card("EXACT COMMAND / WORKING DIRECTORY",request.CommandText+"\r\n\r\n"+request.Cwd,125,true));
                cards.Add(Card("BOUND INPUTS / SHA-256",String.Join("\r\n",request.Bindings.Select(b=>b.Key+"\r\n"+b.Value)),100,true));
            }
            var feedbackPanel=new Panel { Height=124, BackColor=Color.White, Padding=new Padding(14) };
            feedbackPanel.Controls.Add(Feedback); feedbackPanel.Controls.Add(new Label { Text="OPTIONAL FEEDBACK (returned unchanged; never modifies the command)",Dock=DockStyle.Top,Height=28,ForeColor=ink,Font=new Font("Segoe UI",9) });
            cards.Add(feedbackPanel); foreach (Control card in cards) body.Controls.Add(card);
            body.SizeChanged += delegate { foreach (Control card in cards) card.Width=Math.Max(300,body.ClientSize.Width-30); };
            var footer=new TableLayoutPanel { Dock=DockStyle.Fill, ColumnCount=3, RowCount=1, Padding=new Padding(0,18,0,8) };
            footer.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100)); footer.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,135)); footer.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,205));
            var cancel=new Button { Text=preview ? "Needs changes" : "Cancel", DialogResult=DialogResult.Cancel, Dock=DockStyle.Fill, Margin=new Padding(6), BackColor=Color.White, ForeColor=ink };
            var accept=new Button { Text=preview ? "Looks good" : stop ? "Disable broker" : "Accept && Execute", DialogResult=DialogResult.OK, Dock=DockStyle.Fill, Margin=new Padding(6), BackColor=Color.FromArgb(20,88,189), ForeColor=Color.White, FlatStyle=FlatStyle.Flat };
            footer.Controls.Add(new Label { Text=preview ? "Visual preview only." : "Cancel is the default.\r\nNo automatic approval or retry.", Dock=DockStyle.Fill, ForeColor=ink, Font=new Font("Segoe UI",9) },0,0); footer.Controls.Add(cancel,1,0); footer.Controls.Add(accept,2,0);
            layout.Controls.Add(header,0,0); layout.Controls.Add(body,0,1); layout.Controls.Add(footer,0,2); Controls.Add(layout);
            CancelButton=cancel; Shown+=delegate { cancel.Focus(); };
        }
    }

    sealed class Work {
        public string Id=Guid.NewGuid().ToString("N"); public int Ticket, Peer; public long PeerTicks;
        public Request Request; public NamedPipeServerStream Pipe; public bool Stop;
        public volatile bool Cancelled, Completed; public ApprovalForm Dialog;
    }

    sealed class Broker : ApplicationContext {
        readonly string sid=WindowsIdentity.GetCurrent().User.Value;
        readonly int session=Process.GetCurrentProcess().SessionId;
        readonly object sync=new object(); readonly Queue<Work> queue=new Queue<Work>();
        readonly List<object> history=new List<object>(); readonly Dictionary<string,object> running=new Dictionary<string,object>();
        readonly Form dispatcher=new Form { ShowInTaskbar=false }; readonly NotifyIcon tray;
        readonly Icon trayIcon=TrayArtwork.WhiteShield();
        readonly EventWaitHandle availability;
        volatile bool stopping; bool showing; int sequence, connections; NamedPipeServerStream listening; Work currentApproval; string listenerError;
        public string PipeName { get { return "Darka.WindowsElevation.Broker."+sid+"."+session; } }
        [DllImport("kernel32.dll", SetLastError=true)] static extern bool GetNamedPipeClientProcessId(SafePipeHandle pipe,out uint pid);
        void Post(Action action) { if (!dispatcher.IsDisposed) try { dispatcher.BeginInvoke(action); } catch (InvalidOperationException) {} }
        public Broker(string ready) {
            var unused=dispatcher.Handle;
            availability=new EventWaitHandle(false,EventResetMode.ManualReset,@"Local\"+PipeName+".Available");
            Program.WriteRecord(sid,session,true);
            var menu=new ContextMenuStrip(); menu.Items.Add("Show queue and current tasks",null,delegate { ShowStatus(); }); menu.Items.Add("Disable administrator execution",null,delegate { Stop(); });
            tray=new NotifyIcon { Icon=trayIcon, Text="Administrator broker enabled", ContextMenuStrip=menu, Visible=true };
            tray.DoubleClick+=delegate { ShowStatus(); };
            new Thread(()=> { Listen(ready); }) { IsBackground=true }.Start();
        }
        void ShowStatus() {
            string text; lock(sync) text="Approvals waiting: "+queue.Count+"\r\nRunning commands: "+running.Count+"\r\n\r\n"+String.Join("\r\n",running.Values.Select(v=>Wire.Json().Serialize(v)));
            MessageBox.Show(text,"Administrator execution broker",MessageBoxButtons.OK,MessageBoxIcon.Information);
        }
        public static PipeSecurity PipePolicy(string userSid) {
            var security=new PipeSecurity();
            security.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(WellKnownSidType.NetworkSid,null),PipeAccessRights.FullControl,AccessControlType.Deny));
            security.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(userSid),PipeAccessRights.ReadWrite|PipeAccessRights.Synchronize,AccessControlType.Allow));
            // Only elevated administrators and SYSTEM can create subsequent server instances.
            security.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid,null),PipeAccessRights.FullControl,AccessControlType.Allow));
            security.AddAccessRule(new PipeAccessRule(new SecurityIdentifier(WellKnownSidType.LocalSystemSid,null),PipeAccessRights.FullControl,AccessControlType.Allow));
            return security;
        }
        void Listen(string ready) {
            bool announced=false;
            while (!stopping) {
                var security=PipePolicy(sid);
                NamedPipeServerStream pipe;
                try { pipe=new NamedPipeServerStream(PipeName,PipeDirection.InOut,254,PipeTransmissionMode.Byte,PipeOptions.Asynchronous,4096,4096,security); }
                catch(Exception error) { listenerError=error.GetType().Name+": "+error.Message; Post(Stop); return; }
                lock(sync) { if(stopping) { pipe.Dispose(); return; } listening=pipe; }
                availability.Set();
                if (!announced) { announced=true; if(!String.IsNullOrEmpty(ready)) using(var signal=EventWaitHandle.OpenExisting(ready)) signal.Set(); }
                try { pipe.WaitForConnection(); } catch(ObjectDisposedException) { return; } catch(IOException) { pipe.Dispose(); continue; }
                availability.Reset();
                lock(sync) if(listening==pipe) listening=null;
                if(Interlocked.Increment(ref connections)>128) { Interlocked.Decrement(ref connections); pipe.Dispose(); continue; }
                new Thread(()=> { Receive(pipe); }) { IsBackground=true }.Start();
            }
        }
        void Receive(NamedPipeServerStream pipe) {
            Work work=null; bool admitted=false;
            try {
                string client=null; pipe.RunAsClient(delegate { client=WindowsIdentity.GetCurrent().User.Value; }); uint peer;
                if(client!=sid || !GetNamedPipeClientProcessId(pipe.SafePipeHandle,out peer) || Process.GetProcessById((int)peer).SessionId!=session) throw new InvalidDataException("Client account/session mismatch");
                long peerTicks=Process.GetProcessById((int)peer).StartTime.ToUniversalTime().ToFileTimeUtc();
                var message=Wire.Receive(pipe); string op=message["op"] as string;
                if(op=="status") { Wire.Only(message,"op"); lock(sync) Wire.Send(pipe,new {ok=true,operation="broker-status",broker_pid=Process.GetCurrentProcess().Id,in_job=SessionLaunch.InJob(),accepting=!stopping,pending=queue.Count,active=running.Values.ToArray(),history=history.ToArray()}); return; }
                if(op!="submit" && op!="stop") throw new InvalidDataException("Only submit/status/stop are supported; approval is broker-owned");
                Wire.Only(message,op=="submit" ? new[]{"op","request"} : new[]{"op"});
                var request=op=="submit" ? new Request((Dictionary<string,object>)message["request"]) : ControlRequest();
                work=new Work {Peer=(int)peer,PeerTicks=peerTicks,Request=request,Pipe=pipe,Stop=op=="stop"};
                lock(sync) {
                    if(stopping || queue.Count>=100) throw new InvalidDataException("Broker stopping or queue full");
                    work.Ticket=++sequence; queue.Enqueue(work);admitted=true;
                    Wire.Send(pipe,new {state="queued",request_id=work.Id,ticket=work.Ticket,broker_pid=Process.GetCurrentProcess().Id});
                }
                Post(Pump);
                // A submit connection is write-once. EOF/extra input cannot grant consent.
                pipe.ReadByte();
            } catch(Exception error) {
                if(!admitted) try { Wire.Send(pipe,Wire.Failure(stopping?"broker_stopping":"invalid_request",error.Message)); } catch(IOException) {} catch(ObjectDisposedException) {}
            } finally {
                if(admitted && !work.Completed) { work.Cancelled=true; Post(delegate { if(work.Dialog!=null) work.Dialog.Close(); Pump(); }); }
                if(!admitted) pipe.Dispose(); Interlocked.Decrement(ref connections);
            }
        }
        public static Request ControlRequest() {
            string exe=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),"whoami.exe"); string hash;
            using(var file=File.OpenRead(exe)) using(var sha=SHA256.Create()) hash=BitConverter.ToString(sha.ComputeHash(file)).Replace("-","").ToLowerInvariant();
            return new Request(new Dictionary<string,object> {{"schema",1},{"task","Disable administrator execution"},{"thread_name","Broker control"},{"reason","Stop accepting requests and cancel pending approvals"},{"changes","Already-started commands finish under supervision; no process is killed"},{"cwd",Environment.GetFolderPath(Environment.SpecialFolder.System)},{"targets",new object[]{"This session's elevated broker"}},{"command",new object[]{exe,"/user"}},{"bindings",new Dictionary<string,object>{{exe,hash}}}});
        }
        void Complete(Work work,Dictionary<string,object> result) {
            result["request_id"]=work.Id; result["ticket"]=work.Ticket; result["operation"]=work.Stop ? "broker-stop" : "run";
            result["execution_model"]="elevated_broker"; result["broker_pid"]=Process.GetCurrentProcess().Id;
            work.Completed=true;
            lock(sync) { running.Remove(work.Id); history.Add(new {request_id=work.Id,ticket=work.Ticket,task=Cut(work.Request.TaskName),thread_name=Cut(work.Request.ThreadName),ok=result["ok"],failure_kind=result.ContainsKey("failure_kind")?result["failure_kind"]:null}); if(history.Count>100) history.RemoveAt(0); }
            try { Wire.Send(work.Pipe,result); } catch(IOException) {} catch(ObjectDisposedException) {} finally { work.Pipe.Dispose(); }
            Post(delegate { if(stopping) FinishStop(); });
        }
        bool Alive(Work work) { try { var peer=Process.GetProcessById(work.Peer);return !work.Cancelled && !peer.HasExited && peer.StartTime.ToUniversalTime().ToFileTimeUtc()==work.PeerTicks; } catch(ArgumentException) { return false; } }
        void Pump() {
            if(showing || stopping) return;
            Work work; lock(sync) { if(queue.Count==0)return; work=queue.Dequeue(); }
            if(!Alive(work)) { Complete(work,Wire.Failure("owner_disconnected","Request owner disconnected before approval")); Post(Pump); return; }
            showing=true; currentApproval=work; BindingLease lease=null;
            try {
                if(!work.Stop) lease=new BindingLease(work.Request);
                using(var promptMutex=new Mutex(false,@"Local\Darka.WindowsElevation.Prompt")) {
                    try { promptMutex.WaitOne(); } catch(AbandonedMutexException) { throw new IOException("owner_recovery_required: old prompt owner was interrupted; confirm it is settled before retry"); }
                    try {
                        using(var dialog=new ApprovalForm(work.Request,false,work.Stop)) {
                            work.Dialog=dialog;
                            bool accepted=dialog.ShowDialog()==DialogResult.OK;
                            string feedback=dialog.Feedback.Text; work.Dialog=null;
                            if(!accepted || !Alive(work)) { var cancelled=Wire.Failure(stopping?"broker_stopping":work.Cancelled?"owner_disconnected":"user_declined","No command launched"); cancelled["feedback"]=feedback; Complete(work,cancelled); }
                            else if(work.Stop) { Complete(work,new Dictionary<string,object>{{"ok",true},{"launched",false},{"feedback",feedback}}); Stop(); }
                            else {
                                var held=lease; lease=null;
                                new Thread(()=> { Run(work,held,feedback); }) {IsBackground=true}.Start();
                            }
                        }
                    } finally { promptMutex.ReleaseMutex(); }
                }
            } catch(Exception error) { Complete(work,Wire.Failure("input_or_approval_failed",error.Message)); }
            finally { if(lease!=null)lease.Dispose(); currentApproval=null; showing=false; if(stopping)FinishStop();else Post(Pump); }
        }
        sealed class Output { public string Text; public bool Truncated; }
        static Output Capture(StreamReader reader) {
            var tail=new StringBuilder(); var buffer=new char[4096]; long count=0; int got;
            while((got=reader.Read(buffer,0,buffer.Length))>0) {count+=got;tail.Append(buffer,0,got);if(tail.Length>16000)tail.Remove(0,tail.Length-16000);}
            return new Output {Text=tail.ToString(),Truncated=count>16000};
        }
        static string Cut(string value) {return value.Length>160?value.Substring(0,160):value;}
        void Run(Work work,BindingLease lease,string feedback) {
            var result=Wire.Failure("launch_failed","Command did not start");
            try {
                using(lease) using(var process=new Process()) {
                    process.StartInfo=new ProcessStartInfo {FileName=work.Request.Command[0],Arguments=String.Join(" ",work.Request.Command.Skip(1).Select(Request.Quote)),WorkingDirectory=work.Request.Cwd,UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true};
                    lock(sync) {
                        if(stopping || !Alive(work)) throw new IOException("Broker disabled or owner disconnected before launch");
                        if(!process.Start()) throw new IOException("Command did not start");
                        result["launched"]=true;result["elevated"]=true;
                        running[work.Id]=new {request_id=work.Id,pid=process.Id,task=Cut(work.Request.TaskName),thread_name=Cut(work.Request.ThreadName),started_utc=DateTime.UtcNow.ToString("o")};
                    }
                    var stdout=Task.Factory.StartNew(()=>Capture(process.StandardOutput)); var stderr=Task.Factory.StartNew(()=>Capture(process.StandardError));
                    process.WaitForExit(); Task.WaitAll(stdout,stderr);
                    result=new Dictionary<string,object>{{"ok",process.ExitCode==0},{"launched",true},{"elevated",true},{"command_exit_code",process.ExitCode},{"worker_exit_code",null},{"stdout",stdout.Result.Text},{"stderr",stderr.Result.Text},{"stdout_truncated",stdout.Result.Truncated},{"stderr_truncated",stderr.Result.Truncated},{"failure_kind",process.ExitCode==0?null:"command_failed"}};
                }
            } catch(Exception error) { result["error"]=error.Message; }
            result["feedback"]=feedback; Complete(work,result);
        }
        void Stop() {
            if(stopping)return;
            Program.WriteRecord(sid,session,false,listenerError);availability.Set();
            Work[] pending; lock(sync) {stopping=true;pending=queue.ToArray();queue.Clear();if(listening!=null)listening.Dispose();}
            if(currentApproval!=null && currentApproval.Dialog!=null) {currentApproval.Cancelled=true;currentApproval.Dialog.Close();}
            foreach(var work in pending) Complete(work,Wire.Failure("broker_stopping","Broker disabled before approval"));
            tray.Text="Administrator broker draining active commands"; FinishStop();
        }
        void FinishStop() {lock(sync)if(running.Count!=0 || showing)return;tray.Visible=false;tray.Dispose();trayIcon.Dispose();availability.Dispose();dispatcher.Dispose();ExitThread();}
    }

    static class Program {
        public static void WriteRecord(string sid,int session,bool accepting,string error=null) {
            string root=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),"Darka.WindowsElevationGate");
            string record=Path.Combine(root,"session-"+sid+"-"+session+".json");
            if(File.Exists(record) && ((File.GetAttributes(record)&FileAttributes.ReparsePoint)!=0 || !Protected(record)))throw new IOException("Session identity record is not protected");
            string pending=Path.Combine(root,Guid.NewGuid().ToString("N")+".pending.json");
            var process=Process.GetCurrentProcess();
            File.WriteAllText(pending,Wire.Json().Serialize(new {pid=process.Id,ticks=process.StartTime.ToUniversalTime().ToFileTimeUtc(),accepting=accepting,failure_kind=error==null?null:"listener_failed",error=error}));
            var acl=new FileSecurity();acl.SetOwner(new SecurityIdentifier("S-1-5-32-544"));acl.SetAccessRuleProtection(true,false);
            foreach(string owner in new[]{"S-1-5-18","S-1-5-32-544"})acl.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier(owner),FileSystemRights.FullControl,AccessControlType.Allow));
            acl.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier("S-1-5-32-545"),FileSystemRights.ReadAndExecute,AccessControlType.Allow));File.SetAccessControl(pending,acl);
            if(File.Exists(record))File.Replace(pending,record,null);else File.Move(pending,record);
        }
        public static bool Protected(string path) {
            FileSystemSecurity acl=Directory.Exists(path)?(FileSystemSecurity)Directory.GetAccessControl(path):File.GetAccessControl(path);
            string owner=acl.GetOwner(typeof(SecurityIdentifier)).Value;
            if(owner!="S-1-5-18" && owner!="S-1-5-32-544")return false;
            foreach(FileSystemAccessRule rule in acl.GetAccessRules(true,true,typeof(SecurityIdentifier))) {
                string sid=rule.IdentityReference.Value;
                if(rule.AccessControlType==AccessControlType.Allow && sid!="S-1-5-18" && sid!="S-1-5-32-544" && ((int)rule.FileSystemRights & 0x500D0156)!=0)return false;
            }
            return true;
        }
        [STAThread] static int Main(string[] args) {
            try {
                if(args.Length==1 && args[0]=="--self-test") {SelfTest();return 0;}
                if(args.Length==1 && args[0]=="--preview") {Application.EnableVisualStyles();using(var form=new ApprovalForm(Broker.ControlRequest(),true)){Console.WriteLine(Wire.Json().Serialize(new {preview_approved=form.ShowDialog()==DialogResult.OK,launched=false}));}return 0;}
                var identity=WindowsIdentity.GetCurrent();
                string exe=Process.GetCurrentProcess().MainModule.FileName;
                string root=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),"Darka.WindowsElevationGate");
                if(!exe.StartsWith(root+"\\",StringComparison.OrdinalIgnoreCase))throw new InvalidOperationException("Protected installed broker required");
                for(string path=exe;path.Length>=root.Length;path=Path.GetDirectoryName(path))if((File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0 || !Protected(path))throw new InvalidOperationException("Administrator-owned/write-protected broker required");
                if(args.Length==1 && args[0]=="--launch-from-desktop")return SessionLaunch.LaunchFromDesktop();
                if(args.Length==2 && args[0]=="--session-bootstrap")return SessionLaunch.Bootstrap(args[1]);
                if(args.Length==2 && args[0]=="--detached-session-bootstrap")return SessionLaunch.Bootstrap(args[1],false);
                if(!new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator) || Process.GetCurrentProcess().SessionId==0)throw new InvalidOperationException("Elevated interactive broker required");
                string ready=args.Length==2 && (args[0]=="--ready-event" || args[0]=="--detached-ready-event")?args[1]:null;
                if(ready!=null) {
                    const string prefix=@"Local\Darka.WindowsElevation.BrokerReady.";Guid nonce;
                    if(!ready.StartsWith(prefix,StringComparison.Ordinal) || !Guid.TryParseExact(ready.Substring(prefix.Length),"N",out nonce))throw new InvalidOperationException("Invalid readiness event");
                    if(args[0]=="--ready-event" && SessionLaunch.InJob())return SessionLaunch.BreakAway(ready,true);
                }
                if(SessionLaunch.InJob())throw new InvalidOperationException("Broker is job-attached; use broker-start with desktop session launch");
                using(var singleton=new Mutex(false,@"Local\Darka.WindowsElevation.BrokerInstance."+identity.User.Value+"."+Process.GetCurrentProcess().SessionId)) {
                    bool acquired;try{acquired=singleton.WaitOne(0);}catch(AbandonedMutexException){acquired=true;}
                    if(!acquired)return 2;
                    try {Application.EnableVisualStyles();Application.Run(new Broker(ready));}finally{singleton.ReleaseMutex();}
                }
                return 0;
            } catch(Exception error) {
                if(args.Length==1 && args[0]=="--self-test")Console.Error.WriteLine(error.Message);
                else MessageBox.Show(error.Message,"Elevation broker stopped safely",MessageBoxButtons.OK,MessageBoxIcon.Error);
                return 1;
            }
        }
        static void SelfTest() {
            int checks=0;
            using(var icon=TrayArtwork.WhiteShield())using(var bitmap=icon.ToBitmap()) {
                bool opaque=false,transparent=false;
                for(int y=0;y<bitmap.Height;y++)for(int x=0;x<bitmap.Width;x++) {
                    var pixel=bitmap.GetPixel(x,y);
                    if(pixel.A==0)transparent=true;
                    else {
                        // Native icon conversion premultiplies antialiased edge pixels.
                        if(pixel.R!=pixel.G || pixel.G!=pixel.B || (pixel.A==255 && pixel.R!=255))throw new Exception("Tray shield is not monochrome white");
                        if(pixel.A==255)opaque=true;
                    }
                }
                if(!opaque || !transparent)throw new Exception("Tray shield lacks artwork or transparency");++checks;
            }
            string userSid=WindowsIdentity.GetCurrent().User.Value;
            var pipeRules=Broker.PipePolicy(userSid).GetAccessRules(true,true,typeof(SecurityIdentifier)).Cast<PipeAccessRule>().ToArray();
            if(!pipeRules.Any(r=>r.IdentityReference.Value=="S-1-5-32-544" && r.AccessControlType==AccessControlType.Allow && r.PipeAccessRights==PipeAccessRights.FullControl))throw new Exception("Elevated listener cannot create subsequent pipe instances");
            if(pipeRules.Any(r=>r.IdentityReference.Value==userSid && r.AccessControlType==AccessControlType.Allow && (r.PipeAccessRights&PipeAccessRights.CreateNewInstance)!=0))throw new Exception("Client can create server instances");++checks;
            if(Request.Quote("a b")!="\"a b\"" || Request.Quote("")!="\"\"" || Request.Quote("a\\b")!="a\\b")throw new Exception("Argument quoting failed");++checks;
            try{Wire.Only(new Dictionary<string,object>{{"op","submit"},{"accepted",true}},"op","request");throw new Exception("Forged consent accepted");}catch(InvalidDataException){++checks;}
            try{Request.PathName(@"\\server\share\file.exe");throw new Exception("Remote path accepted");}catch(InvalidDataException){++checks;}
            try{Request.PathName(@"C:\file.exe:stream");throw new Exception("Alternate stream accepted");}catch(InvalidDataException){++checks;}
            using(var stream=new MemoryStream()){stream.Write(BitConverter.GetBytes(64000),0,4);stream.Position=0;try{Wire.Receive(stream);throw new Exception("Oversize frame accepted");}catch(InvalidDataException){++checks;}}
            var request=Broker.ControlRequest();using(var lease=new BindingLease(request)){++checks;}
            string root=Path.Combine(Path.GetTempPath(),"broker-selftest-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);
            string script=Path.Combine(root,"payload.ps1");
            try {
                File.WriteAllText(script,"Write-Output 'fixture'");string digest;
                using(var input=File.OpenRead(script))using(var sha=SHA256.Create())digest=BitConverter.ToString(sha.ComputeHash(input)).Replace("-","").ToLowerInvariant();
                var data=new Dictionary<string,object>{{"schema",1},{"task","Self-test"},{"thread_name","Self-test"},{"reason","No execution"},{"changes","None"},{"cwd",root},{"targets",new object[]{script}},{"command",new object[]{request.Command[0],script}},{"bindings",new Dictionary<string,object>{{request.Command[0],request.Bindings[request.Command[0]]},{script,digest}}}};
                data["accepted"]=true;try{new Request(data);throw new Exception("Request consent accepted");}catch(InvalidDataException){++checks;}data.Remove("accepted");
                var bound=new Request(data);
                using(var held=new BindingLease(bound)) {
                    try{File.WriteAllText(script,"changed");throw new Exception("Leased input was writable");}catch(IOException){++checks;}
                    try{Directory.Move(root,root+"-moved");throw new Exception("Leased ancestor was replaceable");}catch(IOException){++checks;}
                }
                File.WriteAllText(script,"changed");try{using(var held=new BindingLease(bound)){}throw new Exception("Changed input accepted");}catch(IOException){++checks;}
            } finally {if(File.Exists(script))File.Delete(script);Directory.Delete(root);}
            Console.WriteLine(Wire.Json().Serialize(new {ok=true,self_test_checks=checks,launched=false}));
        }
    }
}
