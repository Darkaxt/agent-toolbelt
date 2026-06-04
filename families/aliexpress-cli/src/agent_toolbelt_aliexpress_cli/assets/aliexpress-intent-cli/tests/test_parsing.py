import unittest
from pathlib import Path

from aliexpress_intent_cli.parsing import parse_product, parse_reviews, parse_search


FIXTURES = Path(__file__).resolve().parent / "fixtures"


class AliExpressParsingTests(unittest.TestCase):
    def test_parse_search_extracts_clean_results(self):
        html = (FIXTURES / "search_results.html").read_text(encoding="utf-8")

        payload = parse_search(html, query="30L trash bin", page=1, url="https://www.aliexpress.com/wholesale")

        self.assertEqual(payload["result_count"], 2)
        first = payload["results"][0]
        self.assertEqual(first["item_id"], "1005001111111111")
        self.assertEqual(first["title"], "30L Stainless Steel Trash Bin")
        self.assertEqual(first["price_text"], "€24.99")
        self.assertTrue(first["free_delivery"])
        self.assertEqual(first["product_link"], "https://www.aliexpress.com/item/1005001111111111.html")

    def test_parse_product_extracts_description_price_shipping_and_variants(self):
        html = (FIXTURES / "item_detail.html").read_text(encoding="utf-8")

        payload = parse_product(html, item_id="1005001111111111", url="https://www.aliexpress.com/item/1005001111111111.html")

        self.assertEqual(payload["title"], "30L Stainless Steel Trash Bin")
        self.assertIn("soft close", payload["description"])
        self.assertEqual(payload["price_summary"]["price_text"], "€24.99")
        self.assertTrue(payload["price_summary"]["free_delivery"])
        self.assertGreaterEqual(len(payload["price_summary"]["details"]), 2)
        self.assertEqual(payload["shipping_summary"]["details"][0]["text"], "Free delivery to Cyprus by Jun 18")
        self.assertEqual(payload["seller"]["store_name"], "Clean Home Store")
        self.assertEqual(len(payload["variants"]), 2)
        self.assertEqual(payload["specs"][0]["name"], "Capacity")
        self.assertEqual(payload["product_link"], "https://www.aliexpress.com/item/1005001111111111.html")

    def test_parse_reviews_extracts_comments(self):
        html = (FIXTURES / "reviews.html").read_text(encoding="utf-8")

        reviews = parse_reviews(html, limit=1)

        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["rating"], 5)
        self.assertIn("lid closes quietly", reviews[0]["body"])
        self.assertEqual(reviews[0]["author"], "A***s")


if __name__ == "__main__":
    unittest.main()
