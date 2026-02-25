"""
STEP 1: Snowflake Database Setup (Fixed — no CHECK constraints)
Run: python 1_setup_database.py
"""

import snowflake.connector
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

load_dotenv()

SNOWFLAKE_CONFIG = {
    "account":   os.getenv("SNOWFLAKE_ACCOUNT"),
    "user":      os.getenv("SNOWFLAKE_USER"),
    "password":  os.getenv("SNOWFLAKE_PASSWORD"),
    "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
    "database":  os.getenv("SNOWFLAKE_DATABASE",  "ALLIED_BANK_DB"),
    "schema":    os.getenv("SNOWFLAKE_SCHEMA",     "PUBLIC"),
}


def get_connection():
    try:
        conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
        print("✅ Connected to Snowflake successfully.")
        return conn
    except Exception as e:
        print(f"❌ Failed to connect to Snowflake: {e}")
        raise


def create_database_and_schema(cursor):
    db  = SNOWFLAKE_CONFIG["database"]
    sch = SNOWFLAKE_CONFIG["schema"]
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {db}")
    cursor.execute(f"USE DATABASE {db}")
    cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {sch}")
    cursor.execute(f"USE SCHEMA {sch}")
    cursor.execute(f"USE WAREHOUSE {SNOWFLAKE_CONFIG['warehouse']}")
    print(f"✅ Using database: {db}, schema: {sch}")


def create_tables(cursor):
    # Snowflake does not support CHECK constraints — validation is done in app layer

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS account_holders (
        account_id      VARCHAR(20)  PRIMARY KEY,
        full_name       VARCHAR(100) NOT NULL,
        cnic            VARCHAR(20)  UNIQUE NOT NULL,
        phone           VARCHAR(20),
        email           VARCHAR(100),
        city            VARCHAR(50),
        account_type    VARCHAR(20),
        branch          VARCHAR(100),
        balance         FLOAT        DEFAULT 0,
        status          VARCHAR(20)  DEFAULT 'Active',
        opened_date     DATE,
        risk_rating     VARCHAR(10)
    )
    """)
    print("✅ Table 'account_holders' created.")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        txn_id          INTEGER      AUTOINCREMENT PRIMARY KEY,
        account_id      VARCHAR(20)  NOT NULL,
        txn_date        DATE         NOT NULL,
        txn_type        VARCHAR(10),
        category        VARCHAR(50),
        amount          FLOAT        NOT NULL,
        balance_after   FLOAT,
        channel         VARCHAR(20),
        description     VARCHAR(255),
        status          VARCHAR(20)  DEFAULT 'Success'
    )
    """)
    print("✅ Table 'transactions' created.")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id              INTEGER      AUTOINCREMENT PRIMARY KEY,
        timestamp       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
        username        VARCHAR(50),
        role            VARCHAR(20),
        question        TEXT,
        report_context  VARCHAR(200),
        sql_query       TEXT,
        rows_returned   INTEGER,
        ai_insight      TEXT,
        status          VARCHAR(20)  DEFAULT 'Success'
    )
    """)
    print("✅ Table 'audit_log' created.")


def seed_data(cursor):
    cities     = ["Karachi","Lahore","Islamabad","Peshawar","Quetta","Multan","Faisalabad","Rawalpindi"]
    branches   = ["Main Branch","Gulshan","DHA","Johar Town","Blue Area","Saddar","Model Town","Cantt"]
    acc_types  = ["Savings","Current","Fixed Deposit","Salary"]
    channels   = ["ATM","Online","Branch","Mobile App","POS"]
    categories = ["Transfer","Utility Bill","Salary","Shopping","Cash Withdrawal","Loan Payment","Insurance","Investment"]
    risks      = ["Low","Medium","High"]

    names = [
        ("Ahsan Raza","35201-1234567-1"),("Fatima Malik","35202-2345678-2"),
        ("Bilal Chaudhry","35203-3456789-3"),("Sana Khan","35204-4567890-4"),
        ("Usman Tariq","35205-5678901-5"),("Ayesha Iqbal","35206-6789012-6"),
        ("Zubair Ahmed","35207-7890123-7"),("Hira Baig","35208-8901234-8"),
        ("Kamran Siddiqui","35209-9012345-9"),("Nadia Hussain","35210-0123456-0"),
        ("Faisal Nawaz","35211-1234568-1"),("Sara Javed","35212-2345679-2"),
        ("Imran Sheikh","35213-3456780-3"),("Maryam Ali","35214-4567891-4"),
        ("Tariq Mehmood","35215-5678902-5"),("Rabia Noor","35216-6789013-6"),
        ("Hassan Rauf","35217-7890124-7"),("Zara Butt","35218-8901235-8"),
        ("Adeel Farooq","35219-9012346-9"),("Noor Fatima","35220-0123457-0"),
    ]

    accounts = []
    for i, (name, cnic) in enumerate(names):
        acc_id   = f"ABL-{10000+i}"
        city     = random.choice(cities)
        branch   = random.choice(branches)
        acc_type = random.choice(acc_types)
        balance  = round(random.uniform(5000, 500000), 2)
        opened   = (datetime(2018,1,1) + timedelta(days=random.randint(0,1800))).strftime("%Y-%m-%d")
        status   = random.choices(["Active","Inactive","Frozen"], weights=[85,10,5])[0]
        risk     = random.choice(risks)
        phone    = f"03{random.randint(10,49)}-{random.randint(1000000,9999999)}"
        email    = f"{name.split()[0].lower()}.{name.split()[-1].lower()}@email.com"
        accounts.append((acc_id, name, cnic, phone, email, city, acc_type,
                         branch, balance, status, opened, risk))

    # Insert accounts one by one, skipping duplicates
    inserted = 0
    for row in accounts:
        try:
            cursor.execute("""
                INSERT INTO account_holders
                (account_id, full_name, cnic, phone, email, city, account_type,
                 branch, balance, status, opened_date, risk_rating)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, row)
            inserted += 1
        except snowflake.connector.errors.IntegrityError:
            pass  # Skip duplicate account_id or cnic
    print(f"✅ Inserted {inserted} account holders.")

    # Insert transactions
    txns = []
    for acc_id, _, _, _, _, _, _, _, balance, _, opened, _ in accounts:
        start       = datetime.strptime(opened, "%Y-%m-%d")
        running_bal = balance
        for _ in range(random.randint(20, 60)):
            txn_date  = (start + timedelta(days=random.randint(0,1800))).strftime("%Y-%m-%d")
            txn_type  = random.choice(["Credit","Debit"])
            amount    = round(random.uniform(500, 50000), 2)
            channel   = random.choice(channels)
            category  = random.choice(categories)
            status    = random.choices(["Success","Failed","Pending"], weights=[90,5,5])[0]
            desc      = f"{category} via {channel}"
            if txn_type == "Credit":
                running_bal += amount
            else:
                running_bal = max(0, running_bal - amount)
            txns.append((acc_id, txn_date, txn_type, category, amount,
                         round(running_bal, 2), channel, desc, status))

    # Batch insert transactions in chunks of 100
    chunk_size = 100
    for i in range(0, len(txns), chunk_size):
        chunk = txns[i:i+chunk_size]
        cursor.executemany("""
            INSERT INTO transactions
            (account_id, txn_date, txn_type, category, amount,
             balance_after, channel, description, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, chunk)
    print(f"✅ Inserted {len(txns)} transactions.")


def verify_data(cursor):
    cursor.execute("SELECT COUNT(*) FROM account_holders")
    acc_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM transactions")
    txn_count = cursor.fetchone()[0]
    print(f"\n📊 Verification:")
    print(f"   account_holders : {acc_count} rows")
    print(f"   transactions    : {txn_count} rows")


def main():
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        create_database_and_schema(cursor)
        create_tables(cursor)
        seed_data(cursor)
        verify_data(cursor)
        conn.commit()
        print("\n✅ Snowflake setup complete! Run: streamlit run 2_chatbot_app.py")
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Setup failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()