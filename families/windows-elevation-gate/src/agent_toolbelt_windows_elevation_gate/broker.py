"""Unprivileged, framed-JSON client. Only the protected broker owns consent."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
if os.name == 'nt':
    import msvcrt
    import winreg

from .native import Native, Mutex, PREFIX


class BrokerUnavailable(RuntimeError):
    pass


class BrokerStopping(RuntimeError):
    pass


class CompletionUnknown(RuntimeError):
    def __init__(self, receipt):
        super().__init__('Broker response lost; execution/completion is unverified. Do not resubmit automatically; inspect broker status/history.')
        self.receipt = receipt


def send(stream, value):
    data = json.dumps(value, ensure_ascii=False).encode('utf-8')
    if len(data) > 32000:
        raise ValueError('Request exceeds bounded protocol')
    framed = memoryview(struct.pack('<I', len(data)) + data)
    while framed:
        written = stream.write(framed)
        if not written:
            raise EOFError('Broker disconnected while submitting the request')
        framed = framed[written:]
    stream.flush()


def receive(stream):
    def exact(count):
        data = bytearray()
        while len(data) < count:
            block = stream.read(count - len(data))
            if not block:
                raise EOFError('Broker disconnected; command completion is not established')
            data.extend(block)
        return bytes(data)
    count, = struct.unpack('<I', exact(4))
    if not 2 <= count <= 240000:
        raise ValueError('Invalid broker response length')
    value = json.loads(exact(count))
    if not isinstance(value, dict):
        raise ValueError('Invalid broker response')
    return value


def root_path():
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion',
                        0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
        program_files = winreg.QueryValueEx(key, 'ProgramFilesDir')[0]
    return Path(program_files) / 'Darka.WindowsElevationGate'


def current_sid():
    # Token information, not a username or environment-supplied identity.
    adv = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    token, needed = w.HANDLE(), w.DWORD()
    kernel.GetCurrentProcess.restype = w.HANDLE
    adv.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE)]
    adv.GetTokenInformation.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD)]
    kernel.CloseHandle.argtypes = [w.HANDLE]
    if not adv.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        adv.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))
        data = ctypes.create_string_buffer(needed.value)
        if not adv.GetTokenInformation(token, 1, data, len(data), ctypes.byref(needed)):
            raise ctypes.WinError(ctypes.get_last_error())
        return sid_text(ctypes.c_void_p.from_buffer(data).value)
    finally:
        kernel.CloseHandle(token)


def sid_text(sid):
    adv = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    adv.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(w.LPWSTR)]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    text = w.LPWSTR()
    if not adv.ConvertSidToStringSidW(sid, ctypes.byref(text)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return text.value
    finally:
        kernel.LocalFree(ctypes.cast(text, ctypes.c_void_p))


def protected(path):
    path = Path(path)
    for component in (*reversed(path.parents), path):
        if component.lstat().st_file_attributes & 0x400:
            raise ValueError('Redirected broker installation is unsupported')
    adv = ctypes.WinDLL('advapi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    adv.GetNamedSecurityInfoW.argtypes = [w.LPWSTR, ctypes.c_int, w.DWORD] + [ctypes.POINTER(ctypes.c_void_p)] * 5
    adv.GetAce.argtypes = [ctypes.c_void_p, w.DWORD, ctypes.POINTER(ctypes.c_void_p)]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    owner, dacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    # OWNER_SECURITY_INFORMATION | DACL_SECURITY_INFORMATION
    error = adv.GetNamedSecurityInfoW(str(path), 1, 5, ctypes.byref(owner), None, ctypes.byref(dacl), None, ctypes.byref(descriptor))
    if error:
        raise ctypes.WinError(error)
    try:
        trusted = {'S-1-5-18', 'S-1-5-32-544'}
        if sid_text(owner) not in trusted or not dacl:
            raise ValueError('Broker installation must be administrator-owned with a restrictive DACL')
        count = ctypes.c_ushort.from_address(dacl.value + 4).value
        for index in range(count):
            ace = ctypes.c_void_p()
            if not adv.GetAce(dacl, index, ctypes.byref(ace)):
                raise ctypes.WinError(ctypes.get_last_error())
            kind = ctypes.c_ubyte.from_address(ace.value).value
            if kind not in (0, 1):
                raise ValueError('Unsupported broker installation ACE')
            mask = ctypes.c_uint32.from_address(ace.value + 4).value
            if kind == 0 and sid_text(ace.value + 8) not in trusted and mask & 0x500D0156:
                raise ValueError('Broker installation is writable without administrator elevation')
    finally:
        kernel.LocalFree(descriptor)


def installation():
    root = root_path()
    try:
        for path in (root, root / 'active.json'):
            protected(path)
        metadata = json.loads((root / 'active.json').read_text(encoding='utf-8-sig'))
        release, digest = metadata['release'], metadata['sha256']
        if len(release) != 16 or len(digest) != 64 or any(c not in '0123456789abcdef' for c in release + digest):
            raise ValueError('Invalid protected release pointer')
        exe = root / 'releases' / release / 'WindowsElevationBroker.exe'
        for path in (exe.parent.parent, exe.parent, exe):
            protected(path)
        if hashlib.sha256(exe.read_bytes()).hexdigest() != digest:
            raise ValueError('Protected broker digest mismatch')
        return root, exe
    except FileNotFoundError as exc:
        raise BrokerUnavailable('Protected broker is not installed; use the documented installer') from exc


def identity():
    native = Native()
    return native, 'Darka.WindowsElevation.Broker.' + current_sid() + '.' + str(native.session())


@contextmanager
def connection():
    root, exe = installation()
    native, name = identity()
    record_path = root / ('session-' + current_sid() + '-' + str(native.session()) + '.json')
    try:
        protected(record_path)
        record = json.loads(record_path.read_text())
    except FileNotFoundError as exc:
        raise BrokerUnavailable('Broker has not been started in this login session') from exc
    process, _ = native.process(record['pid'], record['ticks'])
    if not process:
        raise BrokerUnavailable('Broker is not running in this login session' + (': ' + record['error'] if record.get('error') else ''))
    if record.get('accepting') is False:
        native.close(process)
        raise BrokerStopping('Broker is draining accepted commands; no new approvals' + (': ' + record['error'] if record.get('error') else ''))
    stream = available = None
    try:
        native.k.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
        size = w.DWORD(32768)
        image = ctypes.create_unicode_buffer(size.value)
        if not native.k.QueryFullProcessImageNameW(process, 0, image, ctypes.byref(size)) or Path(image.value) != exe:
            raise ValueError('Broker PID does not identify the protected installed executable')
        native.k.OpenEventW.argtypes, native.k.OpenEventW.restype = [w.DWORD, w.BOOL, w.LPCWSTR], w.HANDLE
        available = native.k.OpenEventW(0x100000, False, 'Local\\' + name + '.Available')
        if not available:
            raise BrokerUnavailable('Broker availability event is missing')
        while True:
            try:
                native.k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
                native.k.CreateFileW.restype = w.HANDLE
                # Request data/synchronize rights, NOT generic write/create-instance.
                opened = native.k.CreateFileW('\\\\.\\pipe\\' + name, 0x100003, 0, None, 3, 0x110000, None)
                if opened == ctypes.c_void_p(-1).value:
                    raise ctypes.WinError(ctypes.get_last_error())
                try:
                    descriptor = msvcrt.open_osfhandle(opened, os.O_RDWR | os.O_BINARY)
                except BaseException:
                    native.close(opened)
                    raise
                stream = os.fdopen(descriptor, 'r+b', buffering=0)
                break
            except OSError as exc:
                if getattr(exc, 'winerror', None) not in (2, 231):
                    raise
                if json.loads(record_path.read_text()).get('accepting') is False:
                    raise BrokerStopping('Broker disabled while connecting') from exc
                if native.wait(available, process) == 1:
                    raise BrokerUnavailable('Broker exited before connection') from exc
        native.k.GetNamedPipeServerProcessId.argtypes = [w.HANDLE, ctypes.POINTER(w.ULONG)]
        peer = w.ULONG()
        handle = msvcrt.get_osfhandle(stream.fileno())
        if not native.k.GetNamedPipeServerProcessId(handle, ctypes.byref(peer)) or peer.value != record['pid']:
            raise ValueError('Pipe server is not the verified protected broker')
        yield stream, process, native
    finally:
        if stream:
            stream.close()
        native.close(available)
        native.close(process)


def exchange(message):
    with connection() as (stream, process, native):
        send(stream, message)
        receipt = {}
        try:
            result = receive(stream)
            if result.get('state') == 'queued':
                receipt = result
                print(json.dumps(result), file=sys.stderr, flush=True)
                result = receive(stream)
        except (OSError, EOFError) as exc:
            if message['op'] in ('submit', 'stop'):
                raise CompletionUnknown(receipt) from exc
            raise
        if message['op'] == 'stop' and result.get('ok'):
            native.wait(process)
        return result


def status():
    try:
        result = exchange({'op': 'status'})
        result.update(read_only=True, running=True)
        return result
    except BrokerUnavailable as exc:
        return {'ok': True, 'operation': 'broker-status', 'read_only': True, 'running': False, 'accepting': False, 'reason': str(exc)}
    except BrokerStopping as exc:
        return {'ok': True, 'operation': 'broker-status', 'read_only': True, 'running': True, 'accepting': False, 'reason': str(exc)}


def start():
    native = Native()
    with Mutex(PREFIX + '.BrokerStartup', native):
        try:
            result = exchange({'op': 'status'})
        except BrokerUnavailable:
            result = None
        if result is not None:
            if not result.get('accepting'):
                raise BrokerStopping('Broker is not accepting requests; inspect its protected session diagnostic')
            if result.get('in_job') is not False:
                raise BrokerUnavailable('Existing broker has no verified independent lifecycle; stop it through its tray before upgrading/restarting')
            return result
        _, exe = installation()
        launch = subprocess.run([str(exe), '--launch-from-desktop'], capture_output=True,
                                text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            startup = json.loads(launch.stdout)
        except (ValueError, TypeError) as exc:
            raise BrokerUnavailable('Desktop launch returned no structured result: ' + launch.stderr[-2000:]) from exc
        if not isinstance(startup, dict):
            raise BrokerUnavailable('Desktop launch returned an invalid result')
        if not startup.get('ok'):
            return startup
        if launch.returncode or startup.get('in_job') is not False or startup.get('launch_owner') != 'desktop_explorer':
            raise BrokerUnavailable('Desktop launcher did not verify independent startup')
        result = exchange({'op': 'status'})
        if not result.get('accepting'):
            raise BrokerStopping('Broker stopped during startup; inspect its protected session diagnostic')
        if result.get('in_job') is not False:
            raise BrokerUnavailable('Broker did not verify job-independent lifecycle')
        result['launch_owner'] = startup['launch_owner']
        return result


def preview(request):
    _, exe = installation()
    result = subprocess.run([str(exe), '--preview-request'], input=json.dumps(request),
                            capture_output=True, text=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise BrokerUnavailable('Native preview failed: ' + result.stderr[-2000:])
    value = json.loads(result.stdout)
    if not isinstance(value, dict) or value.get('launched') is not False:
        raise BrokerUnavailable('Invalid native preview result')
    return value


def run(request):
    return exchange({'op': 'submit', 'request': request})


def stop():
    return exchange({'op': 'stop'})
