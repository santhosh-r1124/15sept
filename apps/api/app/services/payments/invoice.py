"""Printable invoice rendering (Phase 10).

A self-contained HTML document a browser can print to PDF - no PDF library, no cost. Every
value that came from a user (matter title, names) is HTML-escaped: an invoice is the one place
where a title like ``<script>...`` would otherwise be rendered in a page served from our origin.
The route also sends a locked-down Content-Security-Policy as a second layer.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from html import escape

_STYLE = (
    "body{font:14px/1.5 system-ui,sans-serif;color:#0f172a;max-width:680px;margin:32px auto;"
    "padding:0 16px}h1{font-size:22px;margin:0}table{width:100%;border-collapse:collapse;"
    "margin-top:16px}th,td{text-align:left;padding:8px;border-bottom:1px solid #e2e8f0}"
    "td.num,th.num{text-align:right}.muted{color:#64748b;font-size:12px}"
    ".total td{font-weight:600;border-top:2px solid #0f172a}"
)


def render_invoice_html(
    *,
    invoice_number: str,
    issued_at: datetime,
    client_name: str,
    advocate_name: str,
    description: str,
    amount: Decimal,
    refunded: Decimal,
    currency: str,
) -> str:
    e = escape
    refund_rows = ""
    if refunded > 0:
        refund_rows = (
            f'<tr><td>Refunded</td><td class="num">-{e(currency)} {refunded}</td></tr>'
            f'<tr class="total"><td>Net paid</td>'
            f'<td class="num">{e(currency)} {amount - refunded}</td></tr>'
        )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="robots" content="noindex">'
        f"<title>Invoice {e(invoice_number)}</title><style>{_STYLE}</style></head><body>"
        f"<h1>Invoice {e(invoice_number)}</h1>"
        f'<p class="muted">Issued {e(issued_at.strftime("%d %b %Y"))}</p>'
        f"<p><b>Billed to:</b> {e(client_name)}<br><b>Advocate:</b> {e(advocate_name)}</p>"
        '<table><thead><tr><th>Description</th><th class="num">Amount</th></tr></thead><tbody>'
        f'<tr><td>{e(description)}</td><td class="num">{e(currency)} {amount}</td></tr>'
        f"{refund_rows}"
        "</tbody></table>"
        '<p class="muted">Payment receipt for professional services arranged through the '
        "platform. GST and other tax treatment is not calculated on this document.</p>"
        "</body></html>"
    )
