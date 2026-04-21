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
