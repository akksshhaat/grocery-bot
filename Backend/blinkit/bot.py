import os

from playwright.sync_api import sync_playwright

from .audio import get_grocery_items_from_audio
from .browser import launch_blinkit_context
from .cart import (
    capture_cart_screenshots,
    clear_delivery_tip,
    click_cart_button,
    empty_cart,
    open_cart,
    remove_cart_item,
    wait_for_cart_panel,
)
from .checkout import click_checkout_proceed, click_place_order, select_cod_payment, select_saved_address
from .constants import BASE_DIR
from .products import add_item, parse_item_quantity
from .receipt import extract_order_summary, render_receipt_screenshot
from .text_matching import item_search_name

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
            quantity = item.get("quantity", "1") if isinstance(item, dict) else "1"
            if not item_name:
                failed_items.append({"item": item, "error": "Missing item name"})
                continue

            try:
                add_item(page, item_name, quantity)
                added_items.append({
                    "name": item_name,
                    "quantity": parse_item_quantity(quantity),
                })

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

def run_blinkit_remove_item(item_name, screenshot_path=None):
    if not item_name:
        raise RuntimeError("Item name is required for remove command.")

    with sync_playwright() as p:
        context = launch_blinkit_context(p)
        page = context.new_page()
        print("Opening Blinkit to update cart...")
        page.goto("https://blinkit.com/cart", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        remove_result = remove_cart_item(page, item_name)
        cart_opened = wait_for_cart_panel(page, timeout=5000)
        if not cart_opened:
            cart_opened = open_cart(page)

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
                        [],
                        screenshot_path,
                    )
                    screenshot_paths = [receipt_path]
                except Exception as e:
                    print("Receipt screenshot failed. Falling back to cart screenshots.")
                    print(e)
                    raw_cart_screenshot_paths = capture_cart_screenshots(page, screenshot_path)
                    screenshot_paths = raw_cart_screenshot_paths

        page.wait_for_timeout(1000)
        context.close()

    return {
        "remove_result": remove_result,
        "screenshot_path": screenshot_path,
        "screenshot_paths": screenshot_paths,
        "receipt_path": receipt_path,
        "raw_cart_screenshot_paths": raw_cart_screenshot_paths,
        "cart_opened": cart_opened,
        "order_summary": order_summary,
    }

def run_blinkit_add_item(item_name, quantity=1, screenshot_path=None):
    if not item_name:
        raise RuntimeError("Item name is required for add command.")

    quantity_count = parse_item_quantity(quantity)
    added_items = []
    failed_items = []

    with sync_playwright() as p:
        context = launch_blinkit_context(p)
        page = context.new_page()
        print("Opening Blinkit to add item...")
        page.goto("https://blinkit.com", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        try:
            add_item(page, item_name, quantity_count)
            added_items.append({
                "name": item_name,
                "quantity": quantity_count,
            })
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

        page.wait_for_timeout(1000)
        context.close()

    if failed_items:
        raise RuntimeError(failed_items[0]["error"])

    return {
        "add_result": {
            "item_name": item_name,
            "quantity": quantity_count,
        },
        "added_items": added_items,
        "failed_items": failed_items,
        "screenshot_path": screenshot_path,
        "screenshot_paths": screenshot_paths,
        "receipt_path": receipt_path,
        "raw_cart_screenshot_paths": raw_cart_screenshot_paths,
        "cart_opened": cart_opened,
        "order_summary": order_summary,
    }

def run():
    grocery_items = get_grocery_items_from_audio()
    if not grocery_items:
        print("\nNo grocery items found in audio.")
        return

    print("\nItems to add:")
    for item in grocery_items:
        quantity = item.get("quantity", "1") if isinstance(item, dict) else "1"
        print(f"- {item_search_name(item)} ({quantity})")

    screenshot_path = os.path.join(BASE_DIR, "screenshots", "cart_local.png")
    run_blinkit_order(grocery_items, screenshot_path=screenshot_path)

class BlinkitOrderBot:
    run_order = staticmethod(run_blinkit_order)
    add_item = staticmethod(run_blinkit_add_item)
    remove_item = staticmethod(run_blinkit_remove_item)
    checkout_cod = staticmethod(run_blinkit_checkout_cod)
    run_from_audio = staticmethod(run)


if __name__ == "__main__":
    run()
