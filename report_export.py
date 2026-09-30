from __future__ import annotations

import os
import tempfile
from datetime import datetime

import functools as _functools

# openpyxl and reportlab take a noticeable time to load. They are loaded the first time an export is
# made (not when the program opens), which makes opening Saber Accounting faster.
_LIBRARIES_LOADED = False


def _load_libraries():
    global _LIBRARIES_LOADED, Workbook, Alignment, Font, PatternFill, get_column_letter, colors, A4, landscape
    global getSampleStyleSheet, mm, Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    if _LIBRARIES_LOADED: return
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    _LIBRARIES_LOADED = True

NAVY = "071B2E"

# ---------------------------------------------------------------- Arabic in PDF
# Amiri (SIL Open Font License, assets/fonts/Amiri-OFL.txt) is used for any text that contains Arabic.
import re as _re
import sys as _sys
from pathlib import Path as _Path
from xml.sax.saxutils import escape as _escape

_ARABIC = _re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
_FONTS = {"ready": None}


def _font_folder():
    base = _Path(getattr(_sys, "_MEIPASS", _Path(__file__).resolve().parent))
    for folder in (base / "assets" / "fonts", base / "assets" / "Fonts", base / "Assets" / "fonts"):
        if folder.is_dir(): return folder
    return base / "assets" / "fonts"


def arabic_fonts():
    """Register Amiri once; returns (regular, bold) or (None, None) when the font files are missing."""
    if _FONTS["ready"] is None:
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            folder = _font_folder()
            pdfmetrics.registerFont(TTFont("Amiri", str(folder / "Amiri-Regular.ttf")))
            pdfmetrics.registerFont(TTFont("Amiri-Bold", str(folder / "Amiri-Bold.ttf")))
            _FONTS["ready"] = ("Amiri", "Amiri-Bold")
        except Exception:
            _FONTS["ready"] = (None, None)
    return _FONTS["ready"]


def has_arabic(text):
    return bool(_ARABIC.search(str(text or "")))


def shape_arabic(text):
    """Join the Arabic letters and put the line in visual (right-to-left) order for the PDF."""
    text = str(text or "")
    if not has_arabic(text): return text
    try:
        import arabic_reshaper
        shaped = arabic_reshaper.reshape(text)
    except Exception:
        shaped = text
    try:
        from bidi.algorithm import get_display
        return get_display(shaped)
    except Exception:
        return " ".join(reversed(shaped.split(" ")))


def pdf_paragraph(text, style, bold=False):
    """A Paragraph that renders Arabic with the Arabic font, and anything else with the style's font."""
    regular, bold_font = arabic_fonts()
    if has_arabic(text) and regular:
        from reportlab.lib.styles import ParagraphStyle
        size = style.fontSize * 1.2
        arabic_style = ParagraphStyle(f"ar-{style.name}-{bold}", parent=style, fontName=bold_font if bold else regular, fontSize=size, leading=size * 1.4,
                                      alignment=2 if not _re.search(r"[A-Za-z]{3}", str(text)) else style.alignment)
        return Paragraph(_escape(shape_arabic(text)), arabic_style)
    return Paragraph(_escape(str(text or "")), style)

def export_excel(path, title, headers, rows):
    wb = Workbook(); ws = wb.active; ws.title = title[:31]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    cell = ws.cell(1, 1, title); cell.font = Font(size=16, bold=True, color="FFFFFF")
    cell.fill = PatternFill("solid", fgColor=NAVY); cell.alignment = Alignment(horizontal="center")
    ws.cell(2, 1, f"Generated: {datetime.now():%d-%m-%Y %H:%M}")
    for c, header in enumerate(headers, 1):
        h = ws.cell(4, c, header); h.font = Font(bold=True, color="FFFFFF")
        h.fill = PatternFill("solid", fgColor=NAVY); h.alignment = Alignment(horizontal="center")
    for r, values in enumerate(rows, 5):
        for c, value in enumerate(values, 1): ws.cell(r, c, value)
    for index, column in enumerate(ws.columns, 1):
        width = min(35, max(12, max(len(str(c.value or "")) for c in column) + 2))
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.freeze_panes = "A5"; ws.auto_filter.ref = f"A4:{ws.cell(4, len(headers)).coordinate}"
    wb.save(path)

def export_pdf(path, title, headers, rows):
    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4), rightMargin=10*mm, leftMargin=10*mm, topMargin=10*mm, bottomMargin=10*mm)
    styles = getSampleStyleSheet()
    from reportlab.lib.styles import ParagraphStyle
    story = [pdf_paragraph(title, styles["Title"], True), Paragraph(f"Generated: {datetime.now():%d-%m-%Y %H:%M}", styles["Normal"]), Spacer(1, 6*mm)]
    cell = ParagraphStyle("plain-cell", parent=styles["Normal"], fontSize=7, leading=8.5)
    head = ParagraphStyle("plain-head", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    data = [[pdf_paragraph(h, head, True) if has_arabic(h) else h for h in headers]] + \
           [[pdf_paragraph(value, cell) if has_arabic(value) else ("" if value is None else str(value)) for value in row] for row in rows]
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#071B2E")), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"), ("FONTSIZE", (0,0), (-1,-1), 7),
        ("GRID", (0,0), (-1,-1), .25, colors.grey), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F3F6F8")]),
        ("ALIGN", (2,1), (-1,-1), "RIGHT"), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("BOTTOMPADDING", (0,0), (-1,0), 7), ("TOPPADDING", (0,0), (-1,0), 7),
    ]))
    story.append(table); doc.build(story)

def print_rows(title, headers, rows):
    handle = tempfile.NamedTemporaryFile(prefix="SaberAccounting_", suffix=".pdf", delete=False)
    handle.close(); export_pdf(handle.name, title, headers, rows)
    if os.name != "nt": raise RuntimeError("Printing is available in the Windows application")
    os.startfile(handle.name, "print")
    return handle.name

def export_invoice_pdf(path, invoice, items, logo_path=None, company=None):
    """Professional printable sales invoice (Lebanese format): navy header band with the
    company block + document title, status badge and a Date/Number/Currency/Due info card,
    a BILL TO party card, the line-item table (Item, Description, Quantity, Unit Price,
    Net before VAT), a totals panel (Total Before VAT, VAT 11%, Total, VAT LBP rate and
    VAT in LBP, Balance), the amount in words in English and Arabic, the Arabic fiscal-stamp
    note, and a signature row. Colours and content are data-driven from company settings."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT
    from tafqeet import amount_in_words

    NAVY_C=colors.HexColor("#0B2239"); GOLD_C=colors.HexColor("#C9A24B"); GREY=colors.HexColor("#5F6B76")
    LINE=colors.HexColor("#D5DBE1"); SOFT=colors.HexColor("#F4F6F8"); ZEBRA=colors.HexColor("#EEF2F6")
    PAGE_W,PAGE_H=A4; ML=13*mm; MR=13*mm; CONTENT_W=PAGE_W-ML-MR
    doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=MR,leftMargin=ML,topMargin=13*mm,bottomMargin=16*mm)
    styles=getSampleStyleSheet(); story=[]; money=lambda v: f"{float(v or 0):,.2f}"
    company=company or {}

    small=ParagraphStyle("inv-small",parent=styles["Normal"],fontSize=8,leading=10.5,textColor=colors.HexColor("#243544"))
    small_r=ParagraphStyle("inv-small-r",parent=small,alignment=TA_RIGHT)
    label_s=ParagraphStyle("inv-label",parent=small,textColor=GREY,fontName="Helvetica-Bold",fontSize=7.5)
    co_style=ParagraphStyle("inv-co",parent=styles["Normal"],fontName="Helvetica-Bold",fontSize=16,textColor=colors.white,leading=18)
    co_line=ParagraphStyle("inv-co-line",parent=small,textColor=colors.HexColor("#D7E0E8"),fontSize=7.5,leading=9.5)
    title_style=ParagraphStyle("inv-title",parent=styles["Normal"],fontName="Helvetica-Bold",fontSize=20,alignment=TA_RIGHT,textColor=colors.white,leading=22)
    cell=ParagraphStyle("inv-cell",parent=styles["Normal"],fontSize=8.5,leading=10.5,textColor=colors.HexColor("#243544"))
    party_name_s=ParagraphStyle("inv-pn",parent=styles["Normal"],fontName="Helvetica-Bold",fontSize=11,textColor=NAVY_C,leading=13)
    section_s=ParagraphStyle("inv-sec",parent=label_s,textColor=GOLD_C,fontSize=8)

    subtype=str(invoice.get("doc_subtype") or "invoice"); kind=str(invoice.get("kind") or "sale")
    title={"credit_note":"CREDIT NOTE","debit_note":"DEBIT NOTE"}.get(subtype,"SALES INVOICE" if kind=="sale" else "PURCHASE INVOICE")

    subtotal=float(invoice.get("subtotal") or 0); vat=float(invoice.get("vat") or 0); total=float(invoice.get("total") or subtotal+vat)
    cur=invoice.get("currency") or ""; paid=float(invoice.get("amount_paid") or 0); balance=total-paid
    status=("PAID",colors.HexColor("#1E7A46")) if paid>=total and total>0 else (("PARTIAL",GOLD_C) if paid>0 else ("DUE",colors.HexColor("#A23B2C")))

    company_name=company.get("company_name") or "SABER FOR AUDIT"
    left=[pdf_paragraph(company_name,co_style,True)]
    for key in ("company_address","company_phone","company_email","company_website"):
        if company.get(key): left.append(pdf_paragraph(str(company[key]),co_line))
    if company.get("company_mof"): left.append(pdf_paragraph(f'VAT No.: {company["company_mof"]}',co_line))
    _vat_reg=str(company.get("company_vat_registered") or "").strip().lower()
    if _vat_reg in ("yes","1","true"):
        _vd=str(company.get("company_vat_date") or "").strip()
        left.append(pdf_paragraph(f'Registered in VAT since {_vd}' if _vd else 'Registered in VAT',co_line))
    elif _vat_reg in ("no","0","false"):
        left.append(pdf_paragraph('Not registered in VAT',co_line))
    logo_cell=None
    if logo_path and os.path.exists(str(logo_path)):
        try: logo_cell=Image(str(logo_path),width=20*mm,height=20*mm)
        except Exception: logo_cell=None
    if logo_cell:
        left_stack=Table([[logo_cell,left]],colWidths=[22*mm,None])
        left_stack.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(0,0),4),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    else:
        left_stack=left
    right=[pdf_paragraph(title,title_style,True)]
    if status[0]!="DUE":
        badge=Table([[Paragraph(status[0],ParagraphStyle("badge",parent=styles["Normal"],fontName="Helvetica-Bold",fontSize=9,textColor=colors.white,alignment=TA_CENTER))]],colWidths=[24*mm])
        badge.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),status[1]),("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)]))
        right+=[Spacer(1,2*mm),Table([[badge]],colWidths=[24*mm],hAlign="RIGHT",style=[("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)])]
    band=Table([[left_stack,right]],colWidths=[CONTENT_W*0.60,CONTENT_W*0.40])
    band.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("BACKGROUND",(0,0),(-1,-1),NAVY_C),("LEFTPADDING",(0,0),(-1,-1),10),
        ("RIGHTPADDING",(0,0),(-1,-1),10),("TOPPADDING",(0,0),(-1,-1),9),("BOTTOMPADDING",(0,0),(-1,-1),9),("LINEBELOW",(0,0),(-1,-1),2.2,GOLD_C)]))
    story.extend([band,Spacer(1,5*mm)])

    info=[["Invoice Date",invoice.get("invoice_date") or ""],["Invoice No.",invoice.get("invoice_number") or ""],
          ["Currency",invoice.get("currency") or ""],["Due Date",invoice.get("due_date") or "-"]]
    info_table=Table([[pdf_paragraph(k,label_s),pdf_paragraph(str(v),small_r,True)] for k,v in info],colWidths=[26*mm,None])
    info_table.setStyle(TableStyle([("LINEBELOW",(0,0),(-1,-2),.4,LINE),("BACKGROUND",(0,0),(0,-1),SOFT),
        ("TOPPADDING",(0,0),(-1,-1),3.5),("BOTTOMPADDING",(0,0),(-1,-1),3.5),("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),("BOX",(0,0),(-1,-1),.5,LINE)]))

    party_lines=[pdf_paragraph(invoice.get("party_name") or "",party_name_s,True)]
    for lbl,val in (("Code",invoice.get("party_code")),("Address",invoice.get("party_address")),("MOF No.",invoice.get("party_mof"))):
        if not val: continue
        if has_arabic(val): party_lines.append(pdf_paragraph(f"{lbl}: {val}",small))
        else: party_lines.append(Paragraph(f"<b>{_escape(lbl)}:</b> {_escape(str(val))}",small))
    party_inner=Table([[pdf_paragraph("BILL TO",section_s,True)]]+[[p] for p in party_lines],colWidths=[None])
    party_inner.setStyle(TableStyle([("LEFTPADDING",(0,0),(-1,-1),9),("RIGHTPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),2),
        ("BOTTOMPADDING",(0,0),(-1,-1),2),("TOPPADDING",(0,0),(0,0),6),("BOTTOMPADDING",(0,-1),(-1,-1),6),
        ("BOX",(0,0),(-1,-1),.5,LINE),("LINEBEFORE",(0,0),(0,-1),2.2,GOLD_C),("BACKGROUND",(0,0),(-1,-1),colors.white)]))

    two_col=Table([[party_inner,info_table]],colWidths=[CONTENT_W*0.56,CONTENT_W*0.44])
    two_col.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(0,0),8),("RIGHTPADDING",(1,0),(1,0),0)]))
    story.extend([two_col,Spacer(1,5*mm)])

    head_s=ParagraphStyle("inv-head",parent=styles["Normal"],fontName="Helvetica-Bold",fontSize=8.5,textColor=colors.white,leading=10)
    head_r=ParagraphStyle("inv-head-r",parent=head_s,alignment=TA_RIGHT)
    headers=[pdf_paragraph("Item",head_s,True),pdf_paragraph("Description",head_s,True),pdf_paragraph("Quantity",head_r,True),
             pdf_paragraph("Unit Price",head_r,True),pdf_paragraph("Net before VAT",head_r,True)]
    rows=[]; net_total=0.0
    for x in items:
        qty=float(x.get("quantity") or 0); price=float(x.get("unit_price") or 0); gross=float(x.get("gross_amount") or qty*price)
        percent=float(x.get("discount_percent") or 0); discount=float(x.get("discount_amount") or 0) or gross*percent/100
        net=gross-discount; net_total+=net; unit=x.get("unit") or ""
        qty_text=f"{qty:g}"+(f" {unit}" if unit else "")
        rows.append([x.get("item_code") or "",pdf_paragraph(x.get("description",""),cell),qty_text,money(price),money(net)])
    if not rows: rows=[["",pdf_paragraph("Invoice total",cell),"1","",money(invoice.get("subtotal"))]]; net_total=float(invoice.get("subtotal") or 0)
    col_w=[22*mm,None,26*mm,26*mm,30*mm]
    used=sum(w for w in col_w if w); col_w=[w if w else (CONTENT_W-used) for w in col_w]
    table=Table([headers]+rows,repeatRows=1,colWidths=col_w)
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),NAVY_C),("LINEBELOW",(0,0),(-1,0),1.6,GOLD_C),
        ("FONTSIZE",(0,1),(-1,-1),8.5),("ALIGN",(2,1),(-1,-1),"RIGHT"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,0),6),("BOTTOMPADDING",(0,0),(-1,0),6),("TOPPADDING",(0,1),(-1,-1),4.5),("BOTTOMPADDING",(0,1),(-1,-1),4.5),
        ("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),("TEXTCOLOR",(0,1),(-1,-1),colors.HexColor("#243544")),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,ZEBRA]),("LINEBELOW",(0,1),(-1,-1),.3,LINE),("BOX",(0,0),(-1,-1),.5,LINE)]))
    story.extend([table,Spacer(1,5*mm)])

    export=invoice.get("vat_treatment") in ("zero_rated","exempt")
    vat_label="VAT 11%" if not export else "<strike>VAT 11%</strike> Export - zero rated (Art. 19)" if invoice.get("vat_treatment")=="zero_rated" else "<strike>VAT 11%</strike> Exempt (Art. 16-17)"
    tl=ParagraphStyle("t-l",parent=styles["Normal"],fontSize=9,alignment=TA_LEFT,textColor=colors.HexColor("#243544"))
    tr=ParagraphStyle("t-r",parent=styles["Normal"],fontSize=9,alignment=TA_RIGHT,textColor=colors.HexColor("#243544"))
    tlw=ParagraphStyle("t-lw",parent=tl,fontName="Helvetica-Bold",fontSize=10.5,textColor=colors.white)
    trw=ParagraphStyle("t-rw",parent=tr,fontName="Helvetica-Bold",fontSize=10.5,textColor=colors.white)
    tlg=ParagraphStyle("t-lg",parent=tl,textColor=GREY,fontSize=8)
    trg=ParagraphStyle("t-rg",parent=tr,textColor=GREY,fontSize=8)
    gross_total=float(invoice.get("gross_total") or subtotal); inv_discount=float(invoice.get("discount") or 0)
    disc_pct=float(invoice.get("invoice_discount_percent") or 0)
    trows=[]
    if inv_discount>0.004 or disc_pct>0:
        trows.append([Paragraph("Total",tl),Paragraph(f"{money(gross_total)} {cur}",tr)])
        disc_label=f"Discount {disc_pct:g}%" if disc_pct else "Discount"
        trows.append([Paragraph(disc_label,tl),Paragraph(f"-{money(inv_discount)} {cur}",tr)])
    trows+=[[Paragraph("Total HT (before VAT)",tl),Paragraph(f"{money(subtotal)} {cur}",tr)],
           [Paragraph(vat_label,tl),Paragraph(f"{money(vat)} {cur}",tr)],
           [Paragraph("TOTAL",tlw),Paragraph(f"{money(total)} {cur}",trw)]]
    total_row=len(trows)-1; grey_rows=[]
    if invoice.get("lbp_rate"):
        trows.append([Paragraph("VAT LBP Rate",tlg),Paragraph(f"{float(invoice['lbp_rate']):,.0f}",trg)]); grey_rows.append(len(trows)-1)
    if invoice.get("vat_lbp") is not None:
        trows.append([Paragraph("VAT 11% (LBP)",tlg),Paragraph(f"{float(invoice['vat_lbp']):,.0f} LBP",trg)]); grey_rows.append(len(trows)-1)
    trows.append([Paragraph("Balance Due",tlw),Paragraph(f"{money(balance)} {'DB' if balance>=0 else 'CR'}",trw)])
    balance_row=len(trows)-1
    totals_table=Table(trows,colWidths=[42*mm,38*mm])
    ts=[("TOPPADDING",(0,0),(-1,-1),3.5),("BOTTOMPADDING",(0,0),(-1,-1),3.5),("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
        ("LINEBELOW",(0,0),(-1,1),.4,LINE),("BACKGROUND",(0,total_row),(-1,total_row),NAVY_C),("BACKGROUND",(0,balance_row),(-1,balance_row),GOLD_C),
        ("TEXTCOLOR",(0,balance_row),(-1,balance_row),NAVY_C),("BOX",(0,0),(-1,-1),.5,LINE)]
    for gr in grey_rows: ts.append(("BACKGROUND",(0,gr),(-1,gr),SOFT))
    totals_table.setStyle(TableStyle(ts))

    words=amount_in_words(total,cur)
    words_style=ParagraphStyle("words",parent=small,leading=11)
    words_flow=[pdf_paragraph("AMOUNT IN WORDS",section_s,True),Spacer(1,1.5*mm),
                Paragraph(f"<b>{words['en']}</b>",words_style),Spacer(1,1*mm),pdf_paragraph(words["ar"],words_style)]
    words_box=Table([[words_flow]],colWidths=[CONTENT_W-84*mm])
    words_box.setStyle(TableStyle([("BOX",(0,0),(-1,-1),.5,LINE),("BACKGROUND",(0,0),(-1,-1),SOFT),("LINEBEFORE",(0,0),(0,-1),2.2,GOLD_C),
        ("LEFTPADDING",(0,0),(-1,-1),9),("RIGHTPADDING",(0,0),(-1,-1),9),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]))
    summary=Table([[words_box,totals_table]],colWidths=[CONTENT_W-84*mm+2,84*mm-2])
    summary.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(0,0),8),("RIGHTPADDING",(1,0),(1,0),0)]))
    story.extend([summary,Spacer(1,5*mm)])

    story.append(pdf_paragraph("رسم الطابع المالي يسدد لاحقاً بموجب التصريح (20 ع)",ParagraphStyle("stamp",parent=small,textColor=GREY,fontSize=7.5))
    )
    if invoice.get("notes"): story.append(pdf_paragraph(f'Notes: {invoice["notes"]}',small))
    story.append(Spacer(1,12*mm))
    sign_s=ParagraphStyle("sign",parent=small,alignment=TA_CENTER,textColor=GREY,fontSize=8)
    signs=Table([[pdf_paragraph("Prepared by",sign_s),pdf_paragraph("Approved by",sign_s),pdf_paragraph("Received by",sign_s)]],colWidths=[CONTENT_W/3]*3)
    signs.setStyle(TableStyle([("LINEABOVE",(0,0),(-1,0),.6,GREY),("TOPPADDING",(0,0),(-1,0),5),("LEFTPADDING",(0,0),(-1,-1),14),("RIGHTPADDING",(0,0),(-1,-1),14)]))
    story.append(signs)

    def _decorate(canvas, document):
        canvas.saveState()
        canvas.setFillColor(GOLD_C); canvas.rect(0, PAGE_H-3*mm, PAGE_W, 3*mm, stroke=0, fill=1)
        canvas.setStrokeColor(GOLD_C); canvas.setLineWidth(1); canvas.line(ML, 11*mm, PAGE_W-MR, 11*mm)
        canvas.setFont("Helvetica", 7); canvas.setFillColor(GREY)
        canvas.drawString(ML, 7*mm, company_name)
        canvas.drawCentredString(PAGE_W/2, 7*mm, f"Generated {datetime.now():%d-%m-%Y %H:%M}")
        canvas.drawRightString(PAGE_W-MR, 7*mm, f"Page {document.page}")
        canvas.restoreState()
    doc.build(story, onFirstPage=_decorate, onLaterPages=_decorate)


# ---------------------------------------------------------------- multi-section official reports
def _plain(value):
    """Numbers stay numeric for Excel; Decimals become floats."""
    from decimal import Decimal
    if isinstance(value, Decimal): return float(value)
    return value


def _formatted(value):
    from decimal import Decimal
    if value is None: return ""
    if isinstance(value, bool): return str(value)
    if isinstance(value, int): return f"{value:,}"
    if isinstance(value, (float, Decimal)):
        number = float(value)
        return f"{number:,.0f}" if abs(number - round(number)) < 1e-9 else f"{number:,.2f}"
    return str(value)


def _safe_sheet_title(title):
    cleaned = "".join("-" if ch in '[]:*?/\\' else ch for ch in str(title))
    return cleaned[:31] or "Report"


def export_sections_excel(path, title, meta, sections):
    wb = Workbook(); ws = wb.active; ws.title = _safe_sheet_title(title)
    width = max([len(section["headers"]) for section in sections] + [2])
    navy = PatternFill("solid", fgColor=NAVY); total_fill = PatternFill("solid", fgColor="E8EDF2")
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)
    cell = ws.cell(1, 1, title); cell.font = Font(size=15, bold=True, color="FFFFFF"); cell.fill = navy
    cell.alignment = Alignment(horizontal="center", vertical="center"); ws.row_dimensions[1].height = 26
    row = 2
    for line in list(meta or []) + [f"Generated: {datetime.now():%d-%m-%Y %H:%M}"]:
        ws.cell(row, 1, line).font = Font(italic=True, color="44546A"); row += 1
    widths = {}
    for section in sections:
        row += 1
        ws.cell(row, 1, section["heading"]).font = Font(size=12, bold=True, color=NAVY); row += 1
        if section.get("narrative"):
            import textwrap
            for values in section["rows"]:
                text = " — ".join(str(v) for v in values)
                for paragraph in text.splitlines() or [""]:
                    for chunk in textwrap.wrap(paragraph, 800) or [""]:
                        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=width)
                        cell = ws.cell(row, 1, chunk)
                        cell.alignment = Alignment(wrap_text=True, vertical="top")
                        ws.row_dimensions[row].height = max(30, 15 * ((len(chunk) // 100) + 1))
                        row += 1
            continue
        for column, header in enumerate(section["headers"], 1):
            h = ws.cell(row, column, header); h.font = Font(bold=True, color="FFFFFF"); h.fill = navy
            h.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            widths[column] = max(widths.get(column, 10), min(22, len(str(header)) + 2))
        ws.row_dimensions[row].height = 30; row += 1
        totals = set(section.get("total_rows") or [])
        for index, values in enumerate(section["rows"]):
            for column, value in enumerate(values, 1):
                c = ws.cell(row, column, _plain(value))
                if isinstance(c.value, (int, float)) and not isinstance(c.value, bool):
                    c.number_format = "#,##0.00" if isinstance(c.value, float) and abs(c.value - round(c.value)) > 1e-9 else "#,##0"
                    c.alignment = Alignment(horizontal="right")
                if index in totals: c.font = Font(bold=True); c.fill = total_fill
                widths[column] = max(widths.get(column, 10), min(45, len(_formatted(value)) + 2))
            row += 1
    for column, value in widths.items(): ws.column_dimensions[get_column_letter(column)].width = value
    ws.sheet_view.showGridLines = True
    wb.save(path)


def export_sections_pdf(path, title, meta, sections):
    from reportlab.lib.styles import ParagraphStyle
    financial = title.startswith("Financial Statements,")
    page = A4 if financial else landscape(A4)
    doc = SimpleDocTemplate(str(path), pagesize=page, rightMargin=8*mm, leftMargin=8*mm, topMargin=10*mm, bottomMargin=12*mm, title=title)
    styles = getSampleStyleSheet()
    regular, bold_font = arabic_fonts() if financial else (None, None)
    regular = regular or "Helvetica"; bold_font = bold_font or "Helvetica-Bold"
    if financial:
        for style in styles.byName.values(): style.fontName = regular
        for key in ("Title", "Heading1", "Heading2", "Heading3"): styles[key].fontName = bold_font
        styles["Normal"].fontSize=11; styles["Normal"].leading=15
    header_style = ParagraphStyle("header", parent=styles["Normal"], fontName=bold_font, fontSize=10 if financial else 6.5, leading=13 if financial else 7.5, textColor=colors.white, alignment=1)
    cell_style = ParagraphStyle("cell", parent=styles["Normal"], fontSize=10 if financial else 6.5, leading=13 if financial else 7.5)
    story = [pdf_paragraph(title, styles["Title"], True)]
    for line in list(meta or []) + [f"Generated: {datetime.now():%d-%m-%Y %H:%M}"]: story.append(pdf_paragraph(line, styles["Normal"]))
    story.append(Spacer(1, 4*mm))
    available = page[0] - 16*mm
    for section in sections:
        if financial and (section["heading"].startswith(("Statement of", "Notes: account")) or section["heading"].endswith("DRAFT - Addressee")):
            from reportlab.platypus import PageBreak
            story.append(PageBreak())
        story.append(pdf_paragraph(section["heading"], styles["Heading3"], True))
        if section.get("narrative"):
            for values in section["rows"]:
                for paragraph in " — ".join(str(v) for v in values).splitlines():
                    story.append(pdf_paragraph(paragraph, styles["Normal"]))
                    story.append(Spacer(1, 2*mm))
            story.append(Spacer(1, 3*mm))
            continue
        headers = section["headers"]; count = len(headers)
        body = [[_formatted(value) for value in list(values) + [""] * (count - len(values))] for values in section["rows"]]
        weights = []
        def header_length(text):
            parts = [p.strip() for p in str(text).split(" | ")]
            return max(len(p) * (0.8 if has_arabic(p) else 1) for p in parts) * (0.75 if len(parts) > 1 else 1)
        for column in range(count):
            longest = max([header_length(headers[column])] + [len(row[column]) * (1.15 if has_arabic(row[column]) else 1) for row in body] or [6])
            weights.append(min(max(longest, 7), 30))
        if financial and count == 5:
            weights = [13, 24, 29, 20, 23] if headers[0] == "Account" else [35, 16, 23, 16, 16]
        scale = available / sum(weights); col_widths = [w * scale for w in weights]
        def header_cell(text):
            parts = [p.strip() for p in str(text).split(" | ")]
            if len(parts) == 1: return pdf_paragraph(parts[0], header_style, True)
            return [pdf_paragraph(p, header_style, True) for p in parts]  # English above, Arabic below
        data = [[header_cell(h) for h in headers]]
        for row in body:
            data.append([pdf_paragraph(value, cell_style) if has_arabic(value) or (len(value) > 18 and not value.replace(",", "").replace(".", "").replace("-", "").isdigit()) else value for value in row])
        table = Table(data, repeatRows=1, colWidths=col_widths)
        style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#071B2E")), ("FONTNAME", (0, 1), (-1, -1), regular), ("FONTSIZE", (0, 1), (-1, -1), 10 if financial else 6.5),
                 ("GRID", (0, 0), (-1, -1), .25, colors.grey), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                 ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F6F8")]),
                 ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
        for column in range(count):
            if any(value and value.replace(",", "").replace(".", "").lstrip("-").isdigit() for value in (row[column] for row in body)):
                style.append(("ALIGN", (column, 1), (column, -1), "RIGHT"))
        for index in section.get("total_rows") or []:
            if 0 <= index < len(body):
                style += [("FONTNAME", (0, index + 1), (-1, index + 1), bold_font), ("BACKGROUND", (0, index + 1), (-1, index + 1), colors.HexColor("#E8EDF2"))]
        table.setStyle(TableStyle(style)); story += [table, Spacer(1, 5*mm)]

    def footer(canvas, document):
        canvas.saveState(); canvas.setFont(regular, 7); canvas.setFillColor(colors.HexColor("#5F6B76"))
        footer_title = title.split(" | ")[0] if has_arabic(title) else title
        canvas.drawString(8*mm, 6*mm, footer_title); canvas.drawRightString(page[0] - 8*mm, 6*mm, f"Page {document.page}")
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def _with_libraries(function):
    @_functools.wraps(function)
    def run(*args, **kwargs):
        _load_libraries(); return function(*args, **kwargs)
    return run


for _name, _value in list(globals().items()):
    if callable(_value) and getattr(_value, "__module__", None) == __name__ and isinstance(_value, type(_load_libraries)) \
            and _name not in ("_load_libraries", "_with_libraries"):
        globals()[_name] = _with_libraries(_value)
del _name, _value
