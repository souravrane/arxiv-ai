import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

try:
    # Try DATABASE_URL first
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        from urllib.parse import urlparse
        parsed = urlparse(database_url)
        conn = mysql.connector.connect(
            host=parsed.hostname or "localhost",
            port=int(parsed.port) if parsed.port else 3306,
            database=parsed.path.lstrip('/'),
            user=parsed.username,
            password=parsed.password
        )
    else:
        # Use individual variables
        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
        )

    cur = conn.cursor()
    cur.execute("SELECT VERSION();")
    version = cur.fetchone()
    print(f"✓ Connected successfully!")
    print(f"MySQL version: {version[0]}")

    cur.close()
    conn.close()

except Exception as e:
    print(f"✗ Connection failed: {e}")