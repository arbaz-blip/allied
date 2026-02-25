# 🏦 Allied Bank — AI-Powered Analytics Chatbot
### Streamlit + Mistral AI + SQLite + Power BI

---

## 📁 Project Structure

```
bank_chatbot/
│
├── 1_setup_database.py      ← STEP 1: Create SQLite DB with sample data
├── 2_chatbot_app.py         ← STEP 2: Streamlit chatbot (main app)
├── 3_export_for_powerbi.py  ← STEP 3: Export CSVs/Excel for Power BI
│
├── allied_bank.db           ← Auto-created by Step 1
├── powerbi_data/            ← Auto-created by Step 3
│   ├── account_holders.csv
│   ├── transactions.csv
│   ├── kpi_*.csv
│   └── allied_bank_powerbi.xlsx
│
├── requirements.txt
├── .env.example             ← Copy to .env and add your API key
└── README.md
```

---

## 🚀 Quick Setup (5 Steps)

### Step 1 — Install Requirements

```bash
pip install -r requirements.txt
```

### Step 2 — Get Mistral API Key

1. Go to https://console.mistral.ai/
2. Create a free account
3. Generate an API key
4. Copy `.env.example` → `.env`
5. Paste your key:

```
MISTRAL_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx
```

### Step 3 — Create the Database

```bash
python 1_setup_database.py
```

**What this creates:**

**Table: `account_holders`** (20 sample accounts)
| Column | Type | Description |
|--------|------|-------------|
| account_id | TEXT PK | e.g., ABL-10000 |
| full_name | TEXT | Account holder name |
| cnic | TEXT | Pakistani CNIC (unique) |
| phone | TEXT | Mobile number |
| email | TEXT | Email address |
| city | TEXT | City (Karachi, Lahore, etc.) |
| account_type | TEXT | Savings / Current / Fixed Deposit / Salary |
| branch | TEXT | Branch name |
| balance | REAL | Current balance (PKR) |
| status | TEXT | Active / Inactive / Frozen |
| opened_date | TEXT | Date account opened |
| risk_rating | TEXT | Low / Medium / High |

**Table: `transactions`** (400–1200 sample transactions)
| Column | Type | Description |
|--------|------|-------------|
| txn_id | INTEGER PK | Auto-increment |
| account_id | TEXT FK | Links to account_holders |
| txn_date | TEXT | Transaction date (YYYY-MM-DD) |
| txn_type | TEXT | Credit / Debit |
| category | TEXT | Transfer, Salary, Shopping, etc. |
| amount | REAL | Transaction amount (PKR) |
| balance_after | REAL | Balance after transaction |
| channel | TEXT | ATM / Online / Branch / Mobile App / POS |
| description | TEXT | Transaction description |
| status | TEXT | Success / Failed / Pending |

### Step 4 — Run the Chatbot

```bash
streamlit run 2_chatbot_app.py
```

Open: http://localhost:8501

### Step 5 — Export for Power BI

```bash
python 3_export_for_powerbi.py
```

---

## 🤖 How the Chatbot Works

```
User types question in plain English
        ↓
Mistral AI converts it to a SQLite SELECT query
        ↓
Query runs against allied_bank.db
        ↓
Results shown as table + auto-generated chart
        ↓
Mistral AI generates a human-readable insight
```

### Architecture Flow:

```
┌──────────────────────────────────────────────────────┐
│                  Streamlit Frontend                    │
│  (Chat UI · KPI Cards · Charts · Tables)              │
└───────────────────┬──────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────┐
│              Mistral AI Layer                          │
│  • Receives: user question + DB schema + history      │
│  • Returns:  SQL query + plain English explanation    │
│  • Also:     generates insight from query results     │
└───────────────────┬──────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────┐
│              SQLite Database                           │
│  account_holders ←── FK ──→ transactions             │
└───────────────────┬──────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────┐
│              Power BI (separate)                       │
│  Connects via Excel export or ODBC driver             │
│  Reads same data for dashboards and KPIs              │
└──────────────────────────────────────────────────────┘
```

---

## 💬 Sample Questions to Ask

| Question | What Mistral generates |
|----------|------------------------|
| Show total deposits per city | GROUP BY city, SUM(balance) |
| Top 5 accounts by balance | ORDER BY balance DESC LIMIT 5 |
| How many transactions failed this year? | WHERE status='Failed' filter |
| Monthly credit vs debit trend | strftime monthly aggregation |
| Which branch has the most accounts? | JOIN + GROUP BY branch |
| Average balance by account type | GROUP BY account_type, AVG(balance) |
| Customers with high risk rating | WHERE risk_rating='High' |
| Total amount transacted via ATM | WHERE channel='ATM' SUM |
| Accounts opened in Lahore | WHERE city='Lahore' |
| Top spending categories | GROUP BY category, SUM debit |

---

## 📊 Power BI Setup

### Option A: Excel File (Recommended)

1. Run `python 3_export_for_powerbi.py`
2. Open **Power BI Desktop**
3. **Home → Get Data → Excel Workbook**
4. Navigate to `powerbi_data/allied_bank_powerbi.xlsx`
5. Select all sheets → **Load**

### Option B: Direct SQLite Connection

1. Download SQLite ODBC driver:
   https://www.ch-werner.de/sqliteodbc/
2. Create a System DSN pointing to `allied_bank.db`
3. In Power BI: **Get Data → ODBC → Your DSN**

### Recommended KPI Visuals

| Visual Type | Data | KPI |
|-------------|------|-----|
| Card | COUNT(account_id) | Total Accounts |
| Card | SUM(balance) | Total Deposits |
| Card | COUNT WHERE status=Failed | Failed Transactions |
| Bar Chart | Balance by City | City-wise Deposits |
| Line Chart | Monthly Transaction Volume | Growth Trend |
| Donut Chart | Account Type Distribution | Portfolio Mix |
| Table | Branch Performance | Branch KPIs |
| Gauge | High Risk Exposure | Risk Dashboard |
| Heatmap Matrix | Channel × Category | Usage Patterns |

---

## 🔒 Security Notes

- The chatbot is **read-only** — Mistral cannot generate INSERT/UPDATE/DELETE
- All queries are validated before execution
- Conversation history is session-only (not stored)
- For production: add login with `streamlit-authenticator`
- For on-prem: replace Mistral API with a local model (Ollama + Mistral 7B)

---

## 🏠 Running Fully On-Premises (No Cloud)

To match the Allied Bank PDF requirement (no internet):

```bash
# 1. Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# 2. Pull Mistral model locally
ollama pull mistral:7b

# 3. Change in 2_chatbot_app.py:
#    Replace: client = Mistral(api_key=MISTRAL_KEY)
#    With:    import ollama (or use requests to localhost:11434)
```

The Ollama API runs on `http://localhost:11434` — fully offline.

---

## 🛠️ Customization

### Add more accounts
Edit `names` list in `1_setup_database.py` and re-run.

### Add more transaction categories
Edit `categories` list in `1_setup_database.py`.

### Change Mistral model
In `2_chatbot_app.py`, change:
```python
MODEL = "mistral-large-latest"    # Most capable
MODEL = "open-mistral-7b"         # Free tier / faster
MODEL = "mistral-medium-latest"   # Balanced
```

### Add authentication
```bash
pip install streamlit-authenticator
```

---

## ❓ Troubleshooting

| Error | Fix |
|-------|-----|
| `ModuleNotFoundError: mistralai` | `pip install mistralai` |
| `API key not found` | Create `.env` file with your key |
| `Database not found` | Run `python 1_setup_database.py` first |
| Chart not showing | Toggle "Auto-generate Charts" in sidebar |
| Wrong SQL generated | Rephrase question more specifically |

---

*Built for Allied Bank · Mistral AI + Streamlit + SQLite + Power BI*
