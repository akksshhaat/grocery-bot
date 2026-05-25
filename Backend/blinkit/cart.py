import os

from .constants import CART_ROOT_SELECTOR, CART_TITLE_SELECTOR
from .text_matching import fuzzy_text_score

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

def remove_cart_item(page, item_name):
    if not wait_for_cart_panel(page, timeout=2000) and not open_cart(page):
        raise RuntimeError("Could not open cart.")

    page.wait_for_timeout(1000)
    rows = page.locator('[class*="CartProduct__Container"]')
    row_count = rows.count()
    if row_count == 0:
        raise RuntimeError("Cart is empty.")

    best_index = -1
    best_score = 0
    best_text = ""
    for index in range(row_count):
        row_text = rows.nth(index).inner_text(timeout=1000).replace("\n", " ")
        score = fuzzy_text_score(item_name, row_text)
        if score > best_score:
            best_index = index
            best_score = score
            best_text = row_text

    if best_index < 0 or best_score <= 0:
        raise RuntimeError(f"Could not find item in cart: {item_name}")

    print(f"Removing matching cart item: {best_text}")

    removed_clicks = 0
    for _ in range(25):
        rows = page.locator('[class*="CartProduct__Container"]')
        if best_index >= rows.count():
            break

        row = rows.nth(best_index)
        current_text = row.inner_text(timeout=1000).replace("\n", " ")
        if fuzzy_text_score(item_name, current_text) <= 0:
            break

        minus_button = row.locator('[class*="AddToCart___StyledDiv-sc"]').first
        try:
            minus_button.click(timeout=2000, force=True)
        except Exception as exc:
            raise RuntimeError(f"Could not click remove button for {item_name}") from exc

        removed_clicks += 1
        page.wait_for_timeout(900)

    if removed_clicks == 0:
        raise RuntimeError(f"Could not remove item: {item_name}")

    return {
        "requested_item": item_name,
        "matched_item_text": best_text,
        "remove_clicks": removed_clicks,
    }

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

class CartManager:
    click_cart_button = staticmethod(click_cart_button)
    wait_for_cart_panel = staticmethod(wait_for_cart_panel)
    leave_cart_screen = staticmethod(leave_cart_screen)
    empty_cart = staticmethod(empty_cart)
    remove_item = staticmethod(remove_cart_item)
    open_cart = staticmethod(open_cart)
    clear_delivery_tip = staticmethod(clear_delivery_tip)
    capture_screenshots = staticmethod(capture_cart_screenshots)
