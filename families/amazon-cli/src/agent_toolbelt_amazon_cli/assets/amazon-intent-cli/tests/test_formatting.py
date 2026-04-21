from amazon_intent_cli.formatting import render_text


def test_reviews_text_renders_comments_summary() -> None:
    output = render_text(
        {
            "command": "reviews",
            "marketplace": "es",
            "pagination": {"pages_fetched": 2},
            "reviews_source": "product_reviews",
            "comments_summary": {
                "extracted_review_count": 10,
                "available_review_count": 637,
                "average_rating": 4.7,
                "verified_purchase_count": 9,
                "source_countries": {"Germany": 6, "France": 4},
                "positive_terms": [{"term": "image quality", "count": 7}],
                "critical_terms": [{"term": "remote", "count": 2}],
            },
            "reviews": [],
        }
    )

    assert "Pagination: 2 pages fetched" in output
    assert "Comments: 10 extracted of 637 available, average rating 4.7, verified purchases 9" in output
    assert "Countries: Germany=6, France=4" in output
    assert "Positive terms: image quality=7" in output
    assert "Critical terms: remote=2" in output


def test_offers_text_renders_vat_delivery_and_address_status() -> None:
    output = render_text(
        {
            "command": "offers",
            "asin": "B0DHVGHPF9",
            "include_shipping": True,
            "vat_mode": "auto",
            "address_consistency": {"status": "mismatch"},
            "trusted_best_offer": {"marketplace": "de", "comparison_total": 124.79, "currency": "EUR"},
            "raw_best_offer": {"marketplace": "fr", "comparison_total": 90.0, "currency": "EUR"},
            "current_offer": {"marketplace": "de", "status": "ok"},
            "offers": [
                {
                    "marketplace": "de",
                    "status": "ok",
                    "price": 141.44,
                    "price_ex_vat": 116.89,
                    "price_incl_vat": 141.44,
                    "shipping": 7.9,
                    "comparison_total": 124.79,
                    "comparison_basis": "ex_vat",
                    "delivery_date_text": "28 - 29 April",
                    "address_match": True,
                    "eligible_for_best": True,
                    "sold_by_amazon": False,
                }
            ],
        }
    )

    assert "Address consistency: mismatch" in output
    assert "Trusted best offer: de 124.79 EUR" in output
    assert "Raw best offer: fr 90.0 EUR" in output
    assert "VAT mode: auto" in output
    assert "ex_vat=116.89" in output
    assert "incl_vat=141.44" in output
    assert "basis=ex_vat" in output
    assert "delivery=28 - 29 April" in output
    assert "address_match=True" in output
