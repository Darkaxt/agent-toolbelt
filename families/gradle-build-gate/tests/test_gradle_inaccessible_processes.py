import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from agent_toolbelt_gradle_build_gate.gate import classify_process,LifecycleObserver,rearm_needed


class InaccessibleProcessTests(unittest.TestCase):
    def test_elevated_shell_without_readable_identity_does_not_block(self):
        self.assertEqual(classify_process({"name":"cmd.exe","command":None,"executable":None}),"unrelated")

    def test_shell_with_readable_executable_but_no_command_stays_ambiguous(self):
        self.assertEqual(classify_process({"name":"cmd.exe","command":None,
            "executable":"C:\\Windows\\System32\\cmd.exe"}),"ambiguous")

    def test_inaccessible_java_stays_fail_closed(self):
        self.assertEqual(classify_process({"name":"java.exe","command":None,"executable":None}),"ambiguous")

    def test_polled_blocking_process_is_waited_for_not_resubscribed(self):
        observer=LifecycleObserver(())
        observer.pids,observer.polled={1},{2}
        self.assertFalse(rearm_needed(observer,{"processes":[{"pid":1,"name":"java.exe"}]}))
        self.assertFalse(rearm_needed(observer,{"processes":[{"pid":2,"name":"java.exe"}]}))
        self.assertTrue(rearm_needed(observer,{"processes":[{"pid":3,"name":"java.exe"}]}))

    def test_observer_without_subscription_never_rearms(self):
        self.assertFalse(rearm_needed(object(),{"processes":[{"pid":3,"name":"java.exe"}]}))


if __name__=="__main__":
    unittest.main()
