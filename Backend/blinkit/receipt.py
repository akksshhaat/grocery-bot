import os
from html import escape

from .constants import CART_ROOT_SELECTOR

def money_number(value):
    if not value:
        return 0
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return int(digits) if digits else 0

def html_text(value):
    return escape(str(value or ""), quote=True)

def build_receipt_html(order_summary, failed_items):
    cart_items = order_summary.get("cart_item_breakup", [])
    bill_lines = order_summary.get("bill_breakup", [])
    delivery_eta = order_summary.get("delivery_eta") or "Delivery timing shown in Blinkit"
    shipment_count = order_summary.get("shipment_count") or ""
    total_savings = order_summary.get("total_savings") or ""
    donation = order_summary.get("donation") or {}
    checkout_total = order_summary.get("checkout_total") or ""

    item_rows = []
    for item in cart_items:
        name = html_text(item.get("name"))
        variant = html_text(item.get("variant"))
        quantity = html_text(item.get("quantity", 1))
        price = html_text(item.get("price"))
        mrp = html_text(item.get("mrp"))
        savings = html_text(item.get("savings"))
        meta_parts = [part for part in [variant, f"Qty {quantity}"] if part]
        price_meta = ""
        if mrp:
            price_meta = f'<span class="mrp">MRP {mrp}</span>'
        if savings and savings != "₹0":
            price_meta += f'<span class="save">Saved {savings}</span>'
        item_rows.append(
            f"""
            <div class="item">
                <div class="item-main">
                    <div class="item-name">{name}</div>
                    <div class="item-meta">{' • '.join(meta_parts)}</div>
                </div>
                <div class="item-price">
                    <div class="price">{price}</div>
                    <div class="price-meta">{price_meta}</div>
                </div>
            </div>
            """
        )

    if not item_rows:
        item_rows.append('<div class="empty">No cart items found.</div>')

    bill_rows = []
    for line in bill_lines:
        label = html_text(line.get("label"))
        amount = html_text(line.get("amount") or line.get("details"))
        if not label or not amount:
            continue
        is_total = label.lower() == "grand total"
        bill_rows.append(
            f"""
            <div class="bill-row {'grand' if is_total else ''}">
                <span>{label}</span>
                <strong>{amount}</strong>
            </div>
            """
        )

    if donation.get("amount"):
        bill_rows.append(
            f"""
            <div class="bill-row">
                <span>{html_text(donation.get("label") or "Donation")}</span>
                <strong>{html_text(donation.get("amount"))}</strong>
            </div>
            """
        )

    if checkout_total and not any((line.get("label") or "").lower() == "grand total" for line in bill_lines):
        bill_rows.append(
            f"""
            <div class="bill-row grand">
                <span>Total</span>
                <strong>{html_text(checkout_total)}</strong>
            </div>
            """
        )

    failed_rows = []
    for entry in failed_items or []:
        failed_rows.append(
            f"<li>{html_text(entry.get('item'))}: {html_text(entry.get('error'))}</li>"
        )
    failed_section = ""
    if failed_rows:
        failed_section = f"""
        <section class="failed">
            <h2>Items not added</h2>
            <ul>{''.join(failed_rows)}</ul>
        </section>
        """

    savings_pill = f'<div class="pill">Saved {html_text(total_savings)}</div>' if total_savings else ""
    subtitle = " • ".join(html_text(part) for part in [delivery_eta, shipment_count] if part)

    return f"""
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            * {{
                box-sizing: border-box;
            }}
            body {{
                margin: 0;
                background: #eef2f7;
                color: #111827;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
            }}
            .receipt {{
                width: 390px;
                min-height: 100px;
                background: #ffffff;
                padding: 18px;
            }}
            .header {{
                border-bottom: 1px solid #e5e7eb;
                padding-bottom: 14px;
            }}
            .topline {{
                align-items: flex-start;
                display: flex;
                justify-content: space-between;
                gap: 12px;
            }}
            h1 {{
                font-size: 22px;
                line-height: 1.2;
                margin: 0 0 6px;
            }}
            .subtitle {{
                color: #4b5563;
                font-size: 13px;
                line-height: 1.35;
            }}
            .pill {{
                background: #e8f7ed;
                border: 1px solid #bfe8cb;
                border-radius: 999px;
                color: #137333;
                font-size: 12px;
                font-weight: 700;
                padding: 6px 9px;
                white-space: nowrap;
            }}
            section {{
                padding: 14px 0;
                border-bottom: 1px solid #eef0f3;
            }}
            h2 {{
                font-size: 14px;
                margin: 0 0 10px;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: #6b7280;
            }}
            .item {{
                align-items: flex-start;
                display: flex;
                gap: 12px;
                justify-content: space-between;
                padding: 10px 0;
            }}
            .item + .item {{
                border-top: 1px solid #f3f4f6;
            }}
            .item-main {{
                min-width: 0;
                width: 65%;
            }}
            .item-name {{
                font-size: 14px;
                font-weight: 700;
                line-height: 1.28;
            }}
            .item-meta {{
                color: #6b7280;
                font-size: 12px;
                margin-top: 4px;
            }}
            .item-price {{
                min-width: 95px;
                text-align: right;
            }}
            .price {{
                font-size: 15px;
                font-weight: 800;
            }}
            .price-meta {{
                display: flex;
                flex-direction: column;
                gap: 2px;
                margin-top: 3px;
            }}
            .mrp {{
                color: #6b7280;
                font-size: 11px;
                text-decoration: line-through;
            }}
            .save {{
                color: #137333;
                font-size: 11px;
                font-weight: 700;
            }}
            .bill-row {{
                align-items: center;
                display: flex;
                justify-content: space-between;
                padding: 7px 0;
                color: #374151;
                font-size: 14px;
            }}
            .bill-row.grand {{
                border-top: 1px solid #d1d5db;
                color: #111827;
                font-size: 18px;
                font-weight: 800;
                margin-top: 8px;
                padding-top: 12px;
            }}
            .footer {{
                background: #0b8f24;
                border-radius: 10px;
                color: #ffffff;
                font-size: 14px;
                font-weight: 800;
                margin-top: 14px;
                padding: 13px 14px;
                text-align: center;
            }}
            .empty {{
                background: #f9fafb;
                border-radius: 8px;
                color: #6b7280;
                font-size: 14px;
                padding: 14px;
                text-align: center;
            }}
            .failed {{
                background: #fff7ed;
                border: 1px solid #fed7aa;
                border-radius: 10px;
                margin-top: 12px;
                padding: 12px;
            }}
            .failed h2 {{
                color: #9a3412;
            }}
            .failed ul {{
                margin: 0;
                padding-left: 18px;
                color: #7c2d12;
                font-size: 12px;
            }}
        </style>
    </head>
    <body>
        <div class="receipt" id="receipt">
            <div class="header">
                <div class="topline">
                    <div>
                        <h1>Blinkit cart review</h1>
                        <div class="subtitle">{subtitle}</div>
                    </div>
                    {savings_pill}
                </div>
            </div>
            <section>
                <h2>Items</h2>
                {''.join(item_rows)}
            </section>
            <section>
                <h2>Bill details</h2>
                {''.join(bill_rows) if bill_rows else '<div class="empty">Bill details not found.</div>'}
            </section>
            {failed_section}
            <div class="footer">Reply OK to continue, or CANCEL to stop</div>
        </div>
    </body>
    </html>
    """

def render_receipt_screenshot(context, order_summary, failed_items, screenshot_path):
    receipt_page = context.new_page()
    try:
        receipt_page.set_viewport_size({"width": 430, "height": 1200})
        receipt_page.set_content(build_receipt_html(order_summary, failed_items), wait_until="load")
        receipt = receipt_page.locator("#receipt")
        receipt.wait_for(timeout=3000)
        receipt.screenshot(path=screenshot_path)
        return screenshot_path
    finally:
        receipt_page.close()

def extract_order_summary(page):
    return page.evaluate(
        """() => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const root = Array
                .from(document.querySelectorAll('[class*="Cart___StyledDiv-sc-1ptvk5t-1"]'))
                .find((node) => {
                    if (!visible(node)) return false;
                    const text = (node.innerText || '').toLowerCase();
                    return text.includes('bill details') ||
                        text.includes('proceed') ||
                        text.includes('your total savings');
                }) || Array
                .from(document.querySelectorAll('[class*="Cart___StyledDiv-sc-1ptvk5t-1"]'))
                .find(visible);
            if (!root) {
                return {
                    cart_items: [],
                    bill_lines: [],
                    cart_item_breakup: [],
                    bill_breakup: [],
                    delivery_eta: '',
                    shipment_count: '',
                    total_savings: '',
                    checkout_total: '',
                    donation: {},
                };
            }

            const clean = (text) => (text || '').replace(/\\s+/g, ' ').trim();
            const currency = (text) => {
                const matches = clean(text).match(/₹\\s*\\d+(?:\\.\\d+)?|FREE/gi) || [];
                const match = matches[matches.length - 1];
                return match ? match.replace(/\\s+/g, '') : '';
            };
            const numberFromText = (text) => {
                const match = clean(text).match(/\\d+/);
                return match ? Number(match[0]) : 0;
            };
            const textFrom = (node, selector) => {
                const el = node.querySelector(selector);
                return el ? clean(el.innerText || el.textContent) : '';
            };
            const firstText = (selector) => textFrom(root, selector);

            const cartItems = Array
                .from(root.querySelectorAll('[class*="CartProduct__Container"]'))
                .map((row) => clean(row.innerText))
                .filter(Boolean);
            const cartItemBreakup = Array
                .from(root.querySelectorAll('[class*="CartProduct__Container"]'))
                .map((row) => {
                    const price = textFrom(row, '[class*="DefaultProductCard__Price-sc"]');
                    const mrp = textFrom(row, '[class*="DefaultProductCard__Mrp-sc"]');
                    const qtyContainer = row.querySelector('[class*="AddToCart__UpdatedButtonContainer"]');
                    const qtyText = qtyContainer ? clean(qtyContainer.innerText) : '';
                    const quantity = numberFromText(qtyText) || 1;
                    return {
                        name: textFrom(row, '[class*="DefaultProductCard__ProductTitle"]'),
                        variant: textFrom(row, '[class*="DefaultProductCard__ProductVariantContainer"]'),
                        quantity,
                        price,
                        mrp,
                        savings: price && mrp ? `₹${Math.max(0, numberFromText(mrp) - numberFromText(price))}` : '',
                    };
                })
                .filter((item) => item.name);

            const billLines = Array
                .from(root.querySelectorAll('[class*="BillCard__BillItemContainer"]'))
                .map((row) => clean(row.innerText))
                .filter(Boolean);
            const billBreakup = Array
                .from(root.querySelectorAll('[class*="BillCard__BillItemContainer"]'))
                .map((row) => {
                    const label = textFrom(row, '[class*="BillCard__BillItemLeftHeaderTextContent"]');
                    const right = textFrom(row, '[class*="BillCard__BillItemRightHeader"]');
                    const tag = textFrom(row, '[class*="BillCard__Tag"]');
                    return {
                        label,
                        amount: currency(right),
                        details: clean([tag, right].filter(Boolean).join(' ')),
                    };
                })
                .filter((line) => line.label && (line.amount || line.details));

            const donationContainer = root.querySelector('[class*="FeedingIndiaComponent__Container"]');
            const donation = donationContainer ? {
                label: textFrom(donationContainer, '[class*="FeedingIndiaComponent__Title"]') || 'Donation',
                amount: currency(textFrom(donationContainer, '[class*="FeedingIndiaComponent__Amount"]')),
                selected: Boolean(donationContainer.querySelector('[class*="icon-check"]')),
            } : {};

            return {
                cart_items: cartItems,
                bill_lines: billLines,
                cart_item_breakup: cartItemBreakup,
                bill_breakup: billBreakup,
                delivery_eta: firstText('[class*="HeaderStrip__Heading"]'),
                shipment_count: firstText('[class*="HeaderStrip__Hightlight"]'),
                total_savings: currency(firstText('[class*="TotalSaving__TotalSavings"]')),
                checkout_total: currency(firstText('[class*="CheckoutStrip__NetPriceText"]')),
                donation,
            };
        }"""
    )

class ReceiptRenderer:
    money_number = staticmethod(money_number)
    html_text = staticmethod(html_text)
    build_html = staticmethod(build_receipt_html)
    render_screenshot = staticmethod(render_receipt_screenshot)
    extract_order_summary = staticmethod(extract_order_summary)
