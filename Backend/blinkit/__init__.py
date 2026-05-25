"""Blinkit automation package."""

from .audio import AudioGroceryReader, get_grocery_items_from_audio
from .bot import BlinkitOrderBot, run, run_blinkit_checkout_cod, run_blinkit_order
from .browser import BlinkitBrowser, launch_blinkit_context
from .cart import (
    CartManager,
    capture_cart_screenshots,
    clear_delivery_tip,
    click_cart_button,
    empty_cart,
    leave_cart_screen,
    open_cart,
    wait_for_cart_panel,
)
from .checkout import (
    CheckoutManager,
    cash_payment_selected,
    click_checkout_proceed,
    click_enabled_pay_now,
    click_place_order,
    click_saved_address_candidate,
    get_saved_address_candidates,
    open_saved_addresses,
    select_cod_payment,
    select_saved_address,
)
from .constants import BASE_DIR, CART_ROOT_SELECTOR, CART_TITLE_SELECTOR, MOBILE_USER_AGENT
from .products import (
    ProductSearcher,
    add_item,
    choose_product_option,
    click_product_add_button,
    get_first_product_options,
)
from .receipt import (
    ReceiptRenderer,
    build_receipt_html,
    extract_order_summary,
    html_text,
    money_number,
    render_receipt_screenshot,
)
from .text_matching import TextMatcher, fuzzy_text_score, item_search_name, normalize_match_text

__all__ = [
    "AudioGroceryReader",
    "BlinkitBrowser",
    "BlinkitOrderBot",
    "CartManager",
    "CheckoutManager",
    "ProductSearcher",
    "ReceiptRenderer",
    "TextMatcher",
    "BASE_DIR",
    "CART_ROOT_SELECTOR",
    "CART_TITLE_SELECTOR",
    "MOBILE_USER_AGENT",
    "add_item",
    "build_receipt_html",
    "capture_cart_screenshots",
    "cash_payment_selected",
    "choose_product_option",
    "clear_delivery_tip",
    "click_cart_button",
    "click_checkout_proceed",
    "click_enabled_pay_now",
    "click_place_order",
    "click_product_add_button",
    "click_saved_address_candidate",
    "empty_cart",
    "extract_order_summary",
    "fuzzy_text_score",
    "get_first_product_options",
    "get_grocery_items_from_audio",
    "get_saved_address_candidates",
    "html_text",
    "item_search_name",
    "launch_blinkit_context",
    "leave_cart_screen",
    "money_number",
    "normalize_match_text",
    "open_cart",
    "open_saved_addresses",
    "render_receipt_screenshot",
    "run",
    "run_blinkit_checkout_cod",
    "run_blinkit_order",
    "select_cod_payment",
    "select_saved_address",
    "wait_for_cart_panel",
]
