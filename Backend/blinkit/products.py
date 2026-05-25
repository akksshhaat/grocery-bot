import json

from .cart import leave_cart_screen, wait_for_cart_panel
from .constants import PRODUCT_SELECTION_PROMPT, client

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

class ProductSearcher:
    get_first_options = staticmethod(get_first_product_options)
    choose_option = staticmethod(choose_product_option)
    click_add_button = staticmethod(click_product_add_button)
    add_item = staticmethod(add_item)
