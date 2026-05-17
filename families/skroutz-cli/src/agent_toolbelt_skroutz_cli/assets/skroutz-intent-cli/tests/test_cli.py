import io
import json
import unittest
from contextlib import redirect_stdout

from skroutz_intent_cli import cli


class SkroutzIntentCLITests(unittest.TestCase):
    def test_parser_accepts_public_commands(self):
        parser = cli.build_parser()

        self.assertEqual(parser.parse_args(["inspect-identifier", "62956505"]).command, "inspect-identifier")
        self.assertEqual(parser.parse_args(["search", "iphone 17", "--pages", "2"]).pages, 2)
        self.assertEqual(parser.parse_args(["get", "62956505"]).command, "get")
        self.assertEqual(parser.parse_args(["offers", "62956505"]).command, "offers")
        self.assertEqual(parser.parse_args(["reviews", "62956505", "--limit", "3"]).limit, 3)
        self.assertEqual(parser.parse_args(["compare", "1", "2"]).identifiers, ["1", "2"])

    def test_cart_add_remove_require_confirmation(self):
        parser = cli.build_parser()

        with self.assertRaises(SystemExit):
            args = parser.parse_args(["cart", "add", "62956505"])
            cli.validate_args(parser, args)

        with self.assertRaises(SystemExit):
            args = parser.parse_args(["cart", "remove", "62956505"])
            cli.validate_args(parser, args)

        args = parser.parse_args(["cart", "add", "62956505", "--confirm-cart-add"])
        cli.validate_args(parser, args)
        self.assertEqual(args.cart_command, "add")

    def test_cart_list_requires_no_confirmation(self):
        parser = cli.build_parser()
        args = parser.parse_args(["cart", "list"])

        cli.validate_args(parser, args)

        self.assertEqual(args.cart_command, "list")

    def test_main_renders_structured_json(self):
        original_build_service = cli.build_service

        class FakeService:
            def search(self, **kwargs):
                return {"command": "search", "query": kwargs["query"], "results": []}

        cli.build_service = lambda: FakeService()
        try:
            with io.StringIO() as buffer, redirect_stdout(buffer):
                exit_code = cli.main(["search", "iphone"])
                payload = json.loads(buffer.getvalue())
        finally:
            cli.build_service = original_build_service

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["command"], "search")
        self.assertEqual(payload["query"], "iphone")


if __name__ == "__main__":
    unittest.main()
