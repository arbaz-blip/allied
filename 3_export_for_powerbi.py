"""
STEP 3: Export Data for Power BI
Run this to generate CSV/Excel files for Power BI connection.
Command: python 3_export_for_powerbi.py

Power BI can also connect directly to SQLite using ODBC.
This script exports ready-to-use flat files + a pre-aggregated KPI sheet.
"""

import sqlite3
import pandas as pd
import os

DB_PATH     = "allied_bank.db"
EXPORT_DIR  = "powerbi_data"

os.makedirs(EXPORT_DIR, exist_ok=True)


def export(query: str, filename: str, label: str):
    conn = sqlite3.connect(DB_PATH)
    df   = pd.read_sql_query(query, conn)
    conn.close()
    path = os.path.join(EXPORT_DIR, filename)
    df.to_csv(path, index=False)
    print(f"✅ Exported {label} → {path}  ({len(df)} rows)")
    return df


def main():
    print("=" * 55)
    print("  Allied Bank — Power BI Data Export")
    print("=" * 55)

    # ── 1. Raw tables ────────────────────────────────
    export("SELECT * FROM account_holders", "account_holders.csv", "Account Holders")
    export("SELECT * FROM transactions",    "transactions.csv",    "Transactions")

    # ── 2. KPI: Total Balance by City ────────────────
    export("""
        SELECT city,
               COUNT(account_id)       AS total_accounts,
               ROUND(SUM(balance),2)   AS total_balance,
               ROUND(AVG(balance),2)   AS avg_balance
        FROM account_holders
        GROUP BY city
        ORDER BY total_balance DESC
    """, "kpi_balance_by_city.csv", "KPI: Balance by City")

    # ── 3. KPI: Monthly Transaction Volume ───────────
    export("""
        SELECT strftime('%Y-%m', txn_date) AS month,
               txn_type,
               COUNT(*)                   AS txn_count,
               ROUND(SUM(amount),2)        AS total_amount
        FROM transactions
        WHERE status = 'Success'
        GROUP BY month, txn_type
        ORDER BY month
    """, "kpi_monthly_txn_volume.csv", "KPI: Monthly Transaction Volume")

    # ── 4. KPI: Transactions by Channel ──────────────
    export("""
        SELECT channel,
               COUNT(*)              AS total_txns,
               ROUND(SUM(amount),2)  AS total_amount,
               SUM(CASE WHEN status='Failed' THEN 1 ELSE 0 END) AS failed_txns
        FROM transactions
        GROUP BY channel
        ORDER BY total_txns DESC
    """, "kpi_txn_by_channel.csv", "KPI: Transactions by Channel")

    # ── 5. KPI: Top Spending Categories ──────────────
    export("""
        SELECT category,
               COUNT(*)              AS txn_count,
               ROUND(SUM(amount),2)  AS total_debit
        FROM transactions
        WHERE txn_type='Debit' AND status='Success'
        GROUP BY category
        ORDER BY total_debit DESC
    """, "kpi_spending_categories.csv", "KPI: Spending Categories")

    # ── 6. KPI: Account Distribution ─────────────────
    export("""
        SELECT account_type,
               status,
               risk_rating,
               COUNT(*) AS count
        FROM account_holders
        GROUP BY account_type, status, risk_rating
        ORDER BY count DESC
    """, "kpi_account_distribution.csv", "KPI: Account Distribution")

    # ── 7. KPI: Branch Performance ───────────────────
    export("""
        SELECT ah.branch,
               COUNT(DISTINCT ah.account_id)  AS accounts,
               ROUND(SUM(ah.balance),2)        AS total_deposits,
               COUNT(t.txn_id)                 AS total_transactions,
               ROUND(SUM(t.amount),2)           AS total_txn_value
        FROM account_holders ah
        LEFT JOIN transactions t ON ah.account_id = t.account_id AND t.status='Success'
        GROUP BY ah.branch
        ORDER BY total_deposits DESC
    """, "kpi_branch_performance.csv", "KPI: Branch Performance")

    # ── 8. KPI: Risk Rating Summary ──────────────────
    export("""
        SELECT risk_rating,
               COUNT(*)              AS accounts,
               ROUND(SUM(balance),2) AS total_exposure,
               ROUND(AVG(balance),2) AS avg_balance
        FROM account_holders
        GROUP BY risk_rating
    """, "kpi_risk_summary.csv", "KPI: Risk Rating Summary")

    # ── 9. Combined Excel (all sheets in one file) ───
    print("\n📊 Creating combined Excel workbook...")
    excel_path = os.path.join(EXPORT_DIR, "allied_bank_powerbi.xlsx")
    conn       = sqlite3.connect(DB_PATH)

    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        sheets = {
            "Account Holders":         "SELECT * FROM account_holders",
            "Transactions":            "SELECT * FROM transactions",
            "Balance by City":         "SELECT city, COUNT(account_id) as total_accounts, ROUND(SUM(balance),2) as total_balance, ROUND(AVG(balance),2) as avg_balance FROM account_holders GROUP BY city ORDER BY total_balance DESC",
            "Monthly Volume":          "SELECT strftime('%Y-%m', txn_date) AS month, txn_type, COUNT(*) AS txn_count, ROUND(SUM(amount),2) AS total_amount FROM transactions WHERE status='Success' GROUP BY month, txn_type ORDER BY month",
            "Channel Analysis":        "SELECT channel, COUNT(*) AS total_txns, ROUND(SUM(amount),2) AS total_amount, SUM(CASE WHEN status='Failed' THEN 1 ELSE 0 END) AS failed_txns FROM transactions GROUP BY channel",
            "Spending Categories":     "SELECT category, COUNT(*) AS txn_count, ROUND(SUM(amount),2) AS total_debit FROM transactions WHERE txn_type='Debit' AND status='Success' GROUP BY category ORDER BY total_debit DESC",
            "Branch Performance":      "SELECT ah.branch, COUNT(DISTINCT ah.account_id) AS accounts, ROUND(SUM(ah.balance),2) AS total_deposits FROM account_holders ah GROUP BY ah.branch ORDER BY total_deposits DESC",
            "Risk Summary":            "SELECT risk_rating, COUNT(*) AS accounts, ROUND(SUM(balance),2) AS total_exposure FROM account_holders GROUP BY risk_rating",
        }
        for sheet_name, sql in sheets.items():
            df = pd.read_sql_query(sql, conn)
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"   ✅ Sheet: {sheet_name}")

    conn.close()
    print(f"\n📁 Excel file saved: {excel_path}")

    print("\n" + "=" * 55)
    print("POWER BI CONNECTION INSTRUCTIONS")
    print("=" * 55)
    print("""
Option A — Connect via Excel file (easiest):
  1. Open Power BI Desktop
  2. Home → Get Data → Excel Workbook
  3. Browse to: powerbi_data/allied_bank_powerbi.xlsx
  4. Select all sheets → Load
  5. Build your visuals!

Option B — Connect directly to SQLite via ODBC:
  1. Install SQLite ODBC driver:
     https://www.ch-werner.de/sqliteodbc/
  2. In Power BI: Get Data → ODBC
  3. DSN: point to allied_bank.db
  4. Load tables directly

RECOMMENDED KPI VISUALS IN POWER BI:
  📊 Bar Chart   → Branch Performance (total_deposits)
  🗺️ Map Visual  → Balance by City
  📈 Line Chart  → Monthly Volume (trend over time)
  🍩 Donut Chart → Account Distribution (by type/status)
  🔥 Heatmap     → Channel vs Category (matrix)
  📋 Card        → Total Accounts, Total Balance, Failed Txns
  ⚠️  Gauge       → Risk Rating Exposure
""")


if __name__ == "__main__":
    main()
