#!/usr/bin/env python3
"""
extract_to_json.py

Reads product folders under input_data_source/ (one product per folder: a
saved Alibaba product page .html, plus review dialog exports named
product_reviews.txt / store_reviews.txt / review_data.txt, and/or a
screenshot), and writes ONE JSON array to database/product_data.json:

    .venv/bin/python extract_to_json.py

Each array element has the shape:

    {
      "product": { product_id, title, category, images, attributes,
                    pricing, variant_options, variants, logistics },
      "seller":  { company_id, company_name, ..., contact, ratings,
                    trade_assurance, membership },
      "customer_reviews": { product_id, total_reviews, average_rating,
                             status, reviews: [...] },
      "store_reviews":    { company_id, company_name, average_star,
                             max_star, total_review_count,
                             total_reviewed_orders, rating_breakdown,
                             reviews: [...] },
      "meta": { source, viewer_shipping_country, source_folder, scraped_at }
    }

Where the data comes from:
  - product/seller fields: the `window.detailData = {...}` JSON blob that
    Alibaba embeds in the saved product page (globalData.product /
    globalData.seller / globalData.trade / globalData.inventory /
    globalData.seo.breadCrumb).
  - review lists: the exported "reviews dialog" HTML fragments
    (product_reviews.txt / store_reviews.txt / review_data.txt). The dialog
    is classified as customer or store reviews from its own heading text
    ("Product reviews (N)" / "Store reviews (N)"), not the filename, since a
    generically-named review_data.txt may hold either.
  - a folder with no review .txt files but a screenshot: OCR'd (if
    pytesseract + tesseract-ocr are installed) and treated as customer
    reviews; otherwise that folder contributes no reviews.

One folder = one product. Folders whose name starts with "_" (e.g.
_demo_example_folder) are skipped. Fields the source doesn't have are left
null/empty rather than guessed.

Requires: beautifulsoup4, pillow
Optional: pytesseract + the tesseract-ocr system binary (enables OCR)
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from PIL import Image

try:
    import pytesseract
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

HTML_EXTS = {".html", ".htm"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
REVIEW_TXT_NAMES = {"product_reviews.txt", "customer_reviews.txt", "store_reviews.txt", "review_data.txt"}

MONTH_DATE_RE = re.compile(
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})"
)
HELPFUL_TAIL_RE = re.compile(r"^Helpful \((\d+)\)$")
VARIANT_LABEL_RE = re.compile(r"^.+[:：]$")


def raw_date(text):
    """Return a date in the source's own 'Mon DD, YYYY' form, or None."""
    m = MONTH_DATE_RE.search(text)
    if not m:
        return None
    month, day, year = m.groups()
    return f"{month[:3]} {int(day)}, {year}"


def to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def to_float(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


# ---------- window.detailData extraction ----------

def extract_detail_data(html):
    """Pull the `window.detailData = {...};` JSON blob out of a saved
    Alibaba product page and parse it. Returns {} if not found/parseable."""
    marker = "window.detailData = "
    start = html.find(marker)
    if start == -1:
        return {}
    start += len(marker)
    depth = 0
    end = None
    for i in range(start, len(html)):
        c = html[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        return {}
    try:
        return json.loads(html[start:end])
    except json.JSONDecodeError:
        return {}


def build_category(g):
    product = g.get("product", {})
    breadcrumb = []
    for item in g.get("seo", {}).get("breadCrumb", {}).get("pathList", []):
        href = item.get("hrefObject", {})
        if href.get("name"):
            breadcrumb.append({"name": href.get("name"), "url": href.get("url")})
    return {
        "leaf_category_id": product.get("productLeafId"),
        "top_category_id": product.get("firstLevelCateId"),
        "breadcrumb": breadcrumb,
    }


def build_images(g):
    images = []
    for item in g.get("product", {}).get("mediaItems", []):
        url = item.get("imageUrl") or {}
        if not url:
            continue
        images.append({
            "large": url.get("big"),
            "medium": url.get("normal"),
            "small": url.get("small"),
            "thumb": url.get("thumb"),
        })
    return images


def build_attributes(g):
    product = g.get("product", {})
    key_ids = {a.get("attrNameId") for a in product.get("productKeyIndustryProperties", [])}
    attributes = []
    for attr in product.get("productBasicProperties", []):
        attributes.append({
            "name": attr.get("attrName"),
            "value": attr.get("attrValue"),
            "attr_name_id": attr.get("attrNameId"),
            "attr_value_id": attr.get("attrValueId"),
            "is_key_attribute": attr.get("attrNameId") in key_ids,
        })
    return attributes


def build_pricing(g):
    price = g.get("product", {}).get("price", {}) or {}
    currency_rule = price.get("currencyRule", {}) or {}
    ladder = []
    for tier in price.get("productLadderPrices", []):
        max_qty = tier.get("max")
        ladder.append({
            "min_qty": tier.get("min"),
            "max_qty": max_qty if max_qty is not None and max_qty >= 0 else None,
            "price": tier.get("price"),
            "price_usd": tier.get("dollarPrice"),
            "formatted_price": tier.get("formatPrice") or None,
        })
    currency_displayed = None
    formatted = price.get("formatLadderPrice") or ""
    m = re.match(r"^([A-Za-z]{2,4})\s", formatted)
    if m:
        currency_displayed = m.group(1)
    return {
        "currency_displayed": currency_displayed,
        "currency_source": "USD",
        "fx_rate_usd_to_displayed": to_float(currency_rule.get("rate")),
        "unit": price.get("unit"),
        "moq": g.get("product", {}).get("moq"),
        "price_ladder": ladder,
        "formatted_ladder_price": formatted or None,
    }


def build_variant_options(g):
    options = []
    for attr in g.get("product", {}).get("sku", {}).get("skuAttrs", []):
        values = []
        for v in attr.get("values", []):
            values.append({
                "value_id": v.get("id"),
                "name": v.get("name"),
                "image": v.get("largeImage"),
            })
        options.append({
            "attr_name_id": attr.get("id"),
            "attr_name": attr.get("name"),
            "type": attr.get("type"),
            "values": values,
        })
    return options


def build_variants(g):
    product = g.get("product", {})
    sku = product.get("sku", {})
    first_sku_id = sku.get("firstSkuId")

    attr_by_id = {a.get("id"): a for a in sku.get("skuAttrs", [])}
    sku_inventory = g.get("inventory", {}).get("skuInventory", {})

    variants = []
    for combo_key, entry in sku.get("skuInfoMap", {}).items():
        sku_id = entry.get("id")
        options = []
        for pair in combo_key.split(";"):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            attr_id_s, value_id_s = pair.split(":", 1)
            attr_id, value_id = to_int(attr_id_s), to_int(value_id_s)
            attr = attr_by_id.get(attr_id, {})
            value = next((v for v in attr.get("values", []) if v.get("id") == value_id), {})
            options.append({
                "attr_name": attr.get("name"),
                "attr_name_id": attr_id,
                "value_id": value_id,
                "value_name": value.get("name"),
                "image": value.get("largeImage"),
            })

        inventory = []
        for wh in sku_inventory.get(str(sku_id), {}).get("warehouseInventoryList", []):
            inventory.append({
                "warehouse_id": wh.get("id"),
                "quantity_available": wh.get("inventoryCount"),
                "place_of_dispatch": wh.get("placeOfDispatchId"),
                "store_code": wh.get("storeCode"),
                "store_type": wh.get("storeType"),
            })

        variants.append({
            "sku_id": sku_id,
            "is_default": sku_id == first_sku_id,
            "options": options,
            "inventory": inventory,
        })
    return variants


def build_logistics(g):
    trade = g.get("trade", {}) or {}
    inventory = g.get("inventory", {}) or {}
    logistic_info = trade.get("logisticInfo", {}) or {}
    lead_time = []
    for tier in trade.get("leadTimeInfo", {}).get("ladderPeriodList", []):
        lead_time.append({
            "min_qty": tier.get("minQuantity"),
            "max_qty": tier.get("maxQuantity"),
            "process_days": tier.get("processPeriod"),
        })
    return {
        "ships_from": inventory.get("placeOfDispatches", []),
        "ships_to_country": inventory.get("shippingToCountry"),
        "unit_weight_kg": logistic_info.get("unitWeight"),
        "unit_size_cm": logistic_info.get("unitSize"),
        "lead_time": lead_time,
        "trade_price_type": trade.get("tradeInfo", {}).get("tradePriceType"),
        "sales_volume_text": trade.get("salesVolume"),
    }


def build_product(g):
    product = g.get("product", {}) or {}
    return {
        "product_id": product.get("productId"),
        "title": product.get("subject"),
        "category": build_category(g),
        "images": build_images(g),
        "attributes": build_attributes(g),
        "pricing": build_pricing(g),
        "variant_options": build_variant_options(g),
        "variants": build_variants(g),
        "logistics": build_logistics(g),
    }


def build_rating_breakdown(seller):
    breakdown = []
    for latitude in seller.get("supplierRatingReviews", {}).get("latitudeScoreDTOList", []):
        distribution = [
            {
                "star": s.get("scatterValue"),
                "count": s.get("scatterCount"),
                "percentage": s.get("scatterPercentage"),
            }
            for s in latitude.get("scoreScatterDTOList", [])
        ]
        breakdown.append({
            "category": latitude.get("latitudeType"),
            "average_score": latitude.get("latitudeAverageScore"),
            "star_distribution": distribution,
        })
    return breakdown


def build_seller(g):
    seller = g.get("seller", {}) or {}
    trade = g.get("trade", {}) or {}
    ratings = seller.get("supplierRatingReviews", {}) or {}
    return {
        "company_id": seller.get("companyId"),
        "company_name": seller.get("companyName"),
        "business_type": seller.get("companyBusinessType"),
        "register_country": seller.get("companyRegisterCountry"),
        "years_on_platform": seller.get("companyJoinYears"),
        "employees_count": seller.get("employeesCount"),
        "self_operated": bool(seller.get("sellerSelfOperated")),
        "profile_url": seller.get("companyProfileUrl"),
        "home_url": seller.get("homeUrl"),
        "logo": seller.get("companyLogoFileUrlSmall"),
        "contact": {
            "name": seller.get("contactName"),
            "first_name": seller.get("accountFirstName"),
            "last_name": seller.get("accountLastName"),
            "job_title": seller.get("jobTitle"),
            "gender": seller.get("accountGender"),
            "portrait": (seller.get("accountPortraitImage") or {}).get("original"),
            "response_time": seller.get("responseTimeText"),
        },
        "ratings": {
            "average_star": ratings.get("averageStar"),
            "max_star": ratings.get("maxStar"),
            "total_review_order_count": ratings.get("totalReviewOrderCount"),
            "by_category": [
                {"category": lat.get("latitudeType"), "average_score": lat.get("latitudeAverageScore")}
                for lat in ratings.get("latitudeScoreDTOList", [])
            ],
        },
        "trade_assurance": {
            "enabled": bool(trade.get("globalTradeAssuranceForBuyer")),
            "on_time_delivery_rate": seller.get("supplierOnTimeDeliveryRate"),
            "trade_last_6_months": {
                "ordAmt": seller.get("tradeHalfYear", {}).get("ordAmt"),
                "ordAmt6m": seller.get("tradeHalfYear", {}).get("ordAmt6m"),
                "ordCnt6m": seller.get("tradeHalfYear", {}).get("ordCnt6m"),
            },
        },
        "membership": {
            "is_gold_supplier": bool(seller.get("accountIsGoldPlusSupplier")),
            "is_paid_member": bool(seller.get("accountIsPaidMember")),
            "is_leader_supplier": bool(seller.get("accountIsLeaderSupplier")),
        },
    }


# ---------- review dialog parsing (product_reviews.txt / store_reviews.txt / review_data.txt) ----------

HEADER_RE = re.compile(r"(Product|Store) reviews \((\d+)\)", re.IGNORECASE)


def parse_review_card(card):
    """Parse one review card (a dialog's per-review div) into a row dict, or
    None if the card doesn't look like a real review."""
    segs = card.get_text(separator="|", strip=True).split("|")

    helpful = None
    if segs and HELPFUL_TAIL_RE.match(segs[-1]):
        helpful = int(HELPFUL_TAIL_RE.match(segs[-1]).group(1))
        segs = segs[:-1]

    price = currency = None
    if len(segs) >= 2 and segs[-2] == "See product details":
        price_raw = segs[-1]
        segs = segs[:-2]
        pm = re.match(r"^([A-Za-z]{2,4})\s+(.+)$", price_raw)
        if pm:
            currency, price = pm.group(1), pm.group(2)
        else:
            price = price_raw or None

    if len(segs) < 3:
        return None

    name = segs[1].strip() or None
    idx = 2
    country = None
    if idx < len(segs) and segs[idx] not in ("Verified purchase", "Repeat buyer") and not MONTH_DATE_RE.search(segs[idx]):
        country = segs[idx].strip() or None
        idx += 1

    verified = repeat = False
    while idx < len(segs) and segs[idx] in ("Verified purchase", "Repeat buyer"):
        if segs[idx] == "Verified purchase":
            verified = True
        else:
            repeat = True
        idx += 1

    date = None
    if idx < len(segs) and MONTH_DATE_RE.search(segs[idx]):
        date = raw_date(segs[idx])
        idx += 1

    variants = []
    while idx + 1 < len(segs) and VARIANT_LABEL_RE.match(segs[idx].strip()):
        label = segs[idx].strip().rstrip(":：").strip()
        value = segs[idx + 1].strip()
        variants.append(f"{label}: {value}")
        idx += 2

    text = "|".join(segs[idx:]).strip()[:1000] or None
    star_count = str(card).count("icon-rating-star-fill")
    images_count = len(card.find_all("img")) or None

    return {
        "reviewer_name": name,
        "reviewer_country": country,
        "rating": star_count or None,
        "review_title": None,
        "review_text": text,
        "review_date": date,
        "verified_purchase": verified,
        "repeat_buyer": repeat,
        "helpful_votes": helpful if helpful is not None else 0,
        "total_votes": None,
        "price_at_review": price,
        "currency": currency,
        "variant": "; ".join(variants) or None,
        "images_count": images_count,
    }


def parse_review_dialog(html):
    """Parse a saved 'reviews dialog' export. Returns
    (kind, header_total, rows) where kind is 'customer', 'store' or None,
    header_total is the count shown in the dialog heading (may exceed
    len(rows) since the export can be a partial/scrolled snapshot)."""
    if not html.strip():
        return None, None, []

    soup = BeautifulSoup(html, "html.parser")
    h2 = soup.find("h2")
    header_text = h2.get_text(strip=True) if h2 else ""
    m = HEADER_RE.search(header_text)
    kind = None
    header_total = None
    if m:
        kind = "customer" if m.group(1).lower() == "product" else "store"
        header_total = int(m.group(2))

    cards = soup.find_all("div", class_=lambda c: c and "r-border-b-solid" in c and "r-pt-[20px]" in c)
    rows = [row for card in cards if (row := parse_review_card(card))]
    return kind, header_total, rows


def parse_ocr_reviews(ocr_text):
    lines = [l.strip() for l in ocr_text.splitlines() if l.strip()]
    boundaries = [i for i, line in enumerate(lines) if MONTH_DATE_RE.search(line)]
    rows = []
    for idx, start in enumerate(boundaries):
        end = boundaries[idx + 1] if idx + 1 < len(boundaries) else len(lines)
        block = lines[start + 1:end]

        helpful_votes = None
        text_lines = []
        for line in block:
            hm = re.search(r"Helpful\s*\(?\s*(\d+)\s*\)?", line, re.IGNORECASE)
            if hm:
                helpful_votes = int(hm.group(1))
                break
            text_lines.append(line)

        rows.append({
            "reviewer_name": None,
            "reviewer_country": None,
            "rating": None,
            "review_title": None,
            "review_text": " ".join(text_lines).strip()[:1000] or None,
            "review_date": raw_date(lines[start]),
            "verified_purchase": any(re.search(r"Verified\s+purchase", l, re.IGNORECASE) for l in block),
            "repeat_buyer": False,
            "helpful_votes": helpful_votes if helpful_votes is not None else 0,
            "total_votes": None,
            "price_at_review": None,
            "currency": None,
            "variant": None,
            "images_count": None,
        })
    kind = "store" if re.search(r"Store reviews", ocr_text, re.IGNORECASE) else "customer"
    return kind, rows


def serialize_reviews(rows):
    reviews = []
    for i, row in enumerate(rows, start=1):
        review = dict(row)
        review["review_id"] = f"REV-{i:03d}"
        reviews.append(review)
    return reviews


def build_reviews_block(rows, header_total, extra=None):
    reviews = serialize_reviews(rows)
    ratings = [r["rating"] for r in reviews if r["rating"]]
    average_rating = round(sum(ratings) / len(ratings), 1) if ratings else None
    total = header_total if header_total is not None else len(reviews)
    block = {
        "total_reviews": total,
        "average_rating": average_rating,
        "status": "No reviews yet" if total == 0 else None,
        "reviews": reviews,
    }
    if extra:
        block.update(extra)
    return block


# ---------- per-folder driver ----------

def find_product_html(folder):
    for f in sorted(folder.glob("*.html")) + sorted(folder.glob("*.htm")):
        return f
    return None


def process_product_folder(folder):
    html_path = find_product_html(folder)
    g = {}
    if html_path:
        html = html_path.read_text(encoding="utf-8", errors="replace")
        detail_data = extract_detail_data(html)
        g = detail_data.get("globalData", {}) or {}

    customer_rows, customer_header = [], None
    store_rows, store_header = [], None

    for name in REVIEW_TXT_NAMES:
        path = folder / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        kind, header_total, rows = parse_review_dialog(text)
        if kind is None:
            kind = "customer" if name in ("product_reviews.txt", "customer_reviews.txt") else "store"
        if kind == "customer":
            customer_rows, customer_header = rows, header_total
        else:
            store_rows, store_header = rows, header_total

    if not customer_rows and not store_rows:
        for img_path in sorted(folder.glob("*.png")) + sorted(folder.glob("*.jpg")) + sorted(folder.glob("*.jpeg")):
            if not HAS_OCR:
                print(f"warning: pytesseract not installed, no text extracted from {img_path}", file=sys.stderr)
                continue
            with Image.open(img_path) as img:
                ocr_text = pytesseract.image_to_string(img)
            kind, rows = parse_ocr_reviews(ocr_text)
            if kind == "store":
                store_rows = rows
            else:
                customer_rows = rows
            break

    product = build_product(g)
    seller = build_seller(g)

    customer_reviews = build_reviews_block(
        customer_rows, customer_header, extra={"product_id": product["product_id"]}
    )

    store_summary = g.get("review", {}).get("storeReview", {}) or {}
    ratings = g.get("seller", {}).get("supplierRatingReviews", {}) or {}
    store_reviews = build_reviews_block(
        store_rows, store_header if store_header is not None else store_summary.get("totalReviewCount"),
        extra={
            "company_id": seller["company_id"],
            "company_name": seller["company_name"],
            "average_star": store_summary.get("averageStar", ratings.get("averageStar")),
            "max_star": ratings.get("maxStar"),
            "total_reviewed_orders": ratings.get("totalReviewOrderCount"),
            "rating_breakdown": build_rating_breakdown(g.get("seller", {}) or {}),
        },
    )
    # keep field order close to the reference schema: summary fields first, reviews last
    store_reviews = {
        "company_id": store_reviews["company_id"],
        "company_name": store_reviews["company_name"],
        "average_star": store_reviews["average_star"],
        "max_star": store_reviews["max_star"],
        "total_review_count": store_reviews["total_reviews"],
        "total_reviewed_orders": store_reviews["total_reviewed_orders"],
        "rating_breakdown": store_reviews["rating_breakdown"],
        "reviews": store_reviews["reviews"],
    }

    return {
        "product": product,
        "seller": seller,
        "customer_reviews": customer_reviews,
        "store_reviews": store_reviews,
        "meta": {
            "source": "alibaba.com",
            "viewer_shipping_country": g.get("global", {}).get("visitCountry"),
            "source_folder": folder.name,
        },
    }


def collect_product_folders(root):
    return sorted(
        p for p in root.iterdir()
        if p.is_dir() and not p.name.startswith("_")
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", nargs="?", default="input_data_source",
                        help="directory containing one subfolder per product (default: input_data_source/)")
    parser.add_argument("-o", "--output", default="database/product_data.json",
                        help="output JSON file path (default: database/product_data.json)")
    args = parser.parse_args()

    root = Path(args.input)
    if not root.is_dir():
        print(f"error: input directory not found: {root}", file=sys.stderr)
        sys.exit(1)

    folders = collect_product_folders(root)
    if not folders:
        print(f"no product folders found under {root}", file=sys.stderr)
        sys.exit(1)

    scraped_at = datetime.now().astimezone().isoformat(timespec="seconds")

    products = []
    for folder in folders:
        try:
            entry = process_product_folder(folder)
        except Exception as exc:
            print(f"warning: failed to process {folder}: {exc}", file=sys.stderr)
            continue
        entry["meta"]["scraped_at"] = scraped_at
        products.append(entry)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(products, indent=2, ensure_ascii=False), encoding="utf-8")

    total_customer = sum(p["customer_reviews"]["total_reviews"] for p in products)
    total_store = sum(p["store_reviews"]["total_review_count"] for p in products)
    print(
        f"wrote {len(products)} product(s), {total_customer} customer review(s), "
        f"{total_store} store review(s) -> {args.output}"
    )


if __name__ == "__main__":
    main()
