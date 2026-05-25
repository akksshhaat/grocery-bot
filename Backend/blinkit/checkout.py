from .text_matching import fuzzy_text_score

def click_checkout_proceed(page):
    selectors = [
        'text=/Proceed\\s*To\\s*Pay/i',
        'text=/^Proceed$/i',
        '[class*="CheckoutStrip__Container"]',
        '[class*="CheckoutStrip__CTAText"]',
    ]
    for selector in selectors:
        try:
            page.locator(selector).first.click(timeout=2500)
            page.wait_for_timeout(1800)
            return True
        except Exception:
            pass

    return page.evaluate(
        """() => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const target = Array
                .from(document.querySelectorAll('button, a, div, span'))
                .find((el) => {
                    if (!visible(el)) return false;
                    const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    const className = String(el.className || '').toLowerCase();
                    return text.includes('proceed') ||
                        text.includes('checkout') ||
                        className.includes('checkoutstrip');
                });
            if (!target) return false;
            (target.closest('button, a') || target).click();
            return true;
        }"""
    )

def open_saved_addresses(page):
    selectors = [
        'text=/^Change$/i',
        'text=/Change\\s*address/i',
        '[class*="Address"]:has-text("Change")',
    ]
    for selector in selectors:
        try:
            page.locator(selector).first.click(timeout=2500)
            page.wait_for_timeout(1500)
            return True
        except Exception:
            pass

    return page.evaluate(
        """() => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const target = Array
                .from(document.querySelectorAll('button, a, div, span'))
                .find((el) => {
                    if (!visible(el)) return false;
                    const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    const className = String(el.className || '').toLowerCase();
                    return text === 'change' ||
                        text.includes('change address') ||
                        (className.includes('address') && text.includes('change'));
                });
            if (!target) return false;
            (target.closest('button, a') || target).click();
            return true;
        }"""
    )

def get_saved_address_candidates(page):
    return page.evaluate(
        """() => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const clean = (text) => (text || '').replace(/\\s+/g, ' ').trim();
            const addressSignals = /(home|work|other|flat|floor|tower|block|house|apartment|society|sector|road|street|near|landmark|deliver|address)/i;
            const rejectSignals = /(cart|bill details|items total|grand total|tip your delivery|proceed|payment|cash|upi|card|start shopping)/i;
            const raw = Array.from(document.querySelectorAll('button, a, div'));
            const candidates = [];
            const seen = new Set();

            for (const el of raw) {
                if (!visible(el)) continue;
                const text = clean(el.innerText || el.textContent);
                if (text.length < 8 || text.length > 360) continue;
                if (!addressSignals.test(text)) continue;
                if (rejectSignals.test(text)) continue;

                let card = el;
                for (let depth = 0; depth < 4 && card.parentElement; depth += 1) {
                    const parentText = clean(card.parentElement.innerText || card.parentElement.textContent);
                    if (
                        parentText.length >= text.length &&
                        parentText.length <= 360 &&
                        addressSignals.test(parentText) &&
                        !rejectSignals.test(parentText)
                    ) {
                        card = card.parentElement;
                    }
                }

                const cardText = clean(card.innerText || card.textContent);
                const rect = card.getBoundingClientRect();
                if (!cardText || seen.has(cardText)) continue;
                seen.add(cardText);
                candidates.push({
                    index: candidates.length,
                    text: cardText,
                    rect: {
                        x: rect.left,
                        y: rect.top,
                        width: rect.width,
                        height: rect.height,
                    },
                });
            }

            return candidates.slice(0, 20);
        }"""
    )

def click_saved_address_candidate(page, candidate):
    rect = candidate.get("rect") or {}
    width = rect.get("width") or 0
    height = rect.get("height") or 0
    if width <= 0 or height <= 0:
        return False

    x = rect.get("x", 0) + width * 0.55
    y = rect.get("y", 0) + height * 0.45
    page.mouse.click(x, y)
    page.wait_for_timeout(1500)
    return True

def select_saved_address(page, address_hint):
    if not address_hint:
        return {"selected": False, "reason": "No address hint provided", "candidates": []}

    open_saved_addresses(page)
    page.wait_for_timeout(1200)
    candidates = get_saved_address_candidates(page)
    if not candidates:
        return {"selected": False, "reason": "No saved address candidates found", "candidates": []}

    best = max(candidates, key=lambda entry: fuzzy_text_score(address_hint, entry["text"]))
    best_score = fuzzy_text_score(address_hint, best["text"])
    if best_score < 4:
        return {
            "selected": False,
            "reason": "No saved address matched the hint confidently",
            "candidates": candidates[:5],
        }

    clicked = click_saved_address_candidate(page, best)
    page.wait_for_timeout(1500)
    sheet_still_open = page.evaluate(
        """() => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            return Array
                .from(document.querySelectorAll('div, span, h1, h2'))
                .some((el) => visible(el) && /select delivery address/i.test(el.innerText || el.textContent || ''));
        }"""
    )
    if sheet_still_open:
        confirmed = page.evaluate(
            """() => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                };
                const target = Array
                    .from(document.querySelectorAll('button, a, div, span'))
                    .find((el) => {
                        if (!visible(el)) return false;
                        const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                        return text === 'deliver here' ||
                            text === 'select' ||
                            text === 'continue' ||
                            text === 'confirm' ||
                            text.includes('deliver to this');
                    });
                if (!target) return false;
                (target.closest('button, a') || target).click();
                return true;
            }"""
        )
        if confirmed:
            page.wait_for_timeout(1500)
            sheet_still_open = page.evaluate(
                """() => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    };
                    return Array
                        .from(document.querySelectorAll('div, span, h1, h2'))
                        .some((el) => visible(el) && /select delivery address/i.test(el.innerText || el.textContent || ''));
                }"""
            )
    return {
        "selected": bool(clicked) and not sheet_still_open,
        "reason": "Selected saved address" if clicked and not sheet_still_open else "Matched address tap did not close address selector",
        "hint": address_hint,
        "matched_address": best["text"],
        "score": best_score,
        "candidates": candidates[:5],
    }

def select_cod_payment(page):
    payment_frame = page.frame_locator("#payment_widget")
    frame_cash_selectors = [
        '[title="Cash"][role="button"]',
        '[aria-label="Cash"]',
        'text=/^Cash$/i',
    ]
    for selector in frame_cash_selectors:
        try:
            locator = payment_frame.locator(selector).first
            locator.scroll_into_view_if_needed(timeout=2000)
            locator.click(timeout=2500)
            page.wait_for_timeout(1200)
            if cash_payment_selected(page):
                return True
            break
        except Exception:
            pass

    cash_row_selectors = [
        'text=/^Cash$/i',
        'text=/Cash/i',
    ]
    for selector in cash_row_selectors:
        try:
            locator = page.locator(selector).first
            locator.scroll_into_view_if_needed(timeout=2000)
            locator.click(timeout=2500)
            page.wait_for_timeout(1200)
            if cash_payment_selected(page):
                return True
            break
        except Exception:
            pass

    selectors = [
        'text=/Cash\\s*on\\s*Delivery/i',
        'text=/\\bCOD\\b/i',
        'text=/Pay\\s*on\\s*Delivery/i',
        'text=/Pay\\s*by\\s*Cash/i',
        'text=/Place\\s*order\\s*with\\s*cash/i',
    ]
    expand_selectors = [
        'text=/More\\s*payment\\s*options/i',
        'text=/View\\s*all/i',
        'text=/Other\\s*payment/i',
        'text=/Pay\\s*later/i',
    ]

    for attempt in range(5):
        for selector in selectors:
            try:
                locator = payment_frame.locator(selector).first
                locator.scroll_into_view_if_needed(timeout=1500)
                locator.click(timeout=2000)
                page.wait_for_timeout(1000)
                if cash_payment_selected(page):
                    return True
                return True
            except Exception:
                pass

            try:
                locator = page.locator(selector).first
                locator.scroll_into_view_if_needed(timeout=1500)
                locator.click(timeout=2000)
                page.wait_for_timeout(1000)
                if cash_payment_selected(page):
                    return True
                return True
            except Exception:
                pass

        for selector in expand_selectors:
            try:
                locator = payment_frame.locator(selector).first
                locator.scroll_into_view_if_needed(timeout=1000)
                locator.click(timeout=1500)
                page.wait_for_timeout(800)
                break
            except Exception:
                pass

            try:
                locator = page.locator(selector).first
                locator.scroll_into_view_if_needed(timeout=1000)
                locator.click(timeout=1500)
                page.wait_for_timeout(800)
                break
            except Exception:
                pass

        try:
            page.mouse.wheel(0, 650)
            page.wait_for_timeout(700)
        except Exception:
            pass

    clicked = page.evaluate(
        """() => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const target = Array
                .from(document.querySelectorAll('button, a, div, span'))
                .find((el) => {
                    if (!visible(el)) return false;
                    const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    return text.includes('cash on delivery') ||
                        text === 'cod' ||
                        text.includes('pay on delivery') ||
                        text.includes('pay by cash') ||
                        text.includes('place order with cash');
                });
            if (!target) return false;
            (target.closest('button, a') || target).click();
            return true;
        }"""
    )
    if clicked:
        page.wait_for_timeout(1000)
        if cash_payment_selected(page):
            return True
    return clicked

def cash_payment_selected(page):
    try:
        payment_frame = page.frame_locator("#payment_widget")
        frame_selectors = [
            '[title="Cash"][open]',
            '[aria-label="Cash"][aria-expanded="true"]',
            'text=/Please\\s+keep\\s+exact\\s+change/i',
        ]
        for selector in frame_selectors:
            try:
                if payment_frame.locator(selector).first.is_visible(timeout=700):
                    return True
            except Exception:
                pass
    except Exception:
        pass

    try:
        return page.evaluate(
            """() => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                };
                const text = Array
                    .from(document.querySelectorAll('body, div, span, p'))
                    .filter(visible)
                    .map((el) => el.innerText || el.textContent || '')
                    .join(' ')
                    .replace(/\\s+/g, ' ')
                    .toLowerCase();
                return text.includes('please keep exact change') ||
                    text.includes('exact change handy') ||
                    text.includes('cash on delivery') ||
                    text.includes('pay on delivery');
            }"""
        )
    except Exception:
        return False

def click_enabled_pay_now(page):
    for attempt in range(20):
        try:
            page.mouse.wheel(0, 1200)
            page.wait_for_timeout(400)
        except Exception:
            pass

        target = page.evaluate(
            """() => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                };
                const candidates = Array
                    .from(document.querySelectorAll('button, a, div, span'))
                    .filter((el) => {
                        if (!visible(el)) return false;
                        const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                        return text.includes('pay now') ||
                            text.includes('place order') ||
                            text.includes('confirm order') ||
                            text.includes('pay on delivery') ||
                            text.includes('order now');
                    });

                for (const el of candidates) {
                    let button = el.closest('button, a') || el;
                    for (let depth = 0; depth < 4 && button.parentElement; depth += 1) {
                        const parentText = (button.parentElement.innerText || button.parentElement.textContent || '')
                            .replace(/\\s+/g, ' ')
                            .trim()
                            .toLowerCase();
                        const parentRect = button.parentElement.getBoundingClientRect();
                        if (
                            parentText.includes('pay now') &&
                            parentRect.width >= button.getBoundingClientRect().width &&
                            parentRect.width <= 900 &&
                            parentRect.height <= 140
                        ) {
                            button = button.parentElement;
                        }
                    }
                    const style = window.getComputedStyle(button);
                    const rect = button.getBoundingClientRect();
                    const bg = style.backgroundColor || '';
                    const disabled =
                        button.disabled ||
                        button.getAttribute('aria-disabled') === 'true' ||
                        style.pointerEvents === 'none' ||
                        /disabled/i.test(String(button.className || ''));
                    const looksGrey = /rgba?\\((19[0-9]|20[0-9]|21[0-9])[, ]/.test(bg);
                    return {
                        x: rect.left + rect.width / 2,
                        y: rect.top + rect.height / 2,
                        text: (button.innerText || button.textContent || '').replace(/\\s+/g, ' ').trim(),
                        disabled,
                        looksGrey,
                        backgroundColor: bg,
                    };
                }
                return null;
            }"""
        )

        if target and not target.get("disabled"):
            if target.get("looksGrey") and attempt < 4:
                page.wait_for_timeout(1000)
                continue

            page.mouse.click(target["x"], target["y"])
            page.wait_for_timeout(3000)
            return True

        page.wait_for_timeout(1000)

    return False

def click_place_order(page):
    try:
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(700)
    except Exception:
        pass

    if click_enabled_pay_now(page):
        return True

    selectors = [
        'text=/Place\\s*Order/i',
        'text=/Confirm\\s*Order/i',
        'text=/Pay\\s*on\\s*Delivery/i',
        'text=/Order\\s*Now/i',
        'text=/Pay\\s*Now/i',
    ]
    for selector in selectors:
        try:
            page.locator(selector).first.scroll_into_view_if_needed(timeout=2000)
            page.locator(selector).first.click(timeout=3000)
            page.wait_for_timeout(3000)
            return True
        except Exception:
            pass

    target = page.evaluate(
        """() => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            const target = Array
                .from(document.querySelectorAll('button, a, div, span'))
                .find((el) => {
                    if (!visible(el)) return false;
                    const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    return text.includes('place order') ||
                        text.includes('confirm order') ||
                        text.includes('order now') ||
                        text.includes('pay on delivery') ||
                        text.includes('pay now');
                });
            if (!target) return null;
            const clickable = target.closest('button, a') || target;
            const rect = clickable.getBoundingClientRect();
            return {
                x: rect.left + rect.width / 2,
                y: rect.top + rect.height / 2,
            };
        }"""
    )
    if not target:
        return False

    page.mouse.click(target["x"], target["y"])
    page.wait_for_timeout(3000)
    return True

class CheckoutManager:
    click_proceed = staticmethod(click_checkout_proceed)
    open_saved_addresses = staticmethod(open_saved_addresses)
    get_saved_address_candidates = staticmethod(get_saved_address_candidates)
    click_saved_address_candidate = staticmethod(click_saved_address_candidate)
    select_saved_address = staticmethod(select_saved_address)
    select_cod_payment = staticmethod(select_cod_payment)
    cash_payment_selected = staticmethod(cash_payment_selected)
    click_enabled_pay_now = staticmethod(click_enabled_pay_now)
    click_place_order = staticmethod(click_place_order)
