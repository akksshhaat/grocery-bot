import json
import os
import re
from html import escape

from dotenv import load_dotenv
from openai import OpenAI
from playwright.sync_api import sync_playwright

from app import extract_items_from_audio_files, find_audio_files

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CART_ROOT_SELECTOR = '[class*="Cart___StyledDiv-sc-1ptvk5t-1"]'
CART_TITLE_SELECTOR = '[class*="CartWrapper__Title"]'
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)

load_dotenv(os.path.join(BASE_DIR, ".env"))

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PRODUCT_SELECTION_PROMPT = """
You choose the best Blinkit search result for an Indian grocery order.

Return STRICT JSON only:
{"index": 1, "reason": "short reason"}

Rules:
* index is 1-based from the candidate list
* choose the item that best matches the requested grocery item
* reject misleading brand/name matches, for example "Dairy Milk" is chocolate, not milk
* prefer plain staple groceries over snacks, sweets, accessories, or unrelated products
* if no candidate is a reasonable match, return {"index": 0, "reason": "no good match"}

"""

def launch_blinkit_context(playwright, mobile=True, checkout=False):
    context_options = {
        "user_data_dir": os.path.join(BASE_DIR, "blinkit-user-data"),
        "headless": False,
    }
    if checkout:
        context_options.update(
            {
                "viewport": {"width": 400, "height": 648},
                "device_scale_factor": 1,
                "is_mobile": False,
                "has_touch": False,
            }
        )
    elif mobile:
        context_options.update(
            {
                "viewport": {"width": 390, "height": 844},
                "device_scale_factor": 2,
                "is_mobile": True,
                "has_touch": True,
                "user_agent": MOBILE_USER_AGENT,
            }
        )
    else:
        context_options.update(
            {
                "viewport": {"width": 1365, "height": 900},
                "device_scale_factor": 1,
                "is_mobile": False,
                "has_touch": False,
            }
        )

    return playwright.chromium.launch_persistent_context(**context_options)

def normalize_match_text(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()

def fuzzy_text_score(needle, haystack):
    needle_tokens = [token for token in normalize_match_text(needle).split() if len(token) >= 2]
    haystack_text = normalize_match_text(haystack)
    haystack_tokens = set(haystack_text.split())
    if not needle_tokens or not haystack_tokens:
        return 0

    score = 0
    for token in needle_tokens:
        if token in haystack_tokens:
            score += 4
        elif any(token in candidate or candidate in token for candidate in haystack_tokens if len(candidate) >= 3):
            score += 2

    if normalize_match_text(needle) and normalize_match_text(needle) in haystack_text:
        score += 8

    return score

def item_search_name(item):
    if isinstance(item, str):
        return item
    return item.get("name_en") or item.get("name_hi") or item.get("name")

def get_grocery_items_from_audio():
    audio_files = find_audio_files()
    if not audio_files:
        print("\nNo audio files found.")
        return []

    print("\nReading audio notes:")
    for audio_file in audio_files:
        print(f"- {audio_file.name}")

    result = extract_items_from_audio_files(audio_files)
    transcript = result["transcript"]
    print("\nTranscript:")
    print(transcript)

    print("\nFinal Grocery JSON:")
    grocery_items = result["items"]
    print(json.dumps({"items": grocery_items}, indent=2, ensure_ascii=False))
    return grocery_items

def get_first_product_options(page, limit=5):
    return page.evaluate(
        """(limit) => {
            function visibleAddElements() {
                return Array
                    .from(document.querySelectorAll('button, div, span'))
                    .filter((el) => {
                        const rect = el.getBoundingClientRect();
                        return (el.innerText || '').trim().toUpperCase() === 'ADD' &&
                            rect.width > 0 &&
                            rect.height > 0;
                    });
            }

            function productCardForAdd(addEl) {
                let node = addEl;
                let best = null;

                for (let depth = 0; depth < 12 && node; depth += 1, node = node.parentElement) {
                    const text = (node.innerText || '').replace(/\\s+/g, ' ').trim();
                    const rect = node.getBoundingClientRect();
                    if (!text || text.length < 8 || text.length > 900) {
                        continue;
                    }
                    if (rect.width < 120 || rect.width > 520 || rect.height < 120) {
                        continue;
                    }

                    const hasProductSignals =
                        /ADD/i.test(text) &&
                        (/[₹]/.test(text) || /\\b(g|kg|ml|l|pcs|piece|pack)\\b/i.test(text));

                    if (!hasProductSignals) {
                        continue;
                    }

                    const hasNameSignals =
                        /[A-Za-z]/.test(text.replace(/ADD|MINS|OFF/g, '')) ||
                        node.querySelector('img[alt]');

                    if (hasNameSignals && (!best || text.length > best.text.length)) {
                        best = { node, text };
                    }
                }

                return best;
            }

            const addElements = Array
                .from(visibleAddElements());

            const options = [];
            const seen = new Set();

            for (const addEl of addElements) {
                const best = productCardForAdd(addEl);
                if (!best) {
                    continue;
                }

                const text = best.text;
                if (seen.has(text)) {
                    continue;
                }

                seen.add(text);
                options.push({
                    index: options.length + 1,
                    text,
                    button_index: addElements.indexOf(addEl),
                });

                if (options.length >= limit) {
                    break;
                }
            }

            return options;
        }""",
        limit,
    )

def choose_product_option(item_name, options):
    if not options:
        return 0

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": PRODUCT_SELECTION_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "requested_item": item_name,
                        "candidates": options,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        temperature=0,
    )

    try:
        selection = json.loads(response.choices[0].message.content)
        index = int(selection.get("index", 0))
    except Exception:
        index = 0

    if 1 <= index <= len(options):
        print(f"OpenAI selected option {index}: {options[index - 1]['text']}")
        return index

    print(f"No good product match found for: {item_name}")
    return 0

def click_cart_button(page, timeout=3000):
    selectors = [
        '[class*="CartButton__Button"]',
        'text=/^View\\s*cart$/i',
        'text=/^My\\s*Cart$/i',
        'text=/\\bCart\\b/i',
    ]
    for selector in selectors:
        try:
            page.locator(selector).first.click(timeout=timeout)
            return True
        except Exception:
            pass

    return page.evaluate(
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
                    const className = String(el.className || '').toLowerCase();
                    if (className.includes('cartproduct')) return false;
                    return text === 'view cart' ||
                        text === 'my cart' ||
                        text.includes('view cart') ||
                        className.includes('cartbutton') ||
                        className.includes('checkoutstrip');
                });

            const target = candidates[0];
            if (!target) return false;
            const clickable = target.closest('button, a') || target;
            clickable.click();
            return true;
        }"""
    )

def wait_for_cart_panel(page, timeout=5000):
    try:
        page.get_by_text("My Cart", exact=True).wait_for(timeout=timeout)
        return True
    except Exception:
        pass

    try:
        page.locator(f"{CART_TITLE_SELECTOR}:visible").first.wait_for(timeout=timeout)
        return True
    except Exception:
        pass

    try:
        page.locator(f"{CART_ROOT_SELECTOR}:visible").first.wait_for(timeout=timeout)
        return True
    except Exception:
        pass

    return page.evaluate(
        """() => {
            const visible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0;
            };
            return Array
                .from(document.querySelectorAll('div, span, h1, h2'))
                .some((el) => {
                    if (!visible(el)) return false;
                    const text = (el.innerText || el.textContent || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    const className = String(el.className || '').toLowerCase();
                    return text === 'my cart' ||
                        (className.includes('cartwrapper__title') && text.includes('cart'));
                });
        }"""
    )

def leave_cart_screen(page):
    selectors = [
        'text=/^Start\\s*Shopping$/i',
        '[class*="CartWrapper__Icon"]',
        'text=/^←$/',
        'text=/^‹$/',
    ]
    for selector in selectors:
        try:
            page.locator(selector).first.click(timeout=1500)
            page.wait_for_timeout(1000)
            return True
        except Exception:
            pass

    try:
        page.go_back(wait_until="domcontentloaded", timeout=3000)
        page.wait_for_timeout(1000)
        return True
    except Exception:
        pass

    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        return True
    except Exception:
        return False

def empty_cart(page):
    print("\nEmptying cart...")

    if not click_cart_button(page):
        print("Cart is already empty or cart button is not visible.")
        return

    if not wait_for_cart_panel(page):
        print("Cart did not open.")
        return

    page.wait_for_timeout(1000)
    cart_rows = page.locator('[class*="CartProduct__Container"]')
    cart_count = cart_rows.count()

    if cart_count == 0:
        print("Cart is already empty.")
        leave_cart_screen(page)
        return

    print("Cart items before clearing:")
    for index in range(cart_count):
        item_text = cart_rows.nth(index).inner_text(timeout=1000).replace("\n", " ")
        print(f"{index + 1}. {item_text}")

    removed_any = False

    for attempt in range(100):
        cart_count = cart_rows.count()
        if cart_count == 0:
            break

        first_row = cart_rows.first
        item_text = first_row.inner_text(timeout=1000).replace("\n", " ")
        print(f"Removing cart item: {item_text}")

        minus_button = first_row.locator('[class*="AddToCart___StyledDiv-sc"]').first
        try:
            minus_button.click(timeout=2000, force=True)
        except Exception:
            print("Could not click minus button in first cart row.")
            break

        removed_any = True
        page.wait_for_timeout(900)

        if cart_rows.count() == 0:
            break

        if (attempt + 1) % 10 == 0:
            print(f"Still clearing cart... {attempt + 1} minus clicks")

    if removed_any:
        print("Cart emptied.")
    else:
        print("No removable cart items found.")

    try:
        leave_cart_screen(page)
    except Exception:
        pass

def click_product_add_button(page, option_index):
    option = get_first_product_options(page, limit=5)[option_index - 1]
    if not option:
        raise Exception(f"Selected product option {option_index} is no longer available")

    clicked = page.evaluate(
        """(buttonIndex) => {
            const addElements = Array
                .from(document.querySelectorAll('button, div, span'))
                .filter((el) => {
                    const rect = el.getBoundingClientRect();
                    return (el.innerText || '').trim().toUpperCase() === 'ADD' &&
                        rect.width > 0 &&
                        rect.height > 0;
                });

            const addEl = addElements[buttonIndex];
            if (addEl) {
                addEl.click();
                return true;
            }

            return false;
        }""",
        option["button_index"],
    )

    if not clicked:
        raise Exception(f"Could not click selected product option {option_index}")

def add_item(page, item_name):
    print(f"\nSearching for: {item_name}")
    try:
        if wait_for_cart_panel(page, timeout=800):
            leave_cart_screen(page)
    except Exception:
        pass

    try:
        # Click search bar on homepage when we are not already on the search page.
        page.locator('a[href="/s/"]').click(timeout=1500)
        page.wait_for_timeout(3000)
    except Exception:
        try:
            page.goto("https://blinkit.com/s/", wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
        except Exception:
            pass

    # Real search input on search page
    search_input = page.locator("input").first
    # Clear previous text
    search_input.fill("")
    # Type item
    search_input.fill(item_name)
    print(f"Typed: {item_name}")
    page.wait_for_timeout(3000)

    product_options = get_first_product_options(page, limit=5)
    print("First search results:")
    for option in product_options:
        print(f"{option['index']}. {option['text']}")

    selected_index = choose_product_option(item_name, product_options)
    if selected_index == 0:
        raise Exception(f"No matching product found for {item_name}")

    click_product_add_button(page, selected_index)
    print(f"Added: {item_name}")
    # Small wait
    page.wait_for_timeout(2000)

def open_cart(page):
    try:
        if not click_cart_button(page):
            return False
        if not wait_for_cart_panel(page):
            return False
        page.wait_for_timeout(1000)
        return True
    except Exception:
        return False

def clear_delivery_tip(page):
    print("Clearing delivery tip if selected...")

    selectors = [
        '[class*="ClearTipSelected"]',
        'text=/^Clear$/i',
    ]
    for selector in selectors:
        try:
            page.locator(selector).first.click(timeout=1500)
            page.wait_for_timeout(1000)
            return True
        except Exception:
            pass

    try:
        return page.evaluate(
            """() => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                };
                const tipRoots = Array
                    .from(document.querySelectorAll('[class*="AddTip"], div'))
                    .filter((el) => visible(el) && /tip your delivery partner/i.test(el.innerText || ''));

                for (const root of tipRoots) {
                    const clear = Array
                        .from(root.querySelectorAll('button, div, span'))
                        .find((el) => visible(el) && (el.innerText || '').trim().toLowerCase() === 'clear');
                    if (clear) {
                        clear.click();
                        return true;
                    }
                }

                return false;
            }"""
        )
    except Exception:
        return False

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

def capture_cart_screenshots(page, screenshot_path):
    base, ext = os.path.splitext(screenshot_path)
    if not ext:
        ext = ".png"

    try:
        page.locator('.ReactModal__Content:visible').first.wait_for(timeout=3000)
    except Exception:
        pass

    cart_panel = page.locator(f'{CART_ROOT_SELECTOR}:visible').first
    cart_panel.wait_for(timeout=7000)
    screenshot_paths = []

    metrics = page.evaluate(
        """() => {
            function visibleCartRoot() {
                const all = Array.from(document.querySelectorAll('[class*="Cart___StyledDiv-sc-1ptvk5t-1"]'));
                return all.find((node) => {
                    const text = (node.innerText || '').toLowerCase();
                    const rect = node.getBoundingClientRect();
                    return rect.width > 0 &&
                        rect.height > 0 &&
                        (text.includes('bill details') || text.includes('proceed') || text.includes('your total savings'));
                }) || all.find((node) => {
                    const rect = node.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                });
            }
            const el = visibleCartRoot();
            if (!el) return { height: 0, client: 0 };
            return { height: el.scrollHeight, client: el.clientHeight };
        }"""
    )

    total_height = metrics.get("height", 0)
    viewport_height = metrics.get("client", 0) or 1
    steps = max(1, (total_height + viewport_height - 1) // viewport_height)

    for index in range(steps):
        offset = index * viewport_height
        page.evaluate(
            """(y) => {
                function visibleCartRoot() {
                    const all = Array.from(document.querySelectorAll('[class*="Cart___StyledDiv-sc-1ptvk5t-1"]'));
                    return all.find((node) => {
                        const text = (node.innerText || '').toLowerCase();
                        const rect = node.getBoundingClientRect();
                        return rect.width > 0 &&
                            rect.height > 0 &&
                            (text.includes('bill details') || text.includes('proceed') || text.includes('your total savings'));
                    }) || all.find((node) => {
                        const rect = node.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                    });
                }
                const el = visibleCartRoot();
                if (el) el.scrollTop = y;
            }""",
            offset,
        )
        page.wait_for_timeout(300)
        part_path = f"{base}_part{index + 1}{ext}"
        cart_panel.screenshot(path=part_path)
        screenshot_paths.append(part_path)

    page.evaluate(
        """() => {
            function visibleCartRoot() {
                const all = Array.from(document.querySelectorAll('[class*="Cart___StyledDiv-sc-1ptvk5t-1"]'));
                return all.find((node) => {
                    const text = (node.innerText || '').toLowerCase();
                    const rect = node.getBoundingClientRect();
                    return rect.width > 0 &&
                        rect.height > 0 &&
                        (text.includes('bill details') || text.includes('proceed') || text.includes('your total savings'));
                }) || all.find((node) => {
                    const rect = node.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                });
            }
            const el = visibleCartRoot();
            if (el) el.scrollTop = 0;
        }"""
    )
    return screenshot_paths

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
            <div class="footer">Send address hint, then OK for COD checkout</div>
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

def run_blinkit_order(items, screenshot_path=None):
    added_items = []
    failed_items = []

    with sync_playwright() as p:
        context = launch_blinkit_context(p)
        page = context.new_page()
        print("Opening Blinkit...")
        page.goto("https://blinkit.com")

        # Wait for homepage
        page.wait_for_timeout(5000)
        empty_cart(page)

        # Add all items
        for item in items:
            item_name = item_search_name(item)
            if not item_name:
                failed_items.append({"item": item, "error": "Missing item name"})
                continue

            try:
                add_item(page, item_name)
                added_items.append(item_name)

            except Exception as e:
                print(f"Failed to add {item_name}")
                print(e)
                failed_items.append({"item": item_name, "error": str(e)})

        cart_opened = open_cart(page)
        if not cart_opened:
            cart_opened = click_cart_button(page)
            if cart_opened:
                page.wait_for_timeout(1200)
                cart_opened = wait_for_cart_panel(page, timeout=5000)
        screenshot_paths = []
        raw_cart_screenshot_paths = []
        receipt_path = None
        order_summary = {
            "cart_items": [],
            "bill_lines": [],
            "cart_item_breakup": [],
            "bill_breakup": [],
        }
        if cart_opened:
            clear_delivery_tip(page)
            order_summary = extract_order_summary(page)
            if screenshot_path:
                os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                try:
                    receipt_path = render_receipt_screenshot(
                        context,
                        order_summary,
                        failed_items,
                        screenshot_path,
                    )
                    screenshot_paths = [receipt_path]
                except Exception as e:
                    print("Receipt screenshot failed. Falling back to cart screenshots.")
                    print(e)
                    raw_cart_screenshot_paths = capture_cart_screenshots(page, screenshot_path)
                    screenshot_paths = raw_cart_screenshot_paths

                if os.getenv("BLINKIT_DEBUG_CART_SCREENSHOTS") == "1" and receipt_path:
                    base, ext = os.path.splitext(screenshot_path)
                    raw_path = f"{base}_cart{ext or '.png'}"
                    raw_cart_screenshot_paths = capture_cart_screenshots(page, raw_path)

        print("\nFinished!")
        page.wait_for_timeout(5000)

        context.close()

    return {
        "added_items": added_items,
        "failed_items": failed_items,
        "screenshot_path": screenshot_path,
        "screenshot_paths": screenshot_paths,
        "receipt_path": receipt_path,
        "raw_cart_screenshot_paths": raw_cart_screenshot_paths,
        "cart_opened": cart_opened,
        "order_summary": order_summary,
    }

def run_blinkit_checkout_cod(address_hint):
    if not address_hint:
        raise RuntimeError("Address hint is required before COD checkout.")

    with sync_playwright() as p:
        context = launch_blinkit_context(p, checkout=True)
        page = context.new_page()
        try:
            print("Opening Blinkit for checkout...")
            page.goto("https://blinkit.com/cart", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            cart_opened = open_cart(page)
            if not cart_opened:
                cart_opened = click_cart_button(page)
                if cart_opened:
                    page.wait_for_timeout(1200)
                    cart_opened = wait_for_cart_panel(page, timeout=5000)

            if not cart_opened:
                raise RuntimeError("Could not open cart for checkout.")

            clear_delivery_tip(page)
            address_result = select_saved_address(page, address_hint)
            if not address_result.get("selected"):
                raise RuntimeError(f"Could not select saved address: {address_result.get('reason')}")

            if not click_checkout_proceed(page):
                raise RuntimeError("Could not proceed to payment.")

            page.wait_for_timeout(2500)
            if not select_cod_payment(page):
                raise RuntimeError("Could not select Cash on Delivery.")

            if not click_place_order(page):
                raise RuntimeError("Could not place COD order.")

            page.wait_for_timeout(3000)
            return {
                "success": True,
                "address_result": address_result,
                "final_url": page.url,
                "browser_left_open": True,
            }
        finally:
            print("Checkout browser left open for inspection. Close it manually when done.")
            try:
                page.wait_for_timeout(10 * 60 * 1000)
            except Exception:
                pass

def run():
    grocery_items = get_grocery_items_from_audio()
    if not grocery_items:
        print("\nNo grocery items found in audio.")
        return

    print("\nItems to add:")
    for item in grocery_items:
        print(f"- {item_search_name(item)}")

    screenshot_path = os.path.join(BASE_DIR, "screenshots", "cart_local.png")
    run_blinkit_order(grocery_items, screenshot_path=screenshot_path)

if __name__ == "__main__":
    run()
