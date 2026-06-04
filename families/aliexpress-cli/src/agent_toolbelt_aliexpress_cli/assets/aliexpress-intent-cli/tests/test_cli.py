import io
import json
import unittest
from contextlib import redirect_stdout

from aliexpress_intent_cli import cli


class AliExpressIntentCLITests(unittest.TestCase):
    def test_parser_accepts_public_commands_without_cart(self):
        parser = cli.build_parser()

        self.assertEqual(parser.parse_args(["inspect-identifier", "1005000000000000"]).command, "inspect-identifier")
        self.assertEqual(parser.parse_args(["search", "30L trash bin", "--pages", "2"]).pages, 2)
        self.assertTrue(parser.parse_args(["search", "30L trash bin", "--use-session"]).use_session)
        self.assertEqual(parser.parse_args(["browse", "--url", "https://www.aliexpress.com/wholesale?SearchText=bin"]).command, "browse")
        self.assertEqual(parser.parse_args(["get", "1005000000000000"]).command, "get")
        self.assertEqual(parser.parse_args(["reviews", "1005000000000000", "--limit", "3"]).limit, 3)
        self.assertEqual(parser.parse_args(["compare", "1", "2"]).identifiers, ["1", "2"])
        self.assertEqual(parser.parse_args(["session", "login", "--manual-confirm"]).session_command, "login")

        with self.assertRaises(SystemExit):
            parser.parse_args(["cart", "list"])

    def test_pages_are_bounded(self):
        parser = cli.build_parser()

        with self.assertRaises(SystemExit):
            args = parser.parse_args(["search", "bin", "--pages", "6"])
            cli.validate_args(parser, args)

    def test_main_renders_structured_json(self):
        original_build_service = cli.build_service

        class FakeService:
            def search(self, **kwargs):
                return {"command": "search", "query": kwargs["query"], "session_used": kwargs["use_session"], "results": []}

        cli.build_service = lambda: FakeService()
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["search", "30L trash bin", "--use-session"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.build_service = original_build_service

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "search")
        self.assertTrue(payload["session_used"])


if __name__ == "__main__":
    unittest.main()
