"""
One-time script: generates sentence-transformer embeddings for all products
and stores them in the PostgreSQL products table via pgvector.

Run once after enabling pgvector:
    pip install sentence-transformers psycopg2-binary
    python scripts/generate_embeddings.py
"""

import os
import psycopg2
import psycopg2.extras
from sentence_transformers import SentenceTransformer

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "multiagent")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASS = os.getenv("POSTGRES_PASSWORD", "")

BATCH_SIZE = 64
MODEL_NAME = "all-MiniLM-L6-v2"  # 384 dims, ~80MB, CPU-friendly


def main():
    print(f"Loading model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)

    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASS,
    )
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Enable pgvector and add column if not already done
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    cur.execute("""
        ALTER TABLE products
        ADD COLUMN IF NOT EXISTS embedding vector(384)
    """)
    conn.commit()
    print("pgvector extension enabled, embedding column ready.")

    cur.execute("SELECT COUNT(*) FROM products WHERE embedding IS NULL")
    remaining = cur.fetchone()["count"]
    print(f"Products needing embeddings: {remaining}")

    cur.execute("""
        SELECT product_id, name, category, brand, description
        FROM products WHERE embedding IS NULL
    """)
    products = cur.fetchall()

    for i in range(0, len(products), BATCH_SIZE):
        batch = products[i:i + BATCH_SIZE]
        texts = [
            f"{p['name']} {p['category'] or ''} {p['brand'] or ''} {(p['description'] or '')[:200]}" for p in batch
        ]
        embeddings = model.encode(texts, show_progress_bar=False)

        update_cur = conn.cursor()
        for product, emb in zip(batch, embeddings):
            update_cur.execute(
                "UPDATE products SET embedding = %s WHERE product_id = %s",
                [emb.tolist(), product["product_id"]],
            )
        conn.commit()
        done = min(i + BATCH_SIZE, len(products))
        print(f"  [{done}/{len(products)}] embeddings stored")

    # Create IVFFlat index for fast approximate nearest-neighbour search
    print("Creating vector index...")
    cur.execute("""
        CREATE INDEX IF NOT EXISTS products_embedding_idx
        ON products USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 50)
    """)
    conn.commit()
    print("Done. All embeddings generated and indexed.")
    conn.close()


if __name__ == "__main__":
    main()
