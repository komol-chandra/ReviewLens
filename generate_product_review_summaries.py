#!/usr/bin/env python3
"""
generate_product_review_summaries.py

Reads database/product_data.json (product + seller + customer_reviews +
store_reviews per product) and flattens it into a review-level dataset:
one row per review, with product/sku/seller context repeated on every row.

customer_reviews (tied to the exact product) and store_reviews (about the
seller's storefront as a whole) are merged into a single list, tagged via
review_source so the origin stays traceable.

Writes product_review_summaries.json and product_review_summaries.csv to
the repo root:

    python3 generate_product_review_summaries.py
"""

import csv
import json
from pathlib import Path

INPUT_PATH = Path(__file__).parent / "database" / "product_data.json"
JSON_OUTPUT_PATH = Path(__file__).parent / "product_review_summaries.json"
CSV_OUTPUT_PATH = Path(__file__).parent / "product_review_summaries.csv"

COLUMNS = [
    # product context
    "product_id",
    "product_title",
    "product_category_leaf_id",
    "product_category_top_id",
    "product_category_breadcrumb",
    "product_brand",
    "product_model_number",
    "product_price_currency",
    "product_price_min",
    "product_price_max",
    "product_moq",
    "product_unit",
    "product_sales_volume_text",
    # sku / variant context
    "product_sku_ids",
    "product_default_sku_id",
    # seller context
    "seller_company_id",
    "seller_company_name",
    "seller_business_type",
    "seller_register_country",
    "seller_years_on_platform",
    "seller_average_rating",
    "seller_total_reviewed_orders",
    "seller_trade_assurance_enabled",
    "seller_on_time_delivery_rate",
    # review details
    "review_source",
    "review_id",
    "reviewer_name",
    "reviewer_country",
    "review_rating",
    "review_title",
    "review_text",
    "review_date",
    "review_verified_purchase",
    "review_repeat_buyer",
    "review_helpful_votes",
    "review_total_votes",
    "review_price_at_review",
    "review_currency",
    "review_variant",
    "review_images_count",
    # meta
    "data_source",
    "scraped_at",
]


def load_products(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def extract_attr(attributes, name):
    for attr in attributes or []:
        if attr.get("name") == name:
            return attr.get("value")
    return None


def price_bounds(pricing):
    ladder = (pricing or {}).get("price_ladder") or []
    prices = [tier.get("price") for tier in ladder if tier.get("price") is not None]
    if not prices:
        return None, None
    return min(prices), max(prices)


def build_product_context(product):
    attributes = product.get("attributes") or []
    category = product.get("category") or {}
    breadcrumb = category.get("breadcrumb") or []
    pricing = product.get("pricing") or {}
    price_min, price_max = price_bounds(pricing)
    logistics = product.get("logistics") or {}
    variants = product.get("variants") or []
    default_variant = next((v for v in variants if v.get("is_default")), None)

    return {
        "product_id": product.get("product_id"),
        "product_title": product.get("title"),
        "product_category_leaf_id": category.get("leaf_category_id"),
        "product_category_top_id": category.get("top_category_id"),
        "product_category_breadcrumb": " > ".join(
            b.get("name", "") for b in breadcrumb
        ),
        "product_brand": extract_attr(attributes, "Brand Name"),
        "product_model_number": extract_attr(attributes, "Model Number"),
        "product_price_currency": pricing.get("currency_displayed"),
        "product_price_min": price_min,
        "product_price_max": price_max,
        "product_moq": pricing.get("moq"),
        "product_unit": pricing.get("unit"),
        "product_sales_volume_text": logistics.get("sales_volume_text"),
        "product_sku_ids": ",".join(
            str(v.get("sku_id")) for v in variants if v.get("sku_id") is not None
        ),
        "product_default_sku_id": (default_variant or {}).get("sku_id"),
    }


def build_seller_context(seller):
    seller = seller or {}
    ratings = seller.get("ratings") or {}
    trade_assurance = seller.get("trade_assurance") or {}

    return {
        "seller_company_id": seller.get("company_id"),
        "seller_company_name": seller.get("company_name"),
        "seller_business_type": seller.get("business_type"),
        "seller_register_country": seller.get("register_country"),
        "seller_years_on_platform": seller.get("years_on_platform"),
        "seller_average_rating": ratings.get("average_star"),
        "seller_total_reviewed_orders": ratings.get("total_review_order_count"),
        "seller_trade_assurance_enabled": trade_assurance.get("enabled"),
        "seller_on_time_delivery_rate": trade_assurance.get("on_time_delivery_rate"),
    }


def flatten_review(review, source_label):
    review = review or {}
    return {
        "review_source": source_label,
        "review_id": review.get("review_id"),
        "reviewer_name": review.get("reviewer_name"),
        "reviewer_country": review.get("reviewer_country"),
        "review_rating": review.get("rating"),
        "review_title": review.get("review_title"),
        "review_text": review.get("review_text"),
        "review_date": review.get("review_date"),
        "review_verified_purchase": review.get("verified_purchase"),
        "review_repeat_buyer": review.get("repeat_buyer"),
        "review_helpful_votes": review.get("helpful_votes"),
        "review_total_votes": review.get("total_votes"),
        "review_price_at_review": review.get("price_at_review"),
        "review_currency": review.get("currency"),
        "review_variant": review.get("variant"),
        "review_images_count": review.get("images_count"),
    }


def build_rows(data):
    rows = []
    for record in data:
        product_context = build_product_context(record.get("product") or {})
        seller_context = build_seller_context(record.get("seller"))
        meta = record.get("meta") or {}
        meta_context = {
            "data_source": meta.get("source"),
            "scraped_at": meta.get("scraped_at"),
        }

        customer_reviews = (record.get("customer_reviews") or {}).get("reviews") or []
        store_reviews = (record.get("store_reviews") or {}).get("reviews") or []

        for review in customer_reviews:
            rows.append(
                {
                    **product_context,
                    **seller_context,
                    **flatten_review(review, "customer_review"),
                    **meta_context,
                }
            )

        for review in store_reviews:
            rows.append(
                {
                    **product_context,
                    **seller_context,
                    **flatten_review(review, "store_review"),
                    **meta_context,
                }
            )

    return rows


def write_json(rows, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)


def write_csv(rows, path):
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    data = load_products(INPUT_PATH)
    rows = build_rows(data)
    write_json(rows, JSON_OUTPUT_PATH)
    write_csv(rows, CSV_OUTPUT_PATH)
    print(f"Wrote {len(rows)} review rows from {len(data)} products")
    print(f"  {JSON_OUTPUT_PATH}")
    print(f"  {CSV_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
