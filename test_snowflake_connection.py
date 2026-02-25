"""
Snowflake Connection Test
Run this BEFORE launching the main app to verify your credentials.

Usage:
    python test_snowflake_connection.py
"""

import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 50)
print("  Allied Bank — Snowflake Connection Test")
print("=" * 50)

# ── Check env vars ──────────────────────────────────
required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER", "SNOWFLAKE_PASSWORD"]
missing  = [k for k in required if not os.getenv(k)]

if missing:
    print(f"\n❌ Missing environment variables: {', '.join(missing)}")
    print("   Create a .env file using .env.example as a template.")
    exit(1)

print("\n✅ Credentials found in environment.")

# ── Attempt connection ──────────────────────────────
try:
    import snowflake.connector

    conn = snowflake.connector.connect(
        account   = os.getenv("SNOWFLAKE_ACCOUNT"),
        user      = os.getenv("SNOWFLAKE_USER"),
        password  = os.getenv("SNOWFLAKE_PASSWORD"),
        database  = os.getenv("SNOWFLAKE_DATABASE",  "ALLIED_BANK"),
        schema    = os.getenv("SNOWFLAKE_SCHEMA",    "PUBLIC"),
        warehouse = os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        role      = os.getenv("SNOWFLAKE_ROLE") or None,
    )

    cur = conn.cursor()

    # Basic info
    cur.execute("SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_DATABASE(), "
                "CURRENT_SCHEMA(), CURRENT_WAREHOUSE(), CURRENT_VERSION()")
    row = cur.fetchone()
    print(f"\n✅ Connected successfully!")
    print(f"   User      : {row[0]}")
    print(f"   Role      : {row[1]}")
    print(f"   Database  : {row[2]}")
    print(f"   Schema    : {row[3]}")
    print(f"   Warehouse : {row[4]}")
    print(f"   Version   : {row[5]}")

    # Check required tables
    DB     = os.getenv("SNOWFLAKE_DATABASE", "ALLIED_BANK")
    SCHEMA = os.getenv("SNOWFLAKE_SCHEMA",   "PUBLIC")

    print(f"\n── Checking tables in {DB}.{SCHEMA} ──")
    for table in ["ACCOUNT_HOLDERS", "TRANSACTIONS"]:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {DB}.{SCHEMA}.{table}")
            count = cur.fetchone()[0]
            print(f"   ✅ {table}: {count:,} rows")
        except Exception as e:
            print(f"   ❌ {table}: {e}")

    # Check / create audit log table
    print(f"\n── Checking AUDIT_LOG table ──")
    try:
        cur.execute(f"SELECT COUNT(*) FROM {DB}.{SCHEMA}.AUDIT_LOG")
        count = cur.fetchone()[0]
        print(f"   ✅ AUDIT_LOG exists: {count:,} rows")
    except Exception:
        print(f"   ⚠️  AUDIT_LOG not found — it will be created automatically on first app run.")

    conn.close()
    print("\n✅ All checks passed. You can now run the app:")
    print("   python -m streamlit run 2_chatbot_app_snowflake.py\n")

except ImportError:
    print("\n❌ snowflake-connector-python is not installed.")
    print("   Run: pip install snowflake-connector-python")

except snowflake.connector.errors.DatabaseError as e:
    print(f"\n❌ Connection failed: {e}")
    print("\nCommon fixes:")
    print("  • SNOWFLAKE_ACCOUNT: use format like 'xy12345.us-east-1' (no https://)")
    print("  • SNOWFLAKE_WAREHOUSE: make sure it exists and is not suspended")
    print("  • SNOWFLAKE_DATABASE: confirm the database name is correct and you have access")

except Exception as e:
    print(f"\n❌ Unexpected error: {e}")
