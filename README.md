# Blinkit Automation

Voice-note driven grocery automation for Blinkit. The backend can transcribe Hindi grocery audio, extract structured grocery items with OpenAI, add matching products to a Blinkit cart with Playwright, send a clean receipt-style cart review through Telegram, and place a COD checkout after approval.

## Features

- Transcribes grocery voice notes.
- Extracts grocery item names and quantities into JSON.
- Searches Blinkit and adds best-matching products to cart.
- Sends a clean receipt image for cart review.
- Sends item and bill breakup through Telegram.
- Clears accidental delivery tips before review and checkout.
- Selects saved delivery addresses using fuzzy address-hint matching.
- Places Cash on Delivery orders after Telegram approval.
- Leaves the checkout browser open briefly for inspection after checkout attempts.

## Project Structure

```text
Backend/
  app.py              # Audio conversion, transcription, grocery extraction
  blinkit_bot.py      # Blinkit browser automation, receipt rendering, COD checkout
  order_backends.py   # Ordering backend wrapper
  telegram_bot.py     # Telegram bot entrypoint
  swiggyMCP.py        # Swiggy provider scaffold
  requirements.txt    # Python dependencies
```

Runtime folders such as `Backend/audio/`, `Backend/screenshots/`, and `Backend/blinkit-user-data/` are ignored by Git. The browser profile can contain active Blinkit session data.

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

## Getting API Keys

### OpenAI API key

This project needs an OpenAI API key for transcription and grocery extraction.

1. Open the OpenAI API dashboard: [platform.openai.com/api-keys](https://platform.openai.com/api-keys)
2. Sign in and select the project you want to use.
3. Create a new API key.
4. Copy it once and store it in `Backend/.env`:

```bash
OPENAI_API_KEY=sk-...
```

OpenAI treats API keys as secrets. Do not paste this key into Telegram, frontend code, screenshots, or commits. Official OpenAI authentication docs: [API keys](https://platform.openai.com/docs/api-reference/authentication/api-keys).

### Telegram bot token

This project needs a Telegram bot token so it can receive voice notes and send cart receipts.

1. Open Telegram and search for the official `@BotFather`.
2. Send:

```text
/newbot
```

3. Follow the prompts for bot name and username.
4. BotFather will return an HTTP API token.
5. Add it to `Backend/.env`:

```bash
TELEGRAM_BOT_TOKEN=123456789:AA...
```

Official Telegram docs: [BotFather bot creation](https://core.telegram.org/bots/features).

### Telegram chat ID

Use `ALLOWED_CHAT_ID` to restrict the bot to your Telegram chat.

Quick way:

1. Start your bot in Telegram and send it any message.
2. In a browser, open this URL after replacing the token:

```text
https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates
```

3. Find `message.chat.id` in the JSON response.
4. Add it to `Backend/.env`:

```bash
ALLOWED_CHAT_ID=123456789
```

If `getUpdates` returns an empty result, send another message to your bot and refresh the URL.

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

Send a Hindi grocery voice note to the bot. It will batch nearby voice notes, create the cart, send a receipt image, and include the item and bill breakup.

Checkout flow:

1. Send grocery voice note.
2. Wait for the cart receipt.
3. Send an address hint, for example:

```text
flat F801
```

4. Reply:

```text
OK
```

The bot reopens Blinkit, fuzzy-matches the hint against saved addresses, clears any selected tip, selects Cash, and clicks Pay Now for COD checkout. Reply `CANCEL` before `OK` to discard the pending cart.

## Checkout Notes

- Address matching is fuzzy, not exact. Hints like `F801`, `tower 2 F801`, or `flat F801` can match a saved address containing those tokens.
- COD selection happens inside Blinkit's/Zomato's payment iframe.
- After checkout succeeds or fails, the browser is left open for inspection for about 10 minutes. Close it manually when done.
- Live checkout can place a real order. Use the `OK` approval message only when the cart, address hint, and total look correct.

## Safety Notes

- Do not commit `Backend/.env`.
- The browser profile may contain session data and is intentionally ignored.
- Review the receipt and address hint carefully before replying `OK`.
