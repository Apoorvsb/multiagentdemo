import csv
import re
import sys
import os
import psycopg2
import psycopg2.extras

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config


# ─────────────────────────────────────────────
# CONNECTION
# ─────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        dbname=config.POSTGRES_DB,
        user=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
    )


# ─────────────────────────────────────────────
# CREATE TABLES
# ─────────────────────────────────────────────

def create_tables():
    sql = """
    CREATE TABLE IF NOT EXISTS products (
        product_id        TEXT PRIMARY KEY,
        name              TEXT NOT NULL,
        category          TEXT,
        brand             TEXT,
        price             FLOAT,
        original_price    FLOAT,
        discount_pct      TEXT,
        rating            FLOAT,
        rating_count      TEXT,
        description       TEXT,
        img_link          TEXT,
        product_link      TEXT,
        availability      BOOLEAN DEFAULT TRUE,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS reviews (
        review_id         TEXT PRIMARY KEY,
        product_id        TEXT NOT NULL REFERENCES products(product_id),
        customer_name     TEXT,
        rating            FLOAT,
        review_title      TEXT,
        review_text       TEXT,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print("Tables created — products and reviews.")


# ─────────────────────────────────────────────
# TRANSFORM HELPERS
# ─────────────────────────────────────────────

def clean_price(price_str):
    """₹1,099 → 1099.0"""
    if not price_str:
        return None
    cleaned = re.sub(r'[₹,\s]', '', str(price_str))
    try:
        return float(cleaned)
    except:
        return None


def clean_rating(rating_str):
    """'4.2' → 4.2"""
    if not rating_str:
        return None
    try:
        return float(str(rating_str).strip())
    except:
        return None


def clean_category(category_str):
    """Computers&Accessories|Cables|... → Computers&Accessories"""
    if not category_str:
        return "General"
    return category_str.split("|")[0].strip()


def extract_brand(product_name):
    """First word of product name"""
    if not product_name:
        return "Unknown"
    return product_name.split()[0].strip()


def split_packed_field(field_str):
    """Split comma-separated packed field into list"""
    if not field_str:
        return []
    return [item.strip() for item in field_str.split(",") if item.strip()]


# ─────────────────────────────────────────────
# EXTRACT + TRANSFORM
# ─────────────────────────────────────────────

def extract_and_transform(filepath):
    products = {}   # product_id → product dict
    reviews  = []   # list of review dicts

    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            product_id = row.get("product_id", "").strip()
            if not product_id:
                continue

            # ── STREAM 1: Products ────────────────────────────
            if product_id not in products:
                products[product_id] = {
                    "product_id":     product_id,
                    "name":           row.get("product_name", "").strip(),
                    "category":       clean_category(row.get("category", "")),
                    "brand":          extract_brand(row.get("product_name", "")),
                    "price":          clean_price(row.get("discounted_price", "")),
                    "original_price": clean_price(row.get("actual_price", "")),
                    "discount_pct":   row.get("discount_percentage", "").strip(),
                    "rating":         clean_rating(row.get("rating", "")),
                    "rating_count":   row.get("rating_count", "").strip(),
                    "description":    row.get("about_product", "").strip()[:2000],
                    "img_link":       row.get("img_link", "").strip(),
                    "product_link":   row.get("product_link", "").strip(),
                    "availability":   True,
                }

            # ── STREAM 2: Reviews ─────────────────────────────
            # Each row has comma-packed review fields
            review_ids    = split_packed_field(row.get("review_id",      ""))
            user_names    = split_packed_field(row.get("user_name",      ""))
            review_titles = split_packed_field(row.get("review_title",   ""))
            review_texts  = split_packed_field(row.get("review_content", ""))
            product_rating = clean_rating(row.get("rating", ""))

            # Zip them together — one review per index
            for idx, review_id in enumerate(review_ids):
                if not review_id:
                    continue
                reviews.append({
                    "review_id":     review_id,
                    "product_id":    product_id,
                    "customer_name": user_names[idx]    if idx < len(user_names)    else "Anonymous",
                    "rating":        product_rating,
                    "review_title":  review_titles[idx] if idx < len(review_titles) else "",
                    "review_text":   review_texts[idx]  if idx < len(review_texts)  else "",
                })

    return list(products.values()), reviews


# ─────────────────────────────────────────────
# LOAD
# ─────────────────────────────────────────────

def load_products(products):
    inserted = 0
    with get_conn() as conn:
        with conn.cursor() as cur:
            for p in products:
                try:
                    cur.execute(
                        """
                        INSERT INTO products
                            (product_id, name, category, brand, price,
                             original_price, discount_pct, rating,
                             rating_count, description, img_link,
                             product_link, availability)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (product_id) DO NOTHING
                        """,
                        [
                            p["product_id"],
                            p["name"],
                            p["category"],
                            p["brand"],
                            p["price"],
                            p["original_price"],
                            p["discount_pct"],
                            p["rating"],
                            p["rating_count"],
                            p["description"],
                            p["img_link"],
                            p["product_link"],
                            p["availability"],
                        ]
                    )
                    inserted += 1
                except Exception as e:
                    print(f"Product error {p['product_id']}: {e}")
    print(f"Loaded {inserted} products into products table.")
    return inserted


def load_reviews(reviews):
    inserted  = 0
    skipped   = 0
    seen_ids  = set()

    with get_conn() as conn:
        with conn.cursor() as cur:
            for r in reviews:
                if r["review_id"] in seen_ids:
                    skipped += 1
                    continue
                seen_ids.add(r["review_id"])
                try:
                    cur.execute(
                        """
                        INSERT INTO reviews
                            (review_id, product_id, customer_name,
                             rating, review_title, review_text)
                        VALUES (%s,%s,%s,%s,%s,%s)
                        ON CONFLICT (review_id) DO NOTHING
                        """,
                        [
                            r["review_id"],
                            r["product_id"],
                            r["customer_name"],
                            r["rating"],
                            r["review_title"],
                            r["review_text"][:1000] if r["review_text"] else "",
                        ]
                    )
                    inserted += 1
                except Exception as e:
                    print(f"Review error {r['review_id']}: {e}")
    print(f"Loaded {inserted} reviews into reviews table.")
    print(f"Skipped {skipped} duplicate review IDs.")
    return inserted


# ─────────────────────────────────────────────
# VERIFY
# ─────────────────────────────────────────────

def verify():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM products")
            p_count = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM reviews")
            r_count = cur.fetchone()[0]
            cur.execute("SELECT category, COUNT(*) FROM products GROUP BY category ORDER BY COUNT(*) DESC LIMIT 5")
            categories = cur.fetchall()

    print(f"\n=== Verification ===")
    print(f"products table → {p_count} rows")
    print(f"reviews  table → {r_count} rows")
    print(f"\nTop categories:")
    for cat, count in categories:
        print(f"  {cat:<40} {count}")


# ─────────────────────────────────────────────
# MAIN — ETL PIPELINE
# ─────────────────────────────────────────────

if __name__ == "__main__":
    filepath = os.path.join(os.path.dirname(__file__), "amazon.csv")

    if not os.path.exists(filepath):
        print(f"ERROR: amazon.csv not found at {filepath}")
        print("Copy amazon.csv to the tools/ folder first.")
        sys.exit(1)

    print("=" * 50)
    print("ETL Pipeline — Amazon Products")
    print("=" * 50)

    # Step 1 — Create tables
    print("\n[1/4] Creating tables...")
    create_tables()

    # Step 2 — Extract and Transform
    print(f"\n[2/4] Extracting from {filepath}...")
    products, reviews = extract_and_transform(filepath)
    print(f"Extracted {len(products)} unique products")
    print(f"Extracted {len(reviews)} reviews")

    # Step 3 — Load
    print("\n[3/4] Loading products...")
    load_products(products)

    print("\n[4/4] Loading reviews...")
    load_reviews(reviews)

    # Step 4 — Verify
    verify()

    print("\nETL pipeline completed successfully.")