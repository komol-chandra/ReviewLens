# ReviewLens

English | [বাংলা](README.bn.md)

Turn saved Alibaba product pages and their review dialogs into one structured
JSON dataset, then browse it in a self-contained HTML dashboard.

Drop a product's saved page (+ review exports / screenshot) into
`input_data_source/`, run the extractor, and get `database/product_data.json`
— an array of product records, each with its listing data, seller/company
info, and both customer and store reviews.

---

## Layout

```
input_data_source/       raw inputs, one product per folder
  <product folder>/
    <page>.html           saved Alibaba product page (window.detailData blob)
    product_reviews.txt    exported "Product reviews" dialog (optional)
    store_reviews.txt      exported "Store reviews" dialog (optional)
    review_data.txt        generic review dialog export, classified by its
                            own heading text (optional)
    *.png / *.jpg          screenshot, OCR'd as customer reviews if no
                            review .txt files are present (optional)
  _demo_example_folder/    folders prefixed "_" are skipped
database/
  product_data.json      the tool writes here (default output)
note/
  category_assignments.json   team member -> product category assignments
dashboard.html            self-contained dashboard (data embedded inline)
dashboard.png             dashboard screenshot
extract_to_json.py        the extractor (this tool)
```

**One product per folder.** Everything that belongs to the same product (the
page, its review dialogs, a screenshot) must sit in the same folder; different
products go in different folders.

---

## Collecting the input data (manual workflow)

Data isn't scraped automatically — each product folder is assembled by hand
from the browser, then handed to the extractor:

1. **Open the product details page** on Alibaba.com in your browser.
2. **Save the page HTML.** `Ctrl+S` (or Cmd+S) → "Webpage, HTML only" → save
   it into a new folder under `input_data_source/` (one folder per product,
   e.g. `input_data_source/Custom-for-Toyota-Honda_1601825563615/`).
3. **Open the reviews section** on the page (Product reviews and, separately,
   Store reviews) and let it load all reviews (scroll / click "load more"
   until the full list is showing).
4. **Grab the review list via DevTools.** Open the browser's inspector
   ("Inspect" → Elements/Network), locate the review list markup (or the
   underlying API response), copy it, and paste it into a plain `.txt` file.
5. **Save that file into the same product folder**, named
   `product_reviews.txt` or `store_reviews.txt` (or `review_data.txt` if it's
   a generic export — the extractor classifies it from the dialog's own
   heading text, e.g. "Product reviews (N)" / "Store reviews (N)"). If DevTools
   only gives you a screenshot, save that image into the folder instead — it
   gets OCR'd as customer reviews.
6. Repeat for every product, keeping the **one-folder-per-product** rule —
   don't mix files from two different products in the same folder.
7. **Run the extractor** (see below) once all folders are ready; it reads
   every folder under `input_data_source/` and writes the combined result to
   `database/product_data.json`.

---

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# Optional OCR of screenshots (Debian/Ubuntu):
sudo apt install tesseract-ocr
```

---

## Run the extractor

Defaults read `input_data_source/` and write `database/product_data.json`:

```bash
.venv/bin/python extract_to_json.py
```

Custom input/output:

```bash
.venv/bin/python extract_to_json.py input_data_source/some_folder -o database/product_data.json
```

- Reads the `window.detailData` JSON blob embedded in the saved product page
  for product, seller, trade, inventory, and breadcrumb-category fields.
- Reads `product_reviews.txt` / `store_reviews.txt` / `review_data.txt`
  review-dialog exports; a dialog is classified as customer or store reviews
  from its own heading text ("Product reviews (N)" / "Store reviews (N)"),
  not its filename.
- A folder with a screenshot but no review `.txt` files is OCR'd (needs
  `pytesseract` + the `tesseract-ocr` system binary) and treated as customer
  reviews; without OCR available it contributes no reviews.
- Fields the source doesn't have are left `null`/empty rather than guessed.
- Prints e.g. `wrote 7 product(s), 42 customer review(s), 15 store review(s) -> database/product_data.json`.

---

## Output schema

`database/product_data.json` is a JSON array; each element has:

```jsonc
{
  "product": {
    // product_id, title, category (leaf/top id + breadcrumb), images,
    // attributes, pricing, variant_options, variants, logistics
  },
  "seller": {
    // company_id, company_name, business_type, register_country,
    // years_on_platform, employees_count, self_operated, profile_url,
    // home_url, logo, contact, ratings, trade_assurance, membership
  },
  "customer_reviews": {
    "product_id": 1601617520356,
    "total_reviews": 25,
    "average_rating": 4.8,
    "status": "...",
    "reviews": [ /* see review shape below */ ]
  },
  "store_reviews": {
    "company_id": "...",
    "company_name": "...",
    "average_star": 4.9,
    "max_star": 5,
    "total_review_count": 120,
    "total_reviewed_orders": 340,
    "rating_breakdown": { /* star -> count */ },
    "reviews": [ /* see review shape below */ ]
  },
  "meta": {
    "source": "alibaba.com",
    "viewer_shipping_country": "US",
    "source_folder": "<input folder name>",
    "scraped_at": "2026-07-25T04:12:57+06:00"  // ISO-8601 + offset
  }
}
```

Each review object (customer or store) has: `review_id`, `reviewer_name`,
`reviewer_country`, `rating`, `review_title`, `review_text`, `review_date`
(source's own "Mon DD, YYYY" form), `verified_purchase`, `repeat_buyer`,
`helpful_votes`, `total_votes`, `price_at_review`, `currency`, `variant`,
`images_count`.

---

## Dashboard

`dashboard.html` is self-contained — the product data is embedded directly in
the file (no server, no fetch), so just open it in a browser:

```bash
xdg-open dashboard.html   # or double-click it
```

It shows per-product review/rating charts, category and seller-country chips,
and a searchable, sortable product table (title, category, seller, country,
membership type, price, MOQ, rating, review count). Re-run
`extract_to_json.py` and re-embed the new `database/product_data.json` into
the `<script type="application/json" id="productData">` block to refresh it.
`dashboard.png` is a screenshot of the rendered dashboard.

---

## Other files

- `note/category_assignments.json` — which team member is reviewing/assigned
  to which product categories; not consumed by the tooling, kept for
  team reference.
