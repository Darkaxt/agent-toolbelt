"""Reproduce launch/COM activation ordering, without touching a real mailbox."""
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

SRC=Path(__file__).resolve().parents[1]/'src'
sys.path.insert(0,str(SRC))
from outlook_classic_mail_client import client


class StartupLifecycleTests(unittest.TestCase):
    def modules(self, events):
        app=types.SimpleNamespace(Session=object())
        py=types.ModuleType('pythoncom')
        py.CoInitialize=lambda:events.append('initialize')
        parent=types.ModuleType('win32com')
        com=types.ModuleType('win32com.client')
        com.Dispatch=mock.Mock(side_effect=lambda name:events.append('attach') or app)
        com.GetActiveObject=mock.Mock(side_effect=AssertionError('This Office build does not expose the application in the ROT'))
        parent.client=com
        return {'pythoncom':py,'win32com':parent,'win32com.client':com}

    def test_cold_start_waits_for_desktop_before_single_com_binding(self):
        events=[]
        diagnostics=client.build_client_diagnostics('accounts')
        process=mock.Mock(pid=123)
        with mock.patch.dict(sys.modules,self.modules(events)):
            with mock.patch.object(client,'outlook_runtime_state',return_value={'process_running':False,'visible_window':False}), \
                 mock.patch.object(client,'interactive_outlook_launch_allowed',return_value=True), \
                 mock.patch.object(client,'resolve_outlook_executable',return_value=Path('Outlook.exe')), \
                 mock.patch.object(client.subprocess,'Popen',side_effect=lambda *a,**k:events.append('launch') or process), \
                 mock.patch.object(client,'wait_for_outlook_desktop',create=True,side_effect=lambda p:events.append('ready')):
                app,session=client.connect_outlook(diagnostics)
        self.assertIsNotNone(session)
        self.assertEqual(events,['initialize','launch','ready','attach'])

    def test_binding_failure_never_retries_or_launches_another_desktop(self):
        events=[]
        modules=self.modules(events)
        modules['win32com.client'].Dispatch=mock.Mock(side_effect=RuntimeError('Not registered'))
        with mock.patch.dict(sys.modules,modules), \
             mock.patch.object(client,'outlook_runtime_state',return_value={'process_running':True,'visible_window':True}):
            with self.assertRaises(client.OutlookComUnavailableError) as caught:
                client.connect_outlook(client.build_client_diagnostics('diagnostics-probe'))
        modules['win32com.client'].Dispatch.assert_called_once_with('Outlook.Application')
        modules['win32com.client'].GetActiveObject.assert_not_called()
        self.assertEqual(caught.exception.failure_kind,'outlook_dispatch_failed')

    def test_unready_desktop_prevents_com_attachment(self):
        events=[]
        modules=self.modules(events)
        with mock.patch.dict(sys.modules,modules), \
             mock.patch.object(client,'outlook_runtime_state',return_value={'process_running':False,'visible_window':False}), \
             mock.patch.object(client,'interactive_outlook_launch_allowed',return_value=True), \
             mock.patch.object(client,'resolve_outlook_executable',return_value=Path('Outlook.exe')), \
             mock.patch.object(client.subprocess,'Popen',return_value=mock.Mock(pid=123)), \
             mock.patch.object(client,'wait_for_outlook_desktop',create=True,side_effect=RuntimeError('Launcher exited without a desktop')):
            with self.assertRaises(client.OutlookComUnavailableError):
                client.connect_outlook(client.build_client_diagnostics('accounts'))
        self.assertNotIn('attach',events)
        modules['win32com.client'].Dispatch.assert_not_called()

    @unittest.skipUnless(sys.platform=='win32','Native Windows window observation')
    def test_untitled_outlook_support_window_is_not_a_ready_desktop(self):
        fake=mock.Mock()
        fake.IsWindowVisible.return_value=True
        fake.IsWindowEnabled.return_value=True
        fake.GetClassNameW.side_effect=lambda hwnd,buffer,count:setattr(buffer,'value','rctrl_renwnd32') or 1
        fake.GetWindowTextLengthW.return_value=0
        fake.EnumWindows.side_effect=lambda callback,param:callback(1,0)
        import ctypes
        with mock.patch.object(ctypes,'WinDLL',return_value=fake):
            self.assertFalse(client.outlook_visible_window())
        fake.GetClientRect.assert_not_called()

    @unittest.skipUnless(sys.platform=='win32','Native Windows window observation')
    def test_desktop_requires_visible_enabled_titled_content(self):
        import ctypes
        for visible,enabled,title,width,expected in (
            (True,True,20,800,True), (False,True,20,800,False),
            (True,False,20,800,False), (True,True,0,800,False),
            (True,True,20,0,False),
        ):
            with self.subTest(visible=visible,enabled=enabled,title=title,width=width):
                fake=mock.Mock()
                fake.IsWindowVisible.return_value=visible
                fake.IsWindowEnabled.return_value=enabled
                fake.IsIconic.return_value=False
                fake.GetClassNameW.side_effect=lambda hwnd,buffer,count:setattr(buffer,'value','rctrl_renwnd32') or 1
                fake.GetWindowTextLengthW.return_value=title
                def rectangle(hwnd,rect):
                    rect._obj.right=width
                    rect._obj.bottom=600
                    return True
                fake.GetClientRect.side_effect=rectangle
                fake.EnumWindows.side_effect=lambda callback,param:callback(1,0)
                with mock.patch.object(ctypes,'WinDLL',return_value=fake):
                    self.assertIs(client.outlook_visible_window(),expected)

    def test_minimized_desktop_is_reused_but_not_cold_start_readiness(self):
        import ctypes
        fake=mock.Mock()
        fake.IsWindowVisible.return_value=True
        fake.IsWindowEnabled.return_value=True
        fake.IsIconic.return_value=True
        fake.GetWindowTextLengthW.return_value=20
        fake.GetClassNameW.side_effect=lambda hwnd,buffer,count:setattr(buffer,'value','rctrl_renwnd32') or 1
        fake.EnumWindows.side_effect=lambda callback,param:callback(1,0)
        def empty(hwnd,rect):
            rect._obj.right=rect._obj.bottom=0
            return True
        fake.GetClientRect.side_effect=empty
        with mock.patch.object(ctypes,'WinDLL',return_value=fake):
            self.assertTrue(client.outlook_visible_window())
            self.assertFalse(client.outlook_visible_window(allow_minimized=False))

    def test_existing_minimized_desktop_never_launches_or_moves_windows(self):
        with mock.patch.object(client,'outlook_runtime_state',return_value={'process_running':True,'visible_window':True}),mock.patch.object(client,'launch_outlook_desktop') as launch:
            diagnostics={'operation':'accounts'}
            client.prepare_outlook_for_com(diagnostics)
            launch.assert_not_called()
            self.assertEqual(diagnostics['outlook_startup']['action'],'existing_visible_instance')

    def test_desktop_launch_requests_existing_window_reuse(self):
        with mock.patch.object(client,'resolve_outlook_executable',return_value=Path('Outlook.exe')),mock.patch.object(client.subprocess,'Popen',return_value=mock.Mock(pid=123)) as launch,mock.patch.object(client,'wait_for_outlook_desktop'):
            client.launch_outlook_desktop()
        self.assertEqual(launch.call_args.args[0],[str(Path('Outlook.exe')),'/recycle'])


if __name__=='__main__':unittest.main()
