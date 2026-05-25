import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app import convert_audio_to_mp3, extract_items_from_audio_files
from order_backends import OrderingBackend

BASE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = BASE_DIR / "audio"
SCREENSHOT_DIR = BASE_DIR / "screenshots"

load_dotenv(BASE_DIR / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_CHAT_ID = os.getenv("ALLOWED_CHAT_ID")
TELEGRAM_POLL_SECONDS = int(os.getenv("TELEGRAM_POLL_SECONDS", "300"))
BATCH_WAIT_SECONDS = int(os.getenv("TELEGRAM_BATCH_WAIT_SECONDS", "20"))

pending_approvals = {}
ordering_backend = OrderingBackend()
pending_audio_batches = {}
batch_tasks = {}


def is_allowed_chat(update):
    if not ALLOWED_CHAT_ID:
        return True

    return str(update.effective_chat.id) == ALLOWED_CHAT_ID


def safe_unlink(path):
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed_chat(update):
        await update.message.reply_text("This bot is not enabled for this chat.")
        return

    await update.message.reply_text(
        "Send me a Hindi grocery voice note. I will create a Blinkit cart and send a screenshot for approval.\n\n"
        "Reply OK to approve or CANCEL to cancel. Checkout is disabled for now."
    )


async def download_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    media = message.voice or message.audio

    file = await context.bot.get_file(media.file_id)
    original_name = getattr(media, "file_name", None)
    extension = Path(original_name).suffix if original_name else ".ogg"
    if not extension:
        extension = ".ogg"

    AUDIO_DIR.mkdir(exist_ok=True)
    audio_path = AUDIO_DIR / f"{update.effective_chat.id}_{message.message_id}{extension}"
    await file.download_to_drive(custom_path=str(audio_path))
    return audio_path


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed_chat(update):
        await update.message.reply_text("This bot is not enabled for this chat.")
        return

    chat_id = update.effective_chat.id
    message_id = update.effective_message.message_id

    audio_path = None
    mp3_path = None
    try:
        await update.message.reply_text("Received voice note. Downloading audio...")
        audio_path = await download_audio(update, context)
        mp3_path = convert_audio_to_mp3(audio_path)
        pending_audio_batches.setdefault(chat_id, []).append(str(mp3_path))

        if chat_id not in batch_tasks or batch_tasks[chat_id].done():
            await update.message.reply_text(
                f"Queued. I will wait {BATCH_WAIT_SECONDS}s for more voice notes and process together."
            )
            batch_tasks[chat_id] = asyncio.create_task(process_audio_batch(chat_id, context.bot))
        else:
            await update.message.reply_text("Added to current batch.")
    finally:
        if audio_path:
            safe_unlink(audio_path)


async def process_audio_batch(chat_id, bot):
    await asyncio.sleep(BATCH_WAIT_SECONDS)
    audio_files = pending_audio_batches.pop(chat_id, [])
    if not audio_files:
        return

    first_message_id = int(Path(audio_files[0]).stem.split("_")[-1])
    screenshot_path = SCREENSHOT_DIR / f"cart_{chat_id}_{first_message_id}.png"

    try:
        await bot.send_message(chat_id=chat_id, text="Transcribing and extracting groceries...")
        extraction = extract_items_from_audio_files(audio_files)
        items = extraction["items"]

        if not items:
            await bot.send_message(chat_id=chat_id, text="I could not find any grocery items in this batch.")
            return

        item_lines = []
        for item in items:
            name = item.get("name_en") or item.get("name_hi") or item.get("name")
            quantity = item.get("quantity", "1")
            item_lines.append(f"- {name} ({quantity})")

        await bot.send_message(chat_id=chat_id, text="Extracted items:\n" + "\n".join(item_lines))
        await bot.send_message(chat_id=chat_id, text="Creating Blinkit cart...")

        result = await asyncio.to_thread(ordering_backend.create_cart, items, str(screenshot_path))

        pending_approvals[chat_id] = {
            "items": items,
            "screenshot_path": str(screenshot_path),
            "result": result,
        }

        caption = "Blinkit cart is ready. Reply OK to approve or CANCEL to cancel.\n\nCheckout is disabled for now."
        if result.failed_items:
            failed = "\n".join(f"- {entry['item']}: {entry['error']}" for entry in result.failed_items)
            caption += "\n\nSome items failed:\n" + failed

        summary = result.raw.get("order_summary", {})
        cart_items = summary.get("cart_items", [])
        bill_lines = summary.get("bill_lines", [])
        cart_item_breakup = summary.get("cart_item_breakup", [])
        bill_breakup = summary.get("bill_breakup", [])
        summary_lines = ["Order summary breakup:"]
        if cart_item_breakup:
            summary_lines.append("Items:")
            for item in cart_item_breakup[:20]:
                name = item.get("name", "")
                variant = item.get("variant", "")
                quantity = item.get("quantity", 1)
                price = item.get("price", "")
                mrp = item.get("mrp", "")
                savings = item.get("savings", "")
                details = " | ".join(part for part in [variant, f"qty {quantity}", price] if part)
                if mrp:
                    details += f" (MRP {mrp}"
                    if savings:
                        details += f", saved {savings}"
                    details += ")"
                summary_lines.append(f"- {name}: {details}")
        elif cart_items:
            summary_lines.append("Items:")
            for line in cart_items[:20]:
                summary_lines.append(f"- {line}")
        if bill_breakup:
            summary_lines.append("Bill details:")
            for line in bill_breakup[:20]:
                label = line.get("label", "")
                amount = line.get("amount", "")
                details = line.get("details", "")
                value = amount or details
                summary_lines.append(f"- {label}: {value}")
        elif bill_lines:
            summary_lines.append("Bill details:")
            for line in bill_lines[:20]:
                summary_lines.append(f"- {line}")
        screenshot_parts = result.raw.get("screenshot_paths", [])
        for index, part_path in enumerate(screenshot_parts):
            with Path(part_path).open("rb") as screenshot:
                part_caption = caption if index == 0 else f"Cart screenshot part {index + 1}"
                await bot.send_photo(chat_id=chat_id, photo=screenshot, caption=part_caption)
            safe_unlink(part_path)
        await bot.send_message(chat_id=chat_id, text="\n".join(summary_lines))
    except Exception as exc:
        await bot.send_message(chat_id=chat_id, text=f"Batch failed: {exc}")
    finally:
        for mp3_file in audio_files:
            safe_unlink(mp3_file)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed_chat(update):
        await update.message.reply_text("This bot is not enabled for this chat.")
        return

    chat_id = update.effective_chat.id
    text = (update.message.text or "").strip().upper()

    if text == "OK":
        if chat_id not in pending_approvals:
            await update.message.reply_text("No cart is waiting for approval.")
            return

        pending_approvals.pop(chat_id, None)
        await update.message.reply_text("Approved. Checkout is currently disabled for safety.")
        return

    if text == "CANCEL":
        if chat_id in pending_approvals:
            pending_approvals.pop(chat_id, None)
            await update.message.reply_text("Cancelled. No order will be placed.")
        else:
            await update.message.reply_text("No cart is waiting for approval.")
        return

    await update.message.reply_text("Send a voice note, or reply OK / CANCEL when a cart is waiting.")


async def run_bot():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is missing in Backend/.env")

    AUDIO_DIR.mkdir(exist_ok=True)
    SCREENSHOT_DIR.mkdir(exist_ok=True)

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_audio))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    if TELEGRAM_POLL_SECONDS <= 0:
        print("Telegram bot polling started. Press Ctrl+C to stop.")
        stop_event = asyncio.Event()
        await stop_event.wait()
    else:
        print(f"Telegram bot polling started for {TELEGRAM_POLL_SECONDS} seconds...")
        await asyncio.sleep(TELEGRAM_POLL_SECONDS)
        print("Telegram bot polling finished.")

    await application.updater.stop()
    await application.stop()
    await application.shutdown()


def main():
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        print("\nTelegram bot stopped.")


if __name__ == "__main__":
    main()
