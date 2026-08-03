# Plan: Build `product_review_summaries` dataset from `product_data.json`

## Context

`database/product_data.json` holds 12 scraped Alibaba product records. Each record has 5 top-level sections: `product` (title, category, attributes, pricing, variants/SKUs, logistics), `seller` (company + ratings + trade assurance), `customer_reviews` (reviews tied to that exact product), `store_reviews` (reviews about the seller's storefront as a whole, sometimes numbering in the thousands), and `meta` (scrape provenance).

The user wants a new, flatter dataset — `product_review_summaries` — that is review-centric: one row per review, carrying enough product/sku/seller context on every row to analyze reviews standalone (ratings, sentiment, verified-purchase rates, etc.) without re-joining against the nested JSON.

User decisions already confirmed:
- **Merge `customer_reviews` and `store_reviews` into one combined, generic list** — treat them as the same kind of "review" (still tagged with a `review_source` column for traceability, since it's free and the two lists have slightly different meaning, but they are NOT split into separate outputs).
- **Granularity: one row per individual review**, with product/seller fields repeated on each row as context columns.

Confirmed from inspecting all 12 records:
- `customer_reviews.reviews` and `store_reviews.reviews` share the same per-review shape (reviewer_name, reviewer_country, rating, review_title, review_text, review_date, verified_purchase, repeat_buyer, helpful_votes, total_votes, price_at_review, currency, variant, images_count, review_id).
- Some review fields are frequently `null` (review_title always seen null, rating/reviewer_name null in a few placeholder store reviews) — script must tolerate missing/null values, not error.
- `product.attributes` is a flat list of `{name, value}` dicts, not fixed keys — brand/model must be looked up by name (`"Brand Name"`, `"Model Number"`) and are sometimes absent (`None`).
- `product.pricing.price_ladder` gives multiple price tiers; take min/max across the ladder's `price` field (list can be empty for 1 product with no pricing).
- `product.variants` gives one or more SKUs (`sku_id`); one is flagged `is_default`.
- Output needed in both `product_review_summaries.json` and `product_review_summaries.csv`, generated from `database/product_data.json`.

## Task 01 — Column list

Columns for `product_review_summaries` (one row per review), grouped by origin:

**Product context**
1. `product_id`
2. `product_title`
3. `product_category_leaf_id`
4. `product_category_top_id`
5. `product_category_breadcrumb` — breadcrumb names joined with ` > `
6. `product_brand` — from attributes `"Brand Name"`, else null
7. `product_model_number` — from attributes `"Model Number"`, else null
8. `product_price_currency`
9. `product_price_min`
10. `product_price_max`
11. `product_moq`
12. `product_unit`
13. `product_sales_volume_text` — e.g. `"62 sold"`

**SKU / variant context**
14. `product_sku_ids` — comma-joined list of all `sku_id`s for the product
15. `product_default_sku_id` — the `is_default` variant's sku_id

**Seller context**
16. `seller_company_id`
17. `seller_company_name`
18. `seller_business_type`
19. `seller_register_country`
20. `seller_years_on_platform`
21. `seller_average_rating` — `seller.ratings.average_star`
22. `seller_total_reviewed_orders` — `seller.ratings.total_review_order_count`
23. `seller_trade_assurance_enabled`
24. `seller_on_time_delivery_rate`

**Review details (the row itself)**
25. `review_source` — `"customer_review"` or `"store_review"`
26. `review_id`
27. `reviewer_name`
28. `reviewer_country`
29. `review_rating`
30. `review_title`
31. `review_text`
32. `review_date`
33. `review_verified_purchase`
34. `review_repeat_buyer`
35. `review_helpful_votes`
36. `review_total_votes`
37. `review_price_at_review`
38. `review_currency`
39. `review_variant` — free-text variant description attached to the review (e.g. `"Color: Red"`)
40. `review_images_count`

**Meta**
41. `data_source` — `meta.source` (e.g. `"alibaba.com"`)
42. `scraped_at`

Products with zero reviews in both lists (none currently, but future-proofing) are simply skipped — no empty placeholder row, since there's no review to describe.

## Task 02 — Python script

New file: `generate_product_review_summaries.py` (repo root, alongside `extract_to_json.py`).

Structure:
- `load_products(path) -> list[dict]`: read `database/product_data.json`.
- `extract_attr(attributes, name) -> str | None`: helper to look up a named attribute value from the `attributes` list.
- `price_bounds(pricing) -> (min, max)`: derive from `price_ladder`, handling an empty ladder.
- `build_product_context(product) -> dict`: returns columns 1–15 as a dict, reused for every review row of that product.
- `build_seller_context(seller) -> dict`: returns columns 16–24.
- `flatten_review(review, source_label) -> dict`: maps one raw review dict to columns 25–40 (`review_source` = `source_label`).
- `build_rows(data) -> list[dict]`: for each product record, build product+seller context once, then iterate `customer_reviews.reviews` (tag `"customer_review"`) and `store_reviews.reviews` (tag `"store_review"`), merging context + flattened review + meta (columns 41–42) into one flat dict per review, appended to the output list.
- `main()`: load from `database/product_data.json`, build rows, write:
  - `product_review_summaries.json` — `json.dump(rows, f, indent=2, ensure_ascii=False)`
  - `product_review_summaries.csv` — `csv.DictWriter` using the fixed column order from Task 01 (so column order is stable regardless of dict insertion order), `newline=''`, UTF-8.
- Use only Python stdlib (`json`, `csv`) — no new dependencies, consistent with the existing `extract_to_json.py` style.
- All field lookups use `.get()` with defaults so a missing/null field never raises — matches the nulls already observed in the data (e.g. `review_title`, `rating`, `reviewer_name` are `None` in several real rows).

## Task 03 — Run the script

Run `python3 generate_product_review_summaries.py` from the repo root. Expected output: `database/product_data.json` (12 products) → `product_review_summaries.json` + `product_review_summaries.csv` at repo root (paths the user already referenced), containing one row per review across both sources — expect roughly 5,000+ rows given `store_reviews.reviews` lengths seen (e.g. one product alone has 2,905 store reviews).

## Housekeeping

The user asked for this plan to be saved under `.claude/_handsOff/` in the repo. Plan mode only permits writing to this plan file itself, so on approval the first execution step will be copying this plan's final content into `.claude/_handsOff/product_review_summaries_plan.md` before starting Task 02.

## Verification

- After running, sanity-check counts: `python3 -c "import json; d=json.load(open('product_review_summaries.json')); print(len(d)); print(d[0])"` and confirm row count equals the sum of `len(customer_reviews.reviews) + len(store_reviews.reviews)` across all 12 products in the source file.
- Open `product_review_summaries.csv` header row and confirm it matches the 42-column list above, and spot-check a couple of rows (one `customer_review`, one `store_review`) for correct product/seller context join.
- Confirm no Python exceptions on missing/null fields (title, rating, brand, model all have real null cases in the source data).
