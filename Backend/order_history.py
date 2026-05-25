import json
import re
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ORDER_HISTORY_DIR = BASE_DIR / "order_history"


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def safe_history_key(value):
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value)).strip("_") or "unknown"


def telegram_user_metadata(update):
    user = update.effective_user
    chat = update.effective_chat

    return {
        "chat_id": chat.id if chat else None,
        "chat_type": chat.type if chat else None,
        "user_id": user.id if user else None,
        "username": user.username if user else None,
        "first_name": user.first_name if user else None,
        "last_name": user.last_name if user else None,
        "language_code": user.language_code if user else None,
    }


def build_confirmed_order_record(update, approval, checkout_result):
    cart_result = approval.get("result")
    cart_raw = cart_result.raw if cart_result else {}
    checkout_raw = checkout_result.raw if checkout_result else {}

    return {
        "confirmed_at": utc_now_iso(),
        "user": telegram_user_metadata(update),
        "provider": cart_result.provider if cart_result else "blinkit",
        "items": approval.get("items", []),
        "cart_edits": approval.get("cart_edits", []),
        "address_hint": approval.get("address_hint"),
        "screenshot_path": approval.get("screenshot_path"),
        "cart": {
            "success": cart_result.success if cart_result else None,
            "added_items": cart_result.added_items if cart_result else [],
            "failed_items": cart_result.failed_items if cart_result else [],
            "order_summary": cart_raw.get("order_summary", {}),
            "cart_opened": cart_raw.get("cart_opened"),
            "receipt_path": cart_raw.get("receipt_path"),
        },
        "checkout": {
            "success": checkout_result.success if checkout_result else None,
            "address_result": checkout_raw.get("address_result", {}),
            "final_url": checkout_raw.get("final_url"),
            "browser_left_open": checkout_raw.get("browser_left_open"),
        },
    }


def append_confirmed_order_history(update, approval, checkout_result):
    metadata = telegram_user_metadata(update)
    history_key = safe_history_key(metadata.get("chat_id") or metadata.get("user_id"))
    history_path = ORDER_HISTORY_DIR / f"chat_{history_key}.jsonl"
    record = build_confirmed_order_record(update, approval, checkout_result)

    ORDER_HISTORY_DIR.mkdir(exist_ok=True)
    with history_path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    return history_path
