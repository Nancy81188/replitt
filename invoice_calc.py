"""One invoice calculation for the screen, the Excel import and the PDF.

Line: Amount = Qty x Unit Price; line discount %; Net = Amount - discount.
Invoice: Total = sum of Net; invoice discount (% or amount) is shared over the lines in proportion to their Net;
Total HT = Total - discount; VAT = Total HT of each line x its VAT %; TOTAL = Total HT + VAT."""
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def _d(value):
    try: return Decimal(str(value if value not in (None, "") else 0).replace(",", "").replace("%", ""))
    except Exception: raise ValueError(f"'{value}' is not a number")


def calculate(lines, invoice_discount_percent=0, invoice_discount_amount=0, zero_vat=False):
    rows = []; total_net = Decimal("0")
    for line in lines:
        qty = _d(line.get("quantity") or 1); price = _d(line.get("unit_price")); percent = _d(line.get("discount_percent"))
        if qty < 0 or price < 0 or percent < 0 or percent > 100: raise ValueError("Quantity, price and discount must be positive (discount up to 100%)")
        gross = (qty * price).quantize(CENT, rounding=ROUND_HALF_UP); discount = (gross * percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)
        net = gross - discount; total_net += net
        rows.append({**line, "quantity": float(qty), "unit_price": float(price), "gross_amount": float(gross), "discount_percent": float(percent),
                     "discount_amount": float(discount), "net": net, "vat_rate": 0.0 if zero_vat else float(_d(line.get("vat_rate") if line.get("vat_rate") not in (None, "") else 11))})
    percent = _d(invoice_discount_percent); amount = _d(invoice_discount_amount)
    if percent < 0 or percent > 100 or amount < 0: raise ValueError("The invoice discount must be between 0% and 100%, or a positive amount")
    discount = amount if amount else (total_net * percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)
    if discount > total_net: raise ValueError("The discount cannot be more than the total")
    remaining = discount; vat_total = Decimal("0"); taxable = Decimal("0"); exempt = Decimal("0")
    for index, row in enumerate(rows):
        share = (discount * row["net"] / total_net).quantize(CENT, rounding=ROUND_HALF_UP) if total_net and index < len(rows) - 1 else remaining
        remaining -= share; after = row["net"] - share
        rate = Decimal(str(row["vat_rate"])); vat = (after * rate / 100).quantize(CENT, rounding=ROUND_HALF_UP)
        row.update(deductible_subtotal=float(after) if rate > 0 else 0.0, non_deductible_subtotal=0.0 if rate > 0 else float(after), vat=float(vat),
                   subtotal=float(after), total=float(after + vat), net=float(row["net"]))
        vat_total += vat; taxable += after if rate > 0 else 0; exempt += after if rate <= 0 else 0
    total_ht = total_net - discount
    return {"lines": rows, "total": float(total_net), "discount": float(discount), "discount_percent": float(percent), "discount_amount": float(amount),
            "total_ht": float(total_ht), "vat": float(vat_total), "grand_total": float(total_ht + vat_total), "taxable": float(taxable), "exempt": float(exempt)}
