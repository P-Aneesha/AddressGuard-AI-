import io
import csv
import json
import qrcode
from barcode import Code128
from barcode.writer import ImageWriter
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from xml.sax.saxutils import escape

PARSED_FIELDS = ["name", "phone", "house_number", "flat_unit", "building", "street",
                 "landmark", "locality", "city", "district", "state", "pin_code"]


def _p(text, style):
    """ReportLab parses Paragraph text as markup; escape user-supplied text so
    characters such as '&' or '<' are printed instead of breaking the PDF."""
    return Paragraph(escape(str(text if text is not None else "")), style)


def _cell(value):
    return str(value) if value not in (None, "") else "-"


def _csv_safe(value):
    """Neutralise spreadsheet formula injection (=, +, -, @ at the start)."""
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def generate_pdf(v: dict) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=20*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    elems = [Paragraph("AddressGuard AI — Validation Report", styles["Title"]), Spacer(1, 8)]

    meta = [
        ["Validation ID", v["validation_id"]], ["Created (UTC)", _cell(v.get("created_at"))],
        ["Decision", v["decision"]], ["Risk Level", v["risk_level"]], ["Confidence", f'{v["confidence"]}%'],
    ]
    elems.append(Table(meta, colWidths=[120, 340], style=_tbl_style()))
    elems.append(Spacer(1, 10))

    elems.append(Paragraph("Original Address", styles["Heading3"]))
    elems.append(_p(v["raw_address"], styles["Normal"]))
    if v.get("decision_description"):
        elems.append(Spacer(1, 6))
        elems.append(_p(f'{v["decision"]}: {v["decision_description"]}', styles["Normal"]))
    elems.append(Spacer(1, 8))

    elems.append(Paragraph("Parsed Fields", styles["Heading3"]))
    pd = v.get("parsed_data") or {}
    rows = [["Field", "Value"]] + [[k.replace("_", " ").title(), _cell(pd.get(k))] for k in PARSED_FIELDS]
    elems.append(Table(rows, colWidths=[140, 320], style=_tbl_style(header=True)))
    elems.append(Spacer(1, 8))

    if v.get("corrections"):
        elems.append(Paragraph("Correction Suggestions", styles["Heading3"]))
        crows = [["Field", "Original", "Suggested", "Confidence"]] + [
            [_cell(c.get("field")), _cell(c.get("original")), _cell(c.get("suggested")), f'{c.get("confidence", "-")}%']
            for c in v["corrections"]]
        elems.append(Table(crows, colWidths=[90, 150, 150, 70], style=_tbl_style(header=True)))
        elems.append(Spacer(1, 8))

    exp = v.get("explainability") or {}
    if exp.get("geo_checks"):
        elems.append(Paragraph("Geographic Checks", styles["Heading3"]))
        grows = [["Check", "Result"]] + [[k.replace("_", " ").title(), _cell(val)] for k, val in exp["geo_checks"].items()]
        elems.append(Table(grows, colWidths=[200, 260], style=_tbl_style(header=True)))
        elems.append(Spacer(1, 8))

    elems.append(Paragraph("Explainability", styles["Heading3"]))
    for line in exp.get("confidence_explanation", []):
        elems.append(_p(line, styles["Normal"]))
    for line in exp.get("risk_explanation", []):
        elems.append(_p("Risk: " + str(line), styles["Normal"]))
    for line in exp.get("decision_explanation", []):
        elems.append(_p("Decision: " + str(line), styles["Normal"]))
    for line in exp.get("limitations", []):
        elems.append(_p("Limitation: " + str(line), styles["Normal"]))

    doc.build(elems)
    buf.seek(0)
    return buf


def _tbl_style(header=False):
    style = [("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 8),
             ("VALIGN", (0, 0), (-1, -1), "TOP")]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4f8cff")),
                   ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                   ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    return TableStyle(style)


def generate_csv(v: dict) -> io.BytesIO:
    buf = io.StringIO()
    w = csv.writer(buf)

    def row(*values):
        w.writerow([_csv_safe(x) for x in values])

    row("Validation ID", v["validation_id"])
    row("Created (UTC)", v.get("created_at") or "")
    row("Raw Address", v["raw_address"])
    row("Confidence", v["confidence"])
    row("Risk Level", v["risk_level"])
    row("Decision", v["decision"])
    if v.get("decision_description"):
        row("Decision Meaning", v["decision_description"])
    for reason in (v.get("explainability") or {}).get("decision_explanation", []):
        row("Decision Reason", reason)
    w.writerow([])
    row("Field", "Value")
    parsed = v.get("parsed_data") or {}
    for k in PARSED_FIELDS:
        row(k, parsed.get(k, ""))
    w.writerow([])
    row("Correction Field", "Original", "Suggested", "Confidence")
    for c in v.get("corrections", []) or []:
        row(c.get("field", ""), c.get("original", ""), c.get("suggested", ""), c.get("confidence", ""))
    # UTF-8 with BOM so spreadsheet tools display non-ASCII text correctly.
    out = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    out.seek(0)
    return out


def generate_qr(v: dict) -> io.BytesIO:
    payload = json.dumps({"id": v["validation_id"], "decision": v["decision"], "confidence": v["confidence"]})
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def generate_barcode(v: dict) -> io.BytesIO:
    buf = io.BytesIO()
    code = Code128(v["validation_id"], writer=ImageWriter())
    code.write(buf, options={"write_text": True, "module_height": 10})
    buf.seek(0)
    return buf


def build_google_maps_url(latitude=None, longitude=None, address="") -> str:
    """Build a Google Maps destination URL from verified coordinates or address."""
    from urllib.parse import quote_plus

    if latitude not in (None, "") and longitude not in (None, ""):
        return f"https://www.google.com/maps/dir/?api=1&destination={quote_plus(str(latitude) + ',' + str(longitude))}"

    clean_address = " ".join(str(address or "").split())
    if clean_address:
        return f"https://www.google.com/maps/search/?api=1&query={quote_plus(clean_address)}"
    return ""


def generate_delivery_qr(maps_url: str) -> io.BytesIO:
    """Generate a QR that opens the verified delivery destination in Google Maps."""
    if not maps_url:
        raise ValueError("Google Maps URL is required")
    img = qrcode.make(maps_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf
