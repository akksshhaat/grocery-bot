# Blinkit Automation

Voice-note driven grocery automation for Blinkit. The backend can transcribe Hindi grocery audio, extract structured grocery items with OpenAI, add matching products to a Blinkit cart with Playwright, capture cart screenshots, and send an order breakup through Telegram.

## Features

- Transcribes grocery voice notes.
- Extracts grocery item names and quantities into JSON.
- Searches Blinkit and adds best-matching products to cart.
- Captures cart screenshots for review.
- Sends item and bill breakup through Telegram.
- Keeps checkout disabled for safety.

## Project Structure

```text
Backend/
  app.py              # Audio conversion, transcription, grocery extraction
  blinkit_bot.py      # Blinkit browser automation and cart screenshot capture
  order_backends.py   # Ordering backend wrapper
  telegram_bot.py     # Telegram bot entrypoint
  swiggyMCP.py        # Swiggy provider scaffold
  requirements.txt    # Python dependencies
```

Runtime folders such as `Backend/audio/`, `Backend/screenshots/`, and `Backend/blinkit-user-data/` are ignored by Git.

## Requirements

- Python 3.9+
- `ffmpeg`
- Playwright browser binaries
- OpenAI API key
- Telegram bot token, if using Telegram

## Setup

```bash
cd ~/Desktop/BlinkitAutomation
python3 -m venv .venv
source .venv/bin/activate
pip install -r Backend/requirements.txt
playwright install chromium
```

Create `Backend/.env`:

```bash
OPENAI_API_KEY=your_openai_api_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
ALLOWED_CHAT_ID=your_telegram_chat_id
TELEGRAM_POLL_SECONDS=300
TELEGRAM_BATCH_WAIT_SECONDS=20
```

`ALLOWED_CHAT_ID` is optional. If omitted, the Telegram bot accepts messages from any chat.

## Usage

### Extract groceries from local audio

Place `.mp3`, `.ogg`, or `.opus` audio files in `Backend/`, then run:

```bash
python Backend/app.py
```

### Create a Blinkit cart from local audio

```bash
python Backend/blinkit_bot.py
```

This opens Chromium with a persistent Blinkit profile under `Backend/blinkit-user-data/`. Log in once if Blinkit asks for it.

### Run the Telegram bot

```bash
python Backend/telegram_bot.py
```

Send a Hindi grocery voice note to the bot. It will batch nearby voice notes, create the cart, send a screenshot, and include the item and bill breakup.

## Safety Notes

- Checkout is currently disabled.
- Do not commit `Backend/.env`.
- The browser profile may contain session data and is intentionally ignored.
