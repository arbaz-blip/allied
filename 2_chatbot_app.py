"""
Allied Bank — Power BI Companion + AI Chatbot (v5 — Snowflake Edition)
=======================================================================
MIGRATION: SQLite3  →  Snowflake

Changes from v4:
  ✅ All DB calls now go to Snowflake (snowflake-connector-python)
  ✅ Connection pooling via @st.cache_resource
  ✅ Snowflake-compatible SQL dialect (no sqlite3 quirks)
  ✅ .env-based credential management
  ✅ All other features preserved (Power BI metadata, DAX, roles, audit log)

Prerequisites:
  pip install snowflake-connector-python streamlit plotly mistralai python-dotenv

.env file must contain:
  SNOWFLAKE_ACCOUNT=your_account_identifier
  SNOWFLAKE_USER=your_username
  SNOWFLAKE_PASSWORD=your_password
  SNOWFLAKE_WAREHOUSE=COMPUTE_WH
  SNOWFLAKE_DATABASE=ALLIED_BANK_DB
  SNOWFLAKE_SCHEMA=PUBLIC
  MISTRAL_API_KEY=your_mistral_key

Command: python -m streamlit run 2_chatbot_app.py
"""

import streamlit as st
import snowflake.connector
import pandas as pd
import plotly.express as px
import json, re, os, requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ─── CONFIG ───────────────────────────────────────────
AI_MODE       = "mistral"            # "mistral" | "ollama"
MISTRAL_KEY   = os.getenv("MISTRAL_API_KEY", "YOUR_KEY_HERE")
MISTRAL_MODEL = "mistral-large-latest"
OLLAMA_URL    = "http://localhost:11434/api/generate"
OLLAMA_MODEL  = "mistral"
METADATA_PATH = "powerbi_metadata.json"
DAX_PATH      = "dax_measures.json"

# ─── SNOWFLAKE CONNECTION CONFIG ──────────────────────
SNOWFLAKE_CONFIG = {
    "account":   os.getenv("SNOWFLAKE_ACCOUNT"),
    "user":      os.getenv("SNOWFLAKE_USER"),
    "password":  os.getenv("SNOWFLAKE_PASSWORD"),
    "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
    "database":  os.getenv("SNOWFLAKE_DATABASE",  "ALLIED_BANK_DB"),
    "schema":    os.getenv("SNOWFLAKE_SCHEMA",     "PUBLIC"),
}

# ─── USERS & PERMISSIONS ──────────────────────────────
USERS = {
    "admin":   {"password": "admin123",   "role": "Admin",   "name": "Admin User"},
    "analyst": {"password": "analyst123", "role": "Analyst", "name": "Sara Khan"},
    "viewer":  {"password": "viewer123",  "role": "Viewer",  "name": "Ahmed Raza"},
}
PERMS = {
    "Viewer":  {"can_export": False, "can_audit": False},
    "Analyst": {"can_export": True,  "can_audit": False},
    "Admin":   {"can_export": True,  "can_audit": True},
}

# ═══════════════════════════════════════════════════════
# SNOWFLAKE CONNECTION LAYER
# ═══════════════════════════════════════════════════════

@st.cache_resource
def get_snowflake_connection():
    try:
        conn = snowflake.connector.connect(**SNOWFLAKE_CONFIG)
        return conn
    except Exception as e:
        st.error(f"❌ Snowflake connection failed: {e}")
        st.stop()


def qry(sql: str) -> pd.DataFrame:
    try:
        sql = re.sub(r"```(?:sql)?", "", sql, flags=re.IGNORECASE).strip()
        sql = sql.strip("`").strip().rstrip(";").strip()

        conn   = get_snowflake_connection()
        cursor = conn.cursor()
        cursor.execute(sql)
        rows    = cursor.fetchall()
        columns = [desc[0].lower() for desc in cursor.description]
        cursor.close()
        return pd.DataFrame(rows, columns=columns)

    except snowflake.connector.errors.ProgrammingError as e:
        err = str(e)
        if "does not exist" in err.lower() or "invalid identifier" in err.lower():
            msg = f"Column/table not found in Snowflake — {err}"
        elif "syntax error" in err.lower():
            msg = f"SQL syntax error — try rephrasing. Detail: {err}"
        else:
            msg = f"Snowflake query failed: {err}"
        return pd.DataFrame({"Error": [msg]})

    except Exception as e:
        return pd.DataFrame({"Error": [f"Unexpected error: {e}"]})


def execute_write(sql: str, params: tuple = None):
    try:
        conn   = get_snowflake_connection()
        cursor = conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        conn.commit()
        cursor.close()
    except Exception as e:
        pass


def setup_tables():
    create_sql = """
    CREATE TABLE IF NOT EXISTS audit_log (
        id             INTEGER      AUTOINCREMENT PRIMARY KEY,
        timestamp      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
        username       VARCHAR(50),
        role           VARCHAR(20),
        question       TEXT,
        report_context VARCHAR(200),
        sql_query      TEXT,
        rows_returned  INTEGER,
        ai_insight     TEXT,
        status         VARCHAR(20)  DEFAULT 'Success'
    )
    """
    execute_write(create_sql)


def log_audit(user, role, q, report_ctx, sql, rows, insight, status="Success"):
    execute_write(
        """INSERT INTO audit_log
           (timestamp, username, role, question, report_context,
            sql_query, rows_returned, ai_insight, status)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
         user, role, q, report_ctx, sql, rows, insight, status)
    )

# ═══════════════════════════════════════════════════════
# POWER BI METADATA & DAX
# ═══════════════════════════════════════════════════════

@st.cache_data
def load_powerbi_metadata():
    try:
        with open(METADATA_PATH, "r") as f:
            return json.load(f)
    except:
        return {"reports": []}


@st.cache_data
def load_dax_measures():
    try:
        with open(DAX_PATH, "r") as f:
            return json.load(f)
    except:
        return {"measures": [], "governance_rules": [], "business_glossary": {}}


def get_all_reports():
    return load_powerbi_metadata().get("reports", [])


def get_measures_context():
    dax   = load_dax_measures()
    lines = ["APPROVED KPI DEFINITIONS (DAX):"]
    for m in dax.get("measures", []):
        if m.get("approved"):
            lines.append(f"  • {m['name']}: {m['description']}")
            lines.append(f"    DAX: {m['dax']}")
    lines.append("\nGOVERNANCE RULES:")
    for rule in dax.get("governance_rules", []):
        lines.append(f"  • {rule}")
    lines.append("\nBUSINESS GLOSSARY:")
    for term, defn in dax.get("business_glossary", {}).items():
        lines.append(f"  • {term}: {defn}")
    return "\n".join(lines)

# ═══════════════════════════════════════════════════════
# DATABASE SCHEMA (updated for Snowflake dialect)
# ═══════════════════════════════════════════════════════

SCHEMA = """
DATABASE SCHEMA (Snowflake — ALLIED_BANK_DB.PUBLIC):

TABLE ACCOUNT_HOLDERS:
  ACCOUNT_ID      VARCHAR PRIMARY KEY
  FULL_NAME       VARCHAR
  CNIC            VARCHAR UNIQUE
  PHONE           VARCHAR
  EMAIL           VARCHAR
  CITY            VARCHAR  -- values: Karachi/Lahore/Islamabad/Peshawar/Quetta/Multan/Faisalabad/Rawalpindi
  ACCOUNT_TYPE    VARCHAR  -- values: Savings/Current/Fixed Deposit/Salary
  BRANCH          VARCHAR
  BALANCE         FLOAT
  STATUS          VARCHAR  -- values: Active/Inactive/Frozen
  OPENED_DATE     DATE
  RISK_RATING     VARCHAR  -- values: Low/Medium/High

TABLE TRANSACTIONS:
  TXN_ID          INTEGER  AUTOINCREMENT PRIMARY KEY
  ACCOUNT_ID      VARCHAR  (FK → ACCOUNT_HOLDERS)
  TXN_DATE        DATE
  TXN_TYPE        VARCHAR  -- values: Credit/Debit
  CATEGORY        VARCHAR  -- values: Transfer/Utility Bill/Salary/Shopping/Cash Withdrawal/Loan Payment/Insurance/Investment
  AMOUNT          FLOAT
  BALANCE_AFTER   FLOAT
  CHANNEL         VARCHAR  -- values: ATM/Online/Branch/Mobile App/POS
  DESCRIPTION     VARCHAR
  STATUS          VARCHAR  -- values: Success/Failed/Pending

SNOWFLAKE SQL NOTES:
- Use TO_CHAR(date_col, 'YYYY-MM') for month grouping (not strftime)
- Use CURRENT_DATE for today's date (not date('now'))
- Use LIMIT n (same as SQL standard)
- Column names in queries should be UPPERCASE or match schema exactly
- String comparisons are case-sensitive; use ILIKE for case-insensitive
- Use DATEDIFF('month', start_date, end_date) for date math
"""

# ═══════════════════════════════════════════════════════
# AI LAYER
# ═══════════════════════════════════════════════════════

def call_ai(prompt, system):
    if AI_MODE == "ollama":
        r = requests.post(OLLAMA_URL,
            json={"model": OLLAMA_MODEL,
                  "prompt": f"{system}\n\nUser: {prompt}\nAssistant:",
                  "stream": False}, timeout=120)
        return r.json().get("response", "").strip()
    from mistralai import Mistral
    client = Mistral(api_key=MISTRAL_KEY)
    r = client.chat.complete(model=MISTRAL_MODEL,
        messages=[{"role":"system","content":system},
                  {"role":"user","content":prompt}])
    return r.choices[0].message.content.strip()


def gen_sql(question, history, visual_context=""):
    """Generate Snowflake-compatible SQL from natural language."""
    system = f"""You are an expert SQL analyst for Allied Bank.
The database is Snowflake (NOT SQLite — use Snowflake SQL syntax).

{SCHEMA}

{get_measures_context()}

{visual_context if visual_context else ""}

Convert the user question to a valid Snowflake SELECT query.

SNOWFLAKE-SPECIFIC RULES:
- Use TO_CHAR(date_col, 'YYYY-MM') for monthly grouping (NOT strftime)
- Use CURRENT_DATE, CURRENT_TIMESTAMP (NOT date('now'))
- Use ILIKE for case-insensitive string matching
- Use DATEDIFF('year'/'month'/'day', date1, date2) for date differences
- Table and column names are UPPERCASE in Snowflake
- Only SELECT queries. No writes.
- Max 100 rows unless aggregating.
- Use approved DAX measure definitions for KPI calculations.

Return EXACTLY:
SQL: <query>
EXPLANATION: <one sentence plain English>"""

    ctx = "".join(f"{h['role'].upper()}: {h['content']}\n" for h in history[-4:])
    try:
        raw  = call_ai(ctx + "User: " + question, system)
        sm   = re.search(r"SQL:\s*(.*?)(?=EXPLANATION:|$)", raw, re.DOTALL|re.IGNORECASE)
        em   = re.search(r"EXPLANATION:\s*(.*)",            raw, re.DOTALL|re.IGNORECASE)
        sql  = sm.group(1).strip() if sm else ""
        expl = em.group(1).strip() if em else "Query generated."

        sql  = re.sub(r"```(?:sql)?", "", sql, flags=re.IGNORECASE).strip()
        sql  = sql.strip("`").strip().rstrip(";").strip()

        if not sql:
            return {"sql":"","explanation":"Could not extract a valid SQL query.","error":True}
        if any(sql.upper().strip().startswith(k)
               for k in ["INSERT","UPDATE","DELETE","DROP","ALTER","TRUNCATE","MERGE","CREATE"]):
            return {"sql":"","explanation":"Write operations are not allowed.","error":True}
        return {"sql":sql,"explanation":expl,"error":False}

    except Exception as e:
        return {"sql":"","explanation":f"AI error: {e}","error":True}


def explain_visual(visual, report_name):
    """AI explains a Power BI visual using metadata + DAX + live Snowflake data."""
    df = qry(visual["sql_equivalent"])

    system = f"""You are an AI analyst embedded in Allied Bank's Power BI companion system.
Data is live from Snowflake (the production database connected to Power BI).
Use ONLY the approved KPI definitions below.

{get_measures_context()}

Your explanation must:
1. Be 3-5 sentences for a non-technical branch manager
2. Reference specific numbers from the data
3. Highlight any concern based on governance rules (failure rate > 5%, active ratio < 80%)
4. Give one clear recommendation
5. End with: "This explanation is AI-generated analytical assistance only."
"""
    data_str = df.head(15).to_string(index=False) if not df.empty else "No data available"
    prompt = f"""Power BI Report: {report_name}
Visual: {visual['visual_title']} ({visual['visual_type']})
Filters: {', '.join(visual['filters']) if visual['filters'] else 'None'}
Slicers: {', '.join(visual['slicers']) if visual['slicers'] else 'None'}
Measures: {visual['y_axis']}
Description: {visual['description']}

Live data from Snowflake:
{data_str}

Explain this visual to a bank manager."""
    try:
        return call_ai(prompt, system), df
    except Exception as e:
        return f"Could not generate explanation: {e}", df


def gen_insight(question, df, visual_context=""):
    if df.empty:
        return "No data returned."
    system = f"""You are a senior banking analyst at Allied Bank.
Data is sourced live from Snowflake connected to Power BI.
{get_measures_context()}
{visual_context}
Give a 3-4 sentence professional insight using only approved KPI definitions.
Reference specific numbers. Flag any governance concerns.
End with: 'This is AI-generated analytical assistance only.'"""
    try:
        return call_ai(
            f'Question: "{question}"\nData:\n{df.head(15).to_string(index=False)}',
            system)
    except:
        return "Could not generate insight."

# ═══════════════════════════════════════════════════════
# CHART HELPER
# ═══════════════════════════════════════════════════════

def auto_chart(df, question="", visual_type=None):
    if df.empty or len(df.columns) < 2:
        return None
    num = df.select_dtypes(include="number").columns.tolist()
    cat = df.select_dtypes(include="object").columns.tolist()
    q   = (question or "").lower()
    vt  = (visual_type or "").lower()
    try:
        if "pie" in vt or "donut" in vt:
            if cat and num:
                return px.pie(df, names=cat[0], values=num[0],
                              color_discrete_sequence=px.colors.qualitative.Set3)
        if "line" in vt or any(w in q for w in ["trend","monthly","over time"]):
            if num:
                return px.line(df, x=df.columns[0], y=num[0], markers=True,
                               color_discrete_sequence=["#1a3c6e"])
        if "bar" in vt or "column" in vt or any(w in q for w in ["top","highest","lowest","most"]):
            if cat and num:
                return px.bar(df, x=cat[0], y=num[0], color=num[0],
                              color_continuous_scale="Blues")
        if cat and num and len(df) <= 30:
            return px.bar(df, x=cat[0], y=num[0],
                          color_discrete_sequence=["#1a3c6e"])
        if len(num) >= 2:
            return px.scatter(df.head(50), x=num[0], y=num[1])
    except:
        pass
    return None

# ═══════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════

CSS = """<style>
.top-bar{background:linear-gradient(135deg,#1a3c6e,#2e6da4);color:white;
         padding:16px 24px;border-radius:12px;margin-bottom:18px;text-align:center;}
.kpi-card{background:white;border:1px solid #dde4f0;border-radius:10px;
          padding:14px;text-align:center;box-shadow:0 2px 8px rgba(0,0,0,.06);}
.kpi-val{font-size:1.7rem;font-weight:700;color:#1a3c6e;}
.kpi-lbl{font-size:.78rem;color:#777;margin-top:3px;}
.section-hdr{font-size:1rem;font-weight:700;color:#1a3c6e;margin:22px 0 10px;
             border-left:4px solid #2e6da4;padding-left:10px;}
.ai-box{background:#f0f7ff;border:1px solid #b3d1f0;border-radius:10px;
        padding:14px 18px;margin-top:8px;font-size:.9rem;line-height:1.6;color:#1a1a2e;}
.meta-box{background:#f9f9f9;border:1px solid #e0e0e0;border-radius:8px;
          padding:10px 14px;font-size:.8rem;color:#555;font-family:monospace;margin:6px 0;}
.dax-box{background:#1e1e2e;color:#cdd6f4;padding:10px 14px;border-radius:8px;
         font-family:monospace;font-size:.82rem;margin:4px 0;}
.badge-Admin{background:#1a3c6e;color:white;padding:2px 10px;border-radius:20px;font-size:.76rem;}
.badge-Analyst{background:#2e7d32;color:white;padding:2px 10px;border-radius:20px;font-size:.76rem;}
.badge-Viewer{background:#bf360c;color:white;padding:2px 10px;border-radius:20px;font-size:.76rem;}
.api-tag{background:#ff9800;color:white;padding:1px 8px;border-radius:10px;font-size:.72rem;font-weight:600;}
.sf-tag{background:#29b5e8;color:white;padding:1px 8px;border-radius:10px;font-size:.72rem;font-weight:600;}
.login-hdr{background:linear-gradient(135deg,#1a3c6e,#2e6da4);color:white;
           padding:28px;border-radius:14px;text-align:center;margin-bottom:24px;}
</style>"""

# ═══════════════════════════════════════════════════════
# LOGIN
# ═══════════════════════════════════════════════════════

def show_login():
    st.markdown(CSS, unsafe_allow_html=True)
    _, col, _ = st.columns([1, 1.6, 1])
    with col:
        st.markdown(
            '<div class="login-hdr"><h2 style="margin:0">🏦 Allied Bank</h2>'
            '<p style="margin:6px 0 0;opacity:.85">AI Analytics Portal — Secure Login</p>'
            '<p style="margin:4px 0 0;opacity:.7;font-size:.8rem">⚡ Powered by Snowflake</p>'
            '</div>',
            unsafe_allow_html=True)
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.button("Login →", use_container_width=True):
            if u in USERS and USERS[u]["password"] == p:
                st.session_state.update({
                    "logged_in": True, "username": u,
                    "role": USERS[u]["role"], "name": USERS[u]["name"],
                    "messages": [], "chat_history": []
                })
                st.rerun()
            else:
                st.error("Invalid credentials.")


# ═══════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════

def sidebar():
    role = st.session_state.role
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.name}")
        st.markdown(f'<span class="badge-{role}">{role}</span>', unsafe_allow_html=True)
        st.markdown("---")
        nav = st.radio("Navigation",
                       ["🤖 AI Chatbot","📋 Audit Log"],
                       label_visibility="collapsed")
        st.markdown("---")

        sf_db  = SNOWFLAKE_CONFIG["database"]
        sf_sch = SNOWFLAKE_CONFIG["schema"]
        ai_lbl = "🟢 Ollama (On-Prem)" if AI_MODE == "ollama" else "🔵 Mistral Cloud"

        if st.button("🗑️ Clear Chat", use_container_width=True):
            st.session_state.messages    = []
            st.session_state.chat_history = []
            st.rerun()
        if st.button("🚪 Logout", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
    return nav

# ═══════════════════════════════════════════════════════
# PAGE 2: AI CHATBOT
# ═══════════════════════════════════════════════════════

def page_chatbot():
    role  = st.session_state.role
    perms = PERMS[role]
    meta  = load_powerbi_metadata()

    st.markdown('<div class="section-hdr">🤖 AI Chatbot — Power BI Companion (Snowflake)</div>',
                unsafe_allow_html=True)
    st.caption("Questions answered using Power BI  + live Snowflake data.")

    report_options    = ["(general question)"] + [r["report_name"] for r in meta["reports"]]
    selected_report_name = st.selectbox("Report context", report_options, label_visibility="collapsed")

    visual_context    = ""
    report_context_str = ""

    if selected_report_name != "None (general question)":
        selected_report = next((r for r in meta["reports"]
                                if r["report_name"] == selected_report_name), None)
        if selected_report:
            lines = [f"USER IS CURRENTLY VIEWING: {selected_report['report_name']}",
                     f"Domain: {selected_report['domain']}",
                     f"Description: {selected_report['description']}",
                     "Visuals in this report:"]
            for page in selected_report["pages"]:
                for v in page["visuals"]:
                    lines.append(f"  • {v['visual_title']} ({v['visual_type']}) — {v['description']}")
                    lines.append(f"    Filters: {', '.join(v['filters']) if v['filters'] else 'None'}")
            visual_context     = "\n".join(lines)
            report_context_str = selected_report["report_id"]
            st.success(f"✅ AI context: **{selected_report_name}** + ❄️ Snowflake live data")

    with st.expander("💡 Sample Questions"):
        samples = [
            "Why is Karachi performing better than other cities?",
            "Which branch has the most frozen accounts?",
            "What is causing the high debit volume?",
            "Which channel has the most failed transactions?",
            "Show me the monthly trend for the last year",
            "Which accounts are high risk with balance over 100000?",
            "What is the active account ratio?",
            "Compare credit vs debit by month",
            "Which city has the highest average balance?",
            "What is the net flow this year?",
        ]
        cols = st.columns(2)
        for i, s in enumerate(samples):
            with cols[i % 2]:
                if st.button(f"▶ {s}", key=f"s{i}", use_container_width=True):
                    st.session_state.prefill = s

    if "messages"      not in st.session_state: st.session_state.messages     = []
    if "chat_history"  not in st.session_state: st.session_state.chat_history  = []

    for i, msg in enumerate(st.session_state.messages):
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.write(msg["content"])
        else:
            with st.chat_message("assistant"):
                if msg.get("report_context"):
                    st.markdown(
                        # f'<span class="api-tag">Power BI</span> '
                        # f'<span class="sf-tag">❄️ Snowflake</span> '
                        f'Report: **{msg["report_context"]}**',
                        unsafe_allow_html=True)
                # ✅ SQL code block removed — no longer displayed in chat
                st.markdown(f"**{msg.get('explanation','')}**")
                if "df" in msg and not msg["df"].empty:
                    st.dataframe(msg["df"], use_container_width=True)
                    if perms["can_export"]:
                        st.download_button("⬇️ Export CSV",
                            msg["df"].to_csv(index=False),
                            f"result_{i}.csv", "text/csv", key=f"dl{i}")
                if msg.get("fig"):
                    st.plotly_chart(msg["fig"], use_container_width=True)
                if msg.get("insight"):
                    st.info(f"💡 **AI Insight:** {msg['insight']}")

    prefill    = st.session_state.pop("prefill", "")
    user_input = st.chat_input("Ask about your Power BI reports...")
    if prefill and not user_input:
        user_input = prefill

    if user_input:
        st.session_state.messages.append({"role":"user","content":user_input})
        st.session_state.chat_history.append({"role":"user","content":user_input})

        with st.spinner("🤖 AI querying ..."):
            result = gen_sql(user_input, st.session_state.chat_history, visual_context)

        if result["error"] or not result["sql"]:
            log_audit(st.session_state.username, role, user_input,
                      report_context_str, "", 0, result["explanation"], "Failed")
            st.session_state.messages.append({
                "role":"assistant","sql":"","explanation":result["explanation"],
                "df":pd.DataFrame(),"fig":None,"insight":None,"report_context":""})
        else:
            df      = qry(result["sql"])
            fig     = auto_chart(df, user_input)
            insight = gen_insight(user_input, df, visual_context) if not df.empty else None
            log_audit(st.session_state.username, role, user_input,
                      report_context_str, result["sql"], len(df), insight or "")
            st.session_state.chat_history.append({
                "role":"assistant",
                "content": f"SQL: {result['sql']}\n{result['explanation']}"})
            st.session_state.messages.append({
                "role":"assistant","sql":result["sql"],"explanation":result["explanation"],
                "df":df,"fig":fig,"insight":insight,
                "report_context": selected_report_name
                    if selected_report_name != "None (general question)" else ""})
        st.rerun()

# ═══════════════════════════════════════════════════════
# PAGE 3: DAX & METADATA VIEWER
# ═══════════════════════════════════════════════════════

def page_metadata():
    st.markdown('<div class="section-hdr">📐 Power BI Metadata & DAX Measures</div>',
                unsafe_allow_html=True)
    st.caption("Structured inputs the AI receives from the Power BI + Snowflake integration layer.")

    tab1, tab2, tab3 = st.tabs(["📊 Report Metadata","📐 DAX Measures","📖 Business Glossary"])

    with tab1:
        meta = load_powerbi_metadata()
        st.markdown(f"**Workspace:** {meta.get('workspace','')} &nbsp;|&nbsp; "
                    f"**Last Updated:** {meta.get('last_updated','')}")
        for report in meta["reports"]:
            with st.expander(f"📁 {report['report_name']} — {report['report_id']}"):
                st.markdown(f"**Domain:** {report['domain']}")
                st.markdown(f"**Description:** {report['description']}")
                for page in report["pages"]:
                    st.markdown(f"**Page: {page['page_name']}**")
                    for v in page["visuals"]:
                        st.markdown(f"""
<div class="meta-box">
<b>{v['visual_title']}</b> ({v['visual_id']}) — {v['visual_type']}<br>
X: {v['x_axis']} &nbsp;|&nbsp; Y: {v['y_axis']}<br>
Filters: {', '.join(v['filters']) if v['filters'] else 'None'}
&nbsp;|&nbsp; Slicers: {', '.join(v['slicers']) if v['slicers'] else 'None'}<br>
{v['description']}
</div>""", unsafe_allow_html=True)

    with tab2:
        dax = load_dax_measures()
        st.markdown(f"**Dataset:** {dax.get('dataset_name','')} &nbsp;|&nbsp; "
                    f"**Approved by:** {dax.get('approved_by','')}")
        for m in dax["measures"]:
            badge = "✅ Approved" if m.get("approved") else "❌ Not Approved"
            with st.expander(f"📐 {m['name']} — {m['measure_id']} {badge}"):
                st.markdown(f"**Description:** {m['description']}")
                st.markdown(f"**Unit:** {m['unit']} &nbsp;|&nbsp; **Owner:** {m['owner']}")
                st.markdown(f"**Used in:** {', '.join(m['used_in_reports'])}")
                st.markdown(f'<div class="dax-box">{m["dax"]}</div>', unsafe_allow_html=True)
        st.markdown("**Governance Rules:**")
        for rule in dax.get("governance_rules", []):
            st.markdown(f"• {rule}")

    with tab3:
        dax      = load_dax_measures()
        glossary = dax.get("business_glossary", {})
        df       = pd.DataFrame(list(glossary.items()), columns=["Term","Definition"])
        st.dataframe(df, use_container_width=True, hide_index=True)

# ═══════════════════════════════════════════════════════
# PAGE 4: AUDIT LOG
# ═══════════════════════════════════════════════════════

def page_audit():
    if not PERMS[st.session_state.role]["can_audit"]:
        st.error("🔒 Admin access required."); return

    st.markdown('<div class="section-hdr">📋 Audit Log — Compliance & Governance</div>',
                unsafe_allow_html=True)
    st.caption("Every AI interaction logged in Snowflake with report context.")

    df = qry("SELECT * FROM AUDIT_LOG ORDER BY ID DESC LIMIT 500")
    if df.empty:
        st.info("No audit records yet."); return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Queries",  len(df))
    c2.metric("Unique Users",   df["username"].nunique() if "username" in df else 0)
    c3.metric("Success Rate",
              f"{(df['status']=='Success').mean()*100:.0f}%" if "status" in df else "N/A")
    c4.metric("Today",
              len(df[df["timestamp"].astype(str).str.startswith(
                  datetime.now().strftime("%Y-%m-%d"))]) if "timestamp" in df else 0)

    uf  = st.selectbox("Filter by User",
                        ["All"] + df["username"].unique().tolist() if "username" in df else ["All"])
    fd  = df if uf == "All" else df[df["username"] == uf]

    show_cols = [c for c in ["timestamp","username","role","question",
                              "report_context","rows_returned","status"]
                 if c in fd.columns]
    st.dataframe(fd[show_cols], use_container_width=True)

    if "username" in df:
        fig = px.bar(df.groupby("username").size().reset_index(name="q"),
                     x="username", y="q", title="Queries per User",
                     color_discrete_sequence=["#1a3c6e"])
        st.plotly_chart(fig, use_container_width=True)

    st.download_button("⬇️ Download Audit Log",
                       fd.to_csv(index=False), "audit_log.csv", "text/csv")

# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════

def main():
    st.set_page_config(page_title="Allied Bank AI", page_icon="🏦",
                       layout="wide", initial_sidebar_state="expanded")
    setup_tables()
    st.markdown(CSS, unsafe_allow_html=True)

    if not st.session_state.get("logged_in"):
        show_login(); return

    ai_lbl = "🟢 On-Prem" if AI_MODE == "ollama" else "🔵 Cloud"
    sf_db  = SNOWFLAKE_CONFIG["database"]
    st.markdown(f"""<div class="top-bar">
        <h1 style="margin:0;font-size:1.6rem">🏦 Allied Bank — AI Analytics Platform</h1>
        <p style="margin:5px 0 0;opacity:.88;font-size:.84rem">
            Power BI Integration &nbsp;|&nbsp;
            ❄️ Snowflake: <b>{sf_db}</b> &nbsp;|&nbsp;
            AI: {ai_lbl} &nbsp;|&nbsp;
            User: <b>{st.session_state.name}</b> &nbsp;|&nbsp;
            Role: <b>{st.session_state.role}</b>
        </p></div>""", unsafe_allow_html=True)

    nav = sidebar()

    if nav == "🤖 AI Chatbot":       page_chatbot()
    elif nav == "📐 DAX & Metadata": page_metadata()
    elif nav == "📋 Audit Log":      page_audit()


if __name__ == "__main__":
    main()