"""
pbix_parser.py — Allied Bank Power BI Auto-Configurator
========================================================
Parses an uploaded .pbix file and extracts:
  1. DAX measures → dax_measures.json
  2. Report layout / visuals → powerbi_metadata.json

A .pbix is a ZIP archive. Key internal files:
  DataModel          → compressed model (tables, columns, DAX measures)
  Report/Layout      → JSON describing every page and visual
  [Content_Types].xml → confirms it's a valid .pbix
"""

import zipfile
import json
import re
import io
import struct
from datetime import date

# ─── Validate the uploaded file is actually a .pbix ──────────────────────
def is_valid_pbix(file_bytes):
    """Check the file is a ZIP and contains Power BI internal files."""
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
            names = z.namelist()
            # Every .pbix has at least one of these
            required = ["[Content_Types].xml", "DataModel", "Report/Layout"]
            return any(r in names for r in required)
    except Exception:
        return False


# ─── Read all files from the .pbix ZIP ───────────────────────────────────
def read_pbix_contents(file_bytes):
    """Open the .pbix ZIP and read all internal files as text."""
    contents = {}
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as z:
        for name in z.namelist():
            try:
                raw = z.read(name)
                # Try UTF-8 first, fall back to latin-1
                try:
                    contents[name] = raw.decode("utf-8", errors="ignore")
                except Exception:
                    contents[name] = raw.decode("latin-1", errors="ignore")
            except Exception as e:
                contents[name] = ""
    return contents


# ─── Extract DAX measures from DataModel text ─────────────────────────────
def extract_dax_measures(contents):
    """
    The DataModel file is binary/compressed but DAX measure text is
    still readable as UTF-8 strings embedded within it.
    We search for all known DAX measure patterns.
    """
    all_text = "\n".join(v for v in contents.values() if isinstance(v, str))
    measures = []
    seen = set()

    # ── Pattern 1: JSON-style "expression" fields (most common in modern .pbix)
    # Looks for: "name": "MeasureName" ... "expression": "DAX formula"
    json_blocks = re.finditer(
        r'"name"\s*:\s*"([^"]{2,80})"\s*(?:,[^}]{0,300}?)"expression"\s*:\s*"([^"]{5,1000})"',
        all_text, re.IGNORECASE | re.DOTALL
    )
    for m in json_blocks:
        name    = m.group(1).strip()
        formula = m.group(2).strip().replace("\\n", "\n").replace("\\t", " ")
        if _is_valid_measure(name, formula) and name not in seen:
            seen.add(name)
            measures.append(_build_measure(name, formula, len(measures)))

    # ── Pattern 2: Classic DAX format  [Name] = CALCULATE(...)
    classic = re.finditer(
        r'\[([A-Za-z][^\]]{2,60})\]\s*=\s*((?:CALCULATE|SUM|DIVIDE|COUNT|AVERAGE|IF|SUMX|COUNTROWS|FILTER|SWITCH)[^\n]{10,300})',
        all_text, re.IGNORECASE | re.MULTILINE
    )
    for m in classic:
        name    = m.group(1).strip()
        formula = m.group(2).strip()
        if _is_valid_measure(name, formula) and name not in seen:
            seen.add(name)
            measures.append(_build_measure(name, formula, len(measures)))

    # ── Pattern 3: Quoted name + := assignment (tabular model format)
    tabular = re.finditer(
        r'"([A-Za-z][^"]{2,60})"\s*:=\s*((?:CALCULATE|SUM|DIVIDE|COUNT|AVERAGE|SUMX|COUNTROWS)[^\n]{10,200})',
        all_text, re.IGNORECASE | re.MULTILINE
    )
    for m in tabular:
        name    = m.group(1).strip()
        formula = m.group(2).strip()
        if _is_valid_measure(name, formula) and name not in seen:
            seen.add(name)
            measures.append(_build_measure(name, formula, len(measures)))

    return measures


def _is_valid_measure(name, formula):
    """Filter out garbage matches — only keep real DAX measures."""
    bad_keywords = ["http", "xmlns", "Content-Type", "application/", "rels", ".xml", "pbi:", "QueryBinding"]
    if any(b.lower() in name.lower() for b in bad_keywords): return False
    if any(b.lower() in formula.lower() for b in bad_keywords): return False
    if len(name) < 2 or len(name) > 80: return False
    if len(formula) < 5: return False
    # Must contain at least one DAX function
    dax_functions = ["SUM(", "COUNT(", "CALCULATE(", "DIVIDE(", "AVERAGE(", "IF(", "SUMX(", "FILTER(", "ALL("]
    return any(fn in formula.upper() for fn in dax_functions)


def _build_measure(name, formula, index):
    """Build a measure dict in our dax_measures.json format."""
    f_up = formula.upper()
    # Auto-detect unit
    if "DIVIDE" in f_up or any(w in name.upper() for w in ["RATIO", "RATE", "%", "PCT", "PERCENT"]):
        unit = "Percentage"
    elif any(w in f_up for w in ["SUM(", "AVERAGE(", "AMOUNT", "BALANCE", "MIN(", "MAX("]):
        unit = "PKR"
    else:
        unit = "Count"

    return {
        "measure_id": f"KPI-{index+1:03d}",
        "name": name,
        "description": f"DAX measure extracted from Power BI: {name}",
        "dax": f"{name} = {formula}",
        "unit": unit,
        "owner": "Auto-extracted — confirm with data team",
        "approved": True,
        "used_in_reports": ["RPT-001"]
    }


# ─── Extract tables and columns from DataModel ───────────────────────────
def extract_schema(contents):
    """Extract table and column names from readable portions of DataModel."""
    all_text = "\n".join(v for v in contents.values() if isinstance(v, str))
    schema = {}

    # Look for table name patterns
    table_matches = re.finditer(r'"tableName"\s*:\s*"([A-Za-z][A-Za-z0-9 _]{1,60})"', all_text)
    for m in table_matches:
        tname = m.group(1).strip()
        if not tname.startswith("$") and tname not in schema:
            schema[tname] = []

    # Look for column patterns near table names
    col_matches = re.finditer(r'"columnName"\s*:\s*"([A-Za-z][A-Za-z0-9 _]{1,60})"', all_text)
    for m in col_matches:
        col = m.group(1).strip()
        if schema:
            first_table = list(schema.keys())[0]
            if col not in schema[first_table]:
                schema[first_table].append(col)

    return schema


# ─── Extract visual layout from Report/Layout ─────────────────────────────
def extract_visuals(contents):
    """
    Report/Layout is a proper JSON file inside the .pbix.
    It describes every page and every visual with:
      - displayName (page title)
      - visualContainers (list of visuals per page)
      - Each visual has: config (type, title, field bindings), filters
    """
    layout_text = contents.get("Report/Layout", "")
    if not layout_text:
        return []

    try:
        layout = json.loads(layout_text)
    except Exception:
        # Sometimes it's double-encoded — try stripping BOM or extra chars
        try:
            layout = json.loads(layout_text.lstrip("\ufeff"))
        except Exception:
            return []

    pages_out = []
    sections  = layout.get("sections", [])

    for section in sections:
        page_name  = section.get("displayName", section.get("name", "Page"))
        visuals_out = []
        containers  = section.get("visualContainers", [])

        for i, vc in enumerate(containers):
            # config is a JSON string inside the JSON
            try:
                config = json.loads(vc.get("config", "{}"))
            except Exception:
                config = {}

            single = config.get("singleVisual", {})
            vtype  = single.get("visualType", "")

            # Skip non-data visuals
            skip_types = {"slicer", "basicShape", "textbox", "image", "actionButton", "shape"}
            if vtype in skip_types or not vtype:
                continue

            # ── Extract title ──────────────────────────────────────
            title = ""
            title_objs = single.get("vcObjects", {}).get("title", [])
            if title_objs:
                title = (title_objs[0]
                         .get("properties", {})
                         .get("text", {})
                         .get("expr", {})
                         .get("Literal", {})
                         .get("Value", ""))
                title = title.strip("'\"")
            if not title:
                title = f"{page_name} — Visual {i+1}"

            # ── Extract field bindings (X/Y axis) ─────────────────
            projections = (single.get("prototypeQuery", {})
                                 .get("Select", []))
            fields = []
            for proj in projections:
                fname = ""
                if "Column" in proj:
                    fname = proj["Column"].get("Property", "")
                elif "Measure" in proj:
                    fname = proj["Measure"].get("Property", "")
                elif "Aggregation" in proj:
                    agg   = proj["Aggregation"]
                    inner = (agg.get("Expression", {})
                                .get("Column", {})
                                .get("Property", ""))
                    fn    = {0:"SUM",1:"AVG",2:"MIN",3:"MAX",4:"COUNT"}.get(agg.get("Function",0),"AGG")
                    fname = f"{fn}({inner})" if inner else ""
                if fname:
                    fields.append(fname)

            x_axis = fields[0] if len(fields) > 0 else "Category"
            y_axis = fields[1] if len(fields) > 1 else "Value"

            # ── Extract active filters ─────────────────────────────
            filter_names = []
            try:
                filters_raw = json.loads(vc.get("filters", "[]"))
                for f in filters_raw:
                    where = f.get("filter", {}).get("Where", [])
                    for cond in where:
                        col = (cond.get("Condition", {})
                                   .get("In", {})
                                   .get("Expressions", [{}])[0]
                                   .get("Column", {})
                                   .get("Property", ""))
                        if col:
                            filter_names.append(col)
            except Exception:
                pass

            # ── Map visual type to friendly name ───────────────────
            type_map = {
                "barChart":       "Bar Chart",
                "clusteredBarChart": "Bar Chart",
                "columnChart":    "Bar Chart",
                "clusteredColumnChart": "Bar Chart",
                "lineChart":      "Line Chart",
                "areaChart":      "Line Chart",
                "lineStackedColumnComboChart": "Line Chart",
                "pieChart":       "Pie Chart",
                "donutChart":     "Pie Chart",
                "tableEx":        "Table",
                "matrix":         "Table",
                "card":           "KPI Card",
                "multiRowCard":   "KPI Card",
                "scatterChart":   "Scatter Chart",
                "gauge":          "Gauge",
                "treemap":        "Treemap",
                "funnel":         "Funnel",
                "waterfallChart": "Waterfall",
                "ribbonChart":    "Bar Chart",
                "map":            "Map",
                "filledMap":      "Map",
            }
            friendly_type = type_map.get(vtype, vtype.replace("Chart", " Chart").title())

            # ── Build smart SQL from field names ───────────────────
            sql = _build_sql(x_axis, y_axis, friendly_type, filter_names)

            visuals_out.append({
                "visual_id":    f"V-{page_name[:3].upper()}-{i+1:02d}",
                "visual_title": title,
                "visual_type":  friendly_type,
                "x_axis":       x_axis,
                "y_axis":       y_axis,
                "filters":      filter_names,
                "slicers":      [],
                "description":  f"Auto-extracted from Power BI: {title} ({friendly_type})",
                "sql_equivalent": sql
            })

        if visuals_out:
            pages_out.append({
                "page_name": page_name,
                "visuals":   visuals_out
            })

    return pages_out


def _build_sql(x_axis, y_axis, chart_type, filters):
    """
    Map Power BI field names → SQLite query for allied_bank.db.
    Handles known Allied Bank fields automatically.
    Unknown fields get a clear TODO template.
    """
    # Allied Bank field → (table, column) mapping
    field_map = {
        "city":         ("account_holders", "city"),
        "branch":       ("account_holders", "branch"),
        "account type": ("account_holders", "account_type"),
        "accounttype":  ("account_holders", "account_type"),
        "status":       ("account_holders", "status"),
        "risk rating":  ("account_holders", "risk_rating"),
        "riskrating":   ("account_holders", "risk_rating"),
        "txn type":     ("transactions", "txn_type"),
        "txntype":      ("transactions", "txn_type"),
        "category":     ("transactions", "category"),
        "channel":      ("transactions", "channel"),
        "txn date":     ("transactions", "txn_date"),
        "txndate":      ("transactions", "txn_date"),
        "balance":      ("account_holders", "balance"),
        "amount":       ("transactions", "amount"),
        "month":        ("transactions", "strftime('%Y-%m', txn_date)"),
    }

    xk = x_axis.lower().replace(" ", "").replace("_", "")
    yk = y_axis.lower().replace(" ", "").replace("_", "")

    x_info = field_map.get(xk) or field_map.get(x_axis.lower())
    y_info = field_map.get(yk) or field_map.get(y_axis.lower())

    if x_info and y_info and x_info[0] == y_info[0]:
        table = x_info[0]
        xc, yc = x_info[1], y_info[1]
        if "COUNT" in y_axis.upper() or chart_type == "KPI Card":
            return f"SELECT {xc}, COUNT(*) AS count FROM {table} GROUP BY {xc} ORDER BY count DESC LIMIT 20"
        return f"SELECT {xc}, ROUND(SUM({yc}), 2) AS total FROM {table} GROUP BY {xc} ORDER BY total DESC LIMIT 20"

    if x_info:
        table, xc = x_info
        return f"SELECT {xc}, COUNT(*) AS count FROM {table} GROUP BY {xc} ORDER BY count DESC LIMIT 20"

    # Fallback template
    return f"-- TODO: map '{x_axis}' vs '{y_axis}' to your SQLite tables\nSELECT '{x_axis}' AS category, 0 AS value"


# ─── Main parse function called by Streamlit ─────────────────────────────
def parse_pbix(file_bytes, report_name="Allied Bank Report"):
    """
    Master function. Takes raw bytes of uploaded .pbix file.
    Returns (metadata_dict, dax_dict, summary_dict).
    """
    summary = {
        "pages":    0,
        "visuals":  0,
        "measures": 0,
        "warnings": []
    }

    contents = read_pbix_contents(file_bytes)

    # ── Extract DAX measures ──────────────────────────────────────
    measures = extract_dax_measures(contents)
    summary["measures"] = len(measures)
    if not measures:
        summary["warnings"].append(
            "No DAX measures found in DataModel. The DataModel may be compressed "
            "in a format this parser cannot read. You can add measures manually in dax_measures.json."
        )

    # ── Build governance rules ────────────────────────────────────
    governance = [
        "All AI-generated insights must end with: 'This is AI-generated analytical assistance only.'",
        "Only Approved measures (approved: true) may be used in AI explanations",
        "Analysts and Admins only may export data — Viewers are read-only",
    ]
    for m in measures:
        if m["unit"] == "Percentage":
            governance.append(f"{m['name']}: verify threshold with Risk & Compliance team")

    dax_dict = {
        "dataset_name": f"Allied Bank — {report_name}",
        "approved_by":  "Pending review",
        "last_updated": date.today().isoformat(),
        "_note": "Auto-extracted from uploaded .pbix file. Review DAX formulas before use.",
        "measures":         measures,
        "governance_rules": governance,
        "business_glossary": {
            "Active Account": "An account with status = Active",
            "Net Flow":       "Total credits minus total debits",
            "Failure Rate":   "Percentage of failed transactions",
            "High Risk":      "Account flagged by risk team based on KYC or transaction patterns",
            "DAX":            "Data Analysis Expressions — Power BI formula language",
            "KPI":            "Key Performance Indicator"
        }
    }

    # ── Extract visual layout ─────────────────────────────────────
    pages = extract_visuals(contents)
    summary["pages"]   = len(pages)
    summary["visuals"] = sum(len(p["visuals"]) for p in pages)

    if not pages:
        summary["warnings"].append(
            "Could not read Report/Layout. A default template page was created. "
            "Please update visual titles and sql_equivalent fields manually."
        )
        pages = [{
            "page_name": "Overview",
            "visuals": [{
                "visual_id":    "V-001",
                "visual_title": "Total Deposits by City",
                "visual_type":  "Bar Chart",
                "x_axis":       "city",
                "y_axis":       "balance",
                "filters":      [],
                "slicers":      [],
                "description":  "Template visual — update to match your report",
                "sql_equivalent": "SELECT city, ROUND(SUM(balance),2) AS total FROM account_holders WHERE status='Active' GROUP BY city ORDER BY total DESC"
            }]
        }]

    metadata_dict = {
        "workspace":    "Allied Bank — Power BI Workspace",
        "last_updated": date.today().isoformat(),
        "_note": "Auto-extracted from uploaded .pbix file.",
        "reports": [{
            "report_id":   "RPT-001",
            "report_name": report_name,
            "domain":      "Banking Analytics",
            "description": f"Extracted from {report_name}.pbix on {date.today().isoformat()}",
            "pages":       pages
        }]
    }

    return metadata_dict, dax_dict, summary
