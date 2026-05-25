import json
import os

from dotenv import load_dotenv
from openai import OpenAI
from playwright.sync_api import sync_playwright

from app import extract_items_from_audio_files, find_audio_files

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CART_ROOT_SELECTOR = '[class*="Cart___StyledDiv-sc-1ptvk5t-1"]'

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

def empty_cart(page):
    print("\nEmptying cart...")

    try:
        page.locator('[class*="CartButton__Button"]').click(timeout=3000)
    except Exception:
        print("Cart is already empty or cart button is not visible.")
        return

    try:
        page.get_by_text("My Cart", exact=True).wait_for(timeout=5000)
    except Exception:
        print("Cart did not open.")
        return

    page.wait_for_timeout(1000)
    cart_rows = page.locator('[class*="CartProduct__Container"]')
    cart_count = cart_rows.count()

    if cart_count == 0:
        print("Cart is already empty.")
        page.keyboard.press("Escape")
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
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
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
        # Click search bar on homepage when we are not already on the search page.
        page.locator('a[href="/s/"]').click(timeout=1500)
        page.wait_for_timeout(3000)
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
        page.locator('[class*="CartButton__Button"]').click(timeout=3000)
        page.get_by_text("My Cart", exact=True).wait_for(timeout=5000)
        page.wait_for_timeout(1000)
        return True
    except Exception:
        return False

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
            if (!root) return { cart_items: [], bill_lines: [], cart_item_breakup: [], bill_breakup: [] };

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

            return {
                cart_items: cartItems,
                bill_lines: billLines,
                cart_item_breakup: cartItemBreakup,
                bill_breakup: billBreakup,
            };
        }"""
    )

def run_blinkit_order(items, screenshot_path=None):
    added_items = []
    failed_items = []

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=os.path.join(BASE_DIR, "blinkit-user-data"),
            headless=False
        )
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
            page.locator('[class*="CartButton__Button"]').click(timeout=3000)
            page.wait_for_timeout(1200)
            cart_opened = True
        screenshot_paths = []
        order_summary = {"cart_items": [], "bill_lines": []}
        if cart_opened:
            order_summary = extract_order_summary(page)
            if screenshot_path:
                os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                screenshot_paths = capture_cart_screenshots(page, screenshot_path)

        print("\nFinished!")
        page.wait_for_timeout(5000)

        context.close()

    return {
        "added_items": added_items,
        "failed_items": failed_items,
        "screenshot_path": screenshot_path,
        "screenshot_paths": screenshot_paths,
        "cart_opened": cart_opened,
        "order_summary": order_summary,
    }

# def place_cod_order(page):
#     pass

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
