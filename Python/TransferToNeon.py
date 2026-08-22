import os
import sys
import psycopg2
from psycopg2.extras import execute_batch
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, '.env.local'))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, '.env'))

# Local database connection settings
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_NAME = os.environ.get("DB_NAME", "Steam")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASS = os.environ.get("DB_PASS", "")

# Neon database connection settings
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_local_connection():
    """Connect to the local PostgreSQL database."""
    kwargs = {
        "host": DB_HOST,
        "port": DB_PORT,
        "dbname": DB_NAME,
        "user": DB_USER,
    }
    if DB_PASS:
        kwargs["password"] = DB_PASS
    
    print(f"Connecting to local database: {DB_NAME} on {DB_HOST}:{DB_PORT} as {DB_USER}")
    return psycopg2.connect(**kwargs)

def get_neon_connection():
    """Connect to the Neon PostgreSQL database."""
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set in environment or .env.local")
    
    print("Connecting to Neon database...")
    return psycopg2.connect(DATABASE_URL)

def ensure_tables(neon_conn):
    """Ensure tables exist in Neon DB."""
    import db
    db.create_tables(neon_conn)
    print("Verified Neon database schema.")

def transfer_table(local_conn, neon_conn, table_name, columns, conflict_clause="DO NOTHING"):
    """Transfer data for a specific table."""
    print(f"Transferring table: {table_name}...")
    
    # Read from local
    with local_conn.cursor() as cur:
        cur.execute(f"SELECT {', '.join(columns)} FROM {table_name}")
        rows = cur.fetchall()
        
    if not rows:
        print(f"  No rows to transfer for {table_name}.")
        return

    print(f"  Fetched {len(rows)} rows from local DB.")
    
    # Write to Neon
    placeholders = ", ".join(["%s"] * len(columns))
    insert_sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders}) ON CONFLICT {conflict_clause};"
    
    with neon_conn.cursor() as cur:
        execute_batch(cur, insert_sql, rows, page_size=1000)
    
    neon_conn.commit()
    print(f"  Successfully inserted/upserted {len(rows)} rows into Neon.")

def transfer_all():
    print("Starting database transfer to Neon...\n")
    
    try:
        local_conn = get_local_connection()
    except Exception as e:
        print(f"Failed to connect to local database: {e}")
        print("Please ensure your local PostgreSQL server is running and the credentials are correct.")
        return
        
    try:
        neon_conn = get_neon_connection()
    except Exception as e:
        print(f"Failed to connect to Neon database: {e}")
        return

    try:
        ensure_tables(neon_conn)
        
        # 1. Transfer tags
        transfer_table(
            local_conn, neon_conn, 
            table_name="tags", 
            columns=["id", "name"],
            conflict_clause="(id) DO NOTHING"
        )
        
        # 2. Transfer games
        transfer_table(
            local_conn, neon_conn, 
            table_name="games", 
            columns=["id", "name", "tags"],
            conflict_clause="(id) DO UPDATE SET name = EXCLUDED.name, tags = EXCLUDED.tags"
        )
        
        # 3. Transfer weeksheet
        transfer_table(
            local_conn, neon_conn, 
            table_name="weeksheet", 
            columns=["week_date", "rank", "game_id", "price", "discount", "rating", "last_week_rank", "consecutive_weeks"],
            conflict_clause="(week_date, rank) DO UPDATE SET game_id = EXCLUDED.game_id, price = EXCLUDED.price, discount = EXCLUDED.discount, rating = EXCLUDED.rating, last_week_rank = EXCLUDED.last_week_rank, consecutive_weeks = EXCLUDED.consecutive_weeks"
        )
        
        print("\nDatabase transfer completed successfully!")
        
    except Exception as e:
        print(f"An error occurred during transfer: {e}")
        neon_conn.rollback()
    finally:
        local_conn.close()
        neon_conn.close()

if __name__ == "__main__":
    transfer_all()
