# ReviewLens

[English](README.md) | বাংলা

সংরক্ষিত Alibaba প্রোডাক্ট পেজ এবং তাদের রিভিউ ডায়ালগগুলোকে একটি সুসংগঠিত
JSON ডেটাসেটে রূপান্তর করুন, তারপর সেটা একটি self-contained HTML ড্যাশবোর্ডে
ব্রাউজ করুন।

একটি প্রোডাক্টের সংরক্ষিত পেজ (+ রিভিউ এক্সপোর্ট / স্ক্রিনশট)
`input_data_source/` ফোল্ডারে রাখুন, extractor চালান, এবং পেয়ে যান
`database/product_data.json` — প্রোডাক্ট রেকর্ডের একটি অ্যারে, যেখানে প্রতিটি
রেকর্ডে থাকে তার লিস্টিং ডেটা, সেলার/কোম্পানি তথ্য, এবং কাস্টমার ও স্টোর উভয়
রিভিউ।

---

## গঠন (Layout)

```
input_data_source/       কাঁচা ইনপুট, প্রতি প্রোডাক্টের জন্য একটি ফোল্ডার
  <product folder>/
    <page>.html           সংরক্ষিত Alibaba প্রোডাক্ট পেজ (window.detailData blob)
    product_reviews.txt    এক্সপোর্ট করা "Product reviews" ডায়ালগ (ঐচ্ছিক)
    store_reviews.txt      এক্সপোর্ট করা "Store reviews" ডায়ালগ (ঐচ্ছিক)
    review_data.txt        সাধারণ রিভিউ ডায়ালগ এক্সপোর্ট, নিজের হেডিং টেক্সট
                            অনুযায়ী শ্রেণীবদ্ধ (ঐচ্ছিক)
    *.png / *.jpg          স্ক্রিনশট, যদি কোনো রিভিউ .txt ফাইল না থাকে তবে
                            OCR করে কাস্টমার রিভিউ হিসেবে গণ্য হয় (ঐচ্ছিক)
  _demo_example_folder/    "_" দিয়ে শুরু হওয়া ফোল্ডারগুলো এড়িয়ে যাওয়া হয়
database/
  product_data.json      টুলটি এখানে লেখে (ডিফল্ট আউটপুট)
note/
  category_assignments.json   টিম মেম্বার -> প্রোডাক্ট ক্যাটাগরি অ্যাসাইনমেন্ট
dashboard.html            self-contained ড্যাশবোর্ড (ডেটা inline embedded)
dashboard.png             ড্যাশবোর্ডের স্ক্রিনশট
extract_to_json.py        extractor (এই টুল)
```

**প্রতি প্রোডাক্টের জন্য একটি ফোল্ডার।** একই প্রোডাক্টের সাথে সম্পর্কিত সবকিছু
(পেজ, তার রিভিউ ডায়ালগ, স্ক্রিনশট) অবশ্যই একই ফোল্ডারে থাকতে হবে; ভিন্ন ভিন্ন
প্রোডাক্ট ভিন্ন ভিন্ন ফোল্ডারে রাখতে হবে।

---

## ইনপুট ডেটা সংগ্রহ (ম্যানুয়াল ওয়ার্কফ্লো)

ডেটা স্বয়ংক্রিয়ভাবে স্ক্র্যাপ করা হয় না — প্রতিটি প্রোডাক্ট ফোল্ডার হাতে
ব্রাউজার থেকে তৈরি করে extractor-কে দেওয়া হয়:

1. **Alibaba.com-এ প্রোডাক্ট ডিটেইলস পেজ খুলুন** আপনার ব্রাউজারে।
2. **পেজ HTML সংরক্ষণ করুন।** `Ctrl+S` (বা Cmd+S) → "Webpage, HTML only" →
   `input_data_source/`-এর অধীনে একটি নতুন ফোল্ডারে সংরক্ষণ করুন (প্রতি
   প্রোডাক্টের জন্য একটি ফোল্ডার, যেমন
   `input_data_source/Custom-for-Toyota-Honda_1601825563615/`)।
3. **পেজে রিভিউ সেকশন খুলুন** (Product reviews এবং আলাদাভাবে Store reviews)
   এবং সম্পূর্ণ লিস্ট দেখানো পর্যন্ত সব রিভিউ লোড হতে দিন (স্ক্রল করুন /
   "load more"-এ ক্লিক করুন)।
4. **DevTools দিয়ে রিভিউ লিস্ট সংগ্রহ করুন।** ব্রাউজারের ইন্সপেক্টর খুলুন
   ("Inspect" → Elements/Network), রিভিউ লিস্টের markup (বা সংশ্লিষ্ট API
   response) খুঁজে বের করুন, কপি করুন, এবং একটি প্লেইন `.txt` ফাইলে পেস্ট
   করুন।
5. **সেই ফাইলটি একই প্রোডাক্ট ফোল্ডারে সংরক্ষণ করুন**, নাম দিন
   `product_reviews.txt` অথবা `store_reviews.txt` (বা `review_data.txt` যদি
   সেটা একটি সাধারণ এক্সপোর্ট হয় — extractor সেটাকে ডায়ালগের নিজস্ব হেডিং
   টেক্সট থেকে শ্রেণীবদ্ধ করে, যেমন "Product reviews (N)" /
   "Store reviews (N)")। যদি DevTools থেকে শুধু একটি স্ক্রিনশট পাওয়া যায়,
   সেই ইমেজটি ফোল্ডারে সংরক্ষণ করুন — সেটা কাস্টমার রিভিউ হিসেবে OCR করা হবে।
6. প্রতিটি প্রোডাক্টের জন্য পুনরাবৃত্তি করুন, **এক-ফোল্ডার-প্রতি-প্রোডাক্ট**
   নিয়ম মেনে — দুটি ভিন্ন প্রোডাক্টের ফাইল একই ফোল্ডারে মিশ্রিত করবেন না।
7. **Extractor চালান** (নিচে দেখুন) সব ফোল্ডার প্রস্তুত হয়ে গেলে; এটি
   `input_data_source/`-এর অধীনে প্রতিটি ফোল্ডার পড়ে এবং সম্মিলিত ফলাফল
   `database/product_data.json`-এ লেখে।

---

## সেটআপ

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# স্ক্রিনশটের ঐচ্ছিক OCR (Debian/Ubuntu):
sudo apt install tesseract-ocr
```

---

## Extractor চালানো

ডিফল্টভাবে `input_data_source/` পড়ে এবং `database/product_data.json`-এ লেখে:

```bash
.venv/bin/python extract_to_json.py
```

কাস্টম ইনপুট/আউটপুট:

```bash
.venv/bin/python extract_to_json.py input_data_source/some_folder -o database/product_data.json
```

- প্রোডাক্ট, সেলার, ট্রেড, ইনভেন্টরি, এবং breadcrumb-category ফিল্ডের জন্য
  সংরক্ষিত প্রোডাক্ট পেজে embedded `window.detailData` JSON blob পড়ে।
- `product_reviews.txt` / `store_reviews.txt` / `review_data.txt` রিভিউ-ডায়ালগ
  এক্সপোর্ট পড়ে; একটি ডায়ালগকে কাস্টমার বা স্টোর রিভিউ হিসেবে তার নিজস্ব
  হেডিং টেক্সট থেকে শ্রেণীবদ্ধ করা হয় ("Product reviews (N)" /
  "Store reviews (N)"), ফাইলনাম থেকে নয়।
- স্ক্রিনশট আছে কিন্তু কোনো রিভিউ `.txt` ফাইল নেই এমন ফোল্ডার OCR করা হয়
  (দরকার `pytesseract` + `tesseract-ocr` সিস্টেম বাইনারি) এবং কাস্টমার রিভিউ
  হিসেবে গণ্য হয়; OCR না থাকলে এটি কোনো রিভিউ যোগ করে না।
- সোর্সে যেসব ফিল্ড নেই সেগুলো অনুমান না করে `null`/খালি রাখা হয়।
- প্রিন্ট করে যেমন
  `wrote 7 product(s), 42 customer review(s), 15 store review(s) -> database/product_data.json`।

---

## আউটপুট স্কিমা

`database/product_data.json` একটি JSON অ্যারে; প্রতিটি এলিমেন্টে থাকে:

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
    "reviews": [ /* নিচে রিভিউ শেপ দেখুন */ ]
  },
  "store_reviews": {
    "company_id": "...",
    "company_name": "...",
    "average_star": 4.9,
    "max_star": 5,
    "total_review_count": 120,
    "total_reviewed_orders": 340,
    "rating_breakdown": { /* star -> count */ },
    "reviews": [ /* নিচে রিভিউ শেপ দেখুন */ ]
  },
  "meta": {
    "source": "alibaba.com",
    "viewer_shipping_country": "US",
    "source_folder": "<input folder name>",
    "scraped_at": "2026-07-25T04:12:57+06:00"  // ISO-8601 + অফসেট
  }
}
```

প্রতিটি রিভিউ অবজেক্টে (কাস্টমার বা স্টোর) থাকে: `review_id`,
`reviewer_name`, `reviewer_country`, `rating`, `review_title`, `review_text`,
`review_date` (সোর্সের নিজস্ব "Mon DD, YYYY" ফর্ম), `verified_purchase`,
`repeat_buyer`, `helpful_votes`, `total_votes`, `price_at_review`,
`currency`, `variant`, `images_count`।

---

## ড্যাশবোর্ড

`dashboard.html` self-contained — প্রোডাক্ট ডেটা সরাসরি ফাইলের ভেতরে embedded
(কোনো সার্ভার নেই, কোনো fetch নেই), তাই শুধু ব্রাউজারে খুলুন:

```bash
xdg-open dashboard.html   # অথবা ডাবল-ক্লিক করুন
```

এটি প্রতি প্রোডাক্টের রিভিউ/রেটিং চার্ট, ক্যাটাগরি এবং সেলার-কান্ট্রি চিপস, এবং
একটি সার্চযোগ্য, সর্টযোগ্য প্রোডাক্ট টেবিল (title, category, seller, country,
membership type, price, MOQ, rating, review count) দেখায়। নতুন
`database/product_data.json` তৈরি করতে `extract_to_json.py` পুনরায় চালান এবং
নতুন ডেটা `<script type="application/json" id="productData">` ব্লকে পুনরায়
embed করে রিফ্রেশ করুন। `dashboard.png` হলো রেন্ডার করা ড্যাশবোর্ডের একটি
স্ক্রিনশট।

---

## অন্যান্য ফাইল

- `note/category_assignments.json` — কোন টিম মেম্বার কোন প্রোডাক্ট ক্যাটাগরি
  রিভিউ করছে/অ্যাসাইন করা হয়েছে; টুলিং এটি ব্যবহার করে না, শুধুমাত্র টিমের
  রেফারেন্সের জন্য রাখা হয়েছে।
