import unittest

from skroutz_intent_cli.identifiers import inspect_identifier
from skroutz_intent_cli.parsing import _price_number, _price_text, parse_cart, parse_product, parse_reviews, parse_search


SEARCH_HTML = """
<html><body>
<a class="js-sku-link" href="/s/62956505/apple-iphone-17-pro-max-12-256gb-deep-blue.html">Apple iPhone 17 Pro Max 256GB</a>
<img src="https://cdn.skroutz.cy/images/phone.jpg" alt="Apple iPhone 17 Pro Max"/>
<span>από 1.299,00 €</span>
<span>σε 26 καταστήματα</span>
<span>4.8</span><span>123 αξιολογήσεις</span>
</body></html>
"""

PRODUCT_HTML = """
<html><head><title>Apple iPhone 17 Pro Max 256GB | Skroutz Cyprus</title></head>
<body>
<h1>Apple iPhone 17 Pro Max 256GB Deep Blue</h1>
<nav><a>Κινητά Τηλέφωνα</a></nav>
<script type="application/ld+json">
{"@type":"Product","name":"Apple iPhone 17 Pro Max 256GB Deep Blue","image":["https://cdn.skroutz.cy/iphone.jpg"],"aggregateRating":{"ratingValue":"4.8","reviewCount":"123"},"offers":{"price":"1299.00","priceCurrency":"EUR"}}
</script>
<section id="specifications"><dt>RAM</dt><dd>12GB</dd><dt>Storage</dt><dd>256GB</dd></section>
<p>σε 26 καταστήματα</p>
<div data-e2e="shop-offer"><a href="/shop/1">Tech Store</a><strong>1.299,00 €</strong><span>Παράδοση αύριο</span></div>
<article class="review"><strong>5</strong><h3>Excellent</h3><p>Fast and reliable.</p><span>Nikos</span><time>2026-04-20</time></article>
</body></html>
"""

CART_HTML = """
<html><body>
<div class="cart-item" data-sku-id="62956505">
  <a href="/s/62956505/apple-iphone.html">Apple iPhone 17</a>
  <input name="quantity" value="2"/>
  <span class="price">1.299,00 €</span>
  <span class="availability">Available</span>
</div>
</body></html>
"""


class ParsingTests(unittest.TestCase):
    def test_price_text_handles_split_decimal_price(self):
        price_text = _price_text("Παράδοση έως αύριο 43 09 € -10% στα 2+ προϊόντα")

        self.assertEqual(price_text, "43,09 €")
        self.assertEqual(_price_number(price_text), 43.09)

    def test_inspect_identifier_accepts_product_url_and_id(self):
        url_result = inspect_identifier("https://www.skroutz.cy/s/62956505/apple-iphone.html?from=cat")
        id_result = inspect_identifier("62956505")

        self.assertTrue(url_result["supported"])
        self.assertEqual(url_result["product_id"], "62956505")
        self.assertEqual(url_result["normalized_url"], "https://www.skroutz.cy/s/62956505/apple-iphone.html")
        self.assertTrue(id_result["supported"])
        self.assertEqual(id_result["normalized_url"], "https://www.skroutz.cy/s/62956505/product.html")

    def test_inspect_identifier_rejects_non_skroutz_urls(self):
        result = inspect_identifier("https://example.com/s/62956505/item.html")

        self.assertFalse(result["supported"])
        self.assertEqual(result["identifier_type"], "unsupported_url")

    def test_parse_search_extracts_core_fields(self):
        payload = parse_search(SEARCH_HTML, query="iphone 17", page=1)

        self.assertEqual(payload["query"], "iphone 17")
        self.assertEqual(payload["results"][0]["product_id"], "62956505")
        self.assertEqual(payload["results"][0]["title"], "Apple iPhone 17 Pro Max 256GB")
        self.assertEqual(payload["results"][0]["min_price_text"], "1.299,00 €")
        self.assertEqual(payload["results"][0]["shop_count"], 26)

    def test_parse_product_extracts_detail_offers_and_specs(self):
        payload = parse_product(PRODUCT_HTML, product_id="62956505", url="https://www.skroutz.cy/s/62956505/product.html")

        self.assertEqual(payload["product_id"], "62956505")
        self.assertEqual(payload["title"], "Apple iPhone 17 Pro Max 256GB Deep Blue")
        self.assertEqual(payload["rating"], 4.8)
        self.assertEqual(payload["review_count"], 123)
        self.assertEqual(payload["price_summary"]["min_price_text"], "1.299,00 €")
        self.assertIn({"name": "RAM", "value": "12GB"}, payload["specs"])

    def test_parse_reviews_honors_limit(self):
        reviews = parse_reviews(PRODUCT_HTML, limit=1)

        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["rating"], 5)
        self.assertEqual(reviews[0]["body"], "Fast and reliable.")

    def test_parse_cart_extracts_rows(self):
        payload = parse_cart(CART_HTML, url="https://www.skroutz.cy/cart")

        self.assertEqual(payload["item_count"], 1)
        self.assertEqual(payload["items"][0]["product_id"], "62956505")
        self.assertEqual(payload["items"][0]["quantity"], 2)
        self.assertEqual(payload["items"][0]["price_text"], "1.299,00 €")


if __name__ == "__main__":
    unittest.main()
