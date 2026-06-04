import unittest

from aliexpress_intent_cli.identifiers import inspect_identifier, validate_browse_url


class AliExpressIdentifierTests(unittest.TestCase):
    def test_inspect_identifier_accepts_item_id_and_url(self):
        id_result = inspect_identifier("1005000000000000")
        url_result = inspect_identifier("https://www.aliexpress.com/item/1005000000000000.html?spm=test")

        self.assertTrue(id_result["supported"])
        self.assertEqual(id_result["identifier_type"], "item_id")
        self.assertEqual(id_result["url"], "https://www.aliexpress.com/item/1005000000000000.html")
        self.assertTrue(url_result["supported"])
        self.assertEqual(url_result["identifier_type"], "item_url")

    def test_inspect_identifier_rejects_unsupported_url(self):
        result = inspect_identifier("https://example.com/item/1005000000000000.html")

        self.assertFalse(result["supported"])
        self.assertEqual(result["identifier_type"], "unsupported_url")
        self.assertIn("unsupported_host", result["warnings"])

    def test_validate_browse_url_requires_aliexpress_absolute_url(self):
        self.assertEqual(
            validate_browse_url("https://www.aliexpress.com/wholesale?SearchText=bin"),
            "https://www.aliexpress.com/wholesale?SearchText=bin",
        )
        with self.assertRaisesRegex(ValueError, "absolute AliExpress URL"):
            validate_browse_url("/wholesale?SearchText=bin")
        with self.assertRaisesRegex(ValueError, "Unsupported AliExpress browse URL"):
            validate_browse_url("https://example.com/search")


if __name__ == "__main__":
    unittest.main()
