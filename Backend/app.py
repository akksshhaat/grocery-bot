import json
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load environment variables

load_dotenv(os.path.join(BASE_DIR, ".env"))

# OpenAI client

client = OpenAI(
api_key=os.getenv("OPENAI_API_KEY")
)

def find_audio_files(directory=BASE_DIR):
    audio_extensions = {".mp3", ".ogg", ".opus"}
    return sorted(
        path
        for path in Path(directory).glob("*")
        if path.is_file() and path.suffix.lower() in audio_extensions
    )

# Prompt

SYSTEM_PROMPT = """
You are an Indian grocery assistant.

Extract ONLY grocery and household items.

Ignore:

* leave requests
* greetings
* casual conversation
* scheduling
* emotions

Return STRICT JSON only.

Format:
{
"items": [
{
"name_hi": "फूलगोभी",
"name_en": "cauliflower",
"quantity": "1"
}
]
}

Rules:

* name_hi should remain in Hindi
* name_en should be English translation
* quantity should be extracted if mentioned
* if quantity missing, use "1"
"""

def transcribe_audio(file_path):
    with open(file_path, "rb") as audio_file:
        transcript_response = client.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe",
            file=audio_file
        )
    return transcript_response.text

def convert_audio_to_mp3(file_path):
    source_path = Path(file_path)
    if source_path.suffix.lower() == ".mp3":
        return source_path

    mp3_path = source_path.with_suffix(".mp3")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-b:a",
            "64k",
            str(mp3_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return mp3_path

def extract_grocery_items(transcript):
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": transcript
            }
        ],
        temperature=0
    )
    return response.choices[0].message.content

def parse_cart_edit_command(message):
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": """
You classify short Telegram messages for a grocery cart approval flow.

Return STRICT JSON only.

Supported actions:
{
  "action": "add_item",
  "item_name": "maggi",
  "quantity": "2"
}

or:
{
  "action": "remove_item",
  "item_name": "diet coke",
  "quantity": ""
}

or:
{
  "action": "none",
  "item_name": "",
  "quantity": ""
}

Rules:
* Use add_item only when the user clearly wants an item added/put/included in the cart.
* Use remove_item only when the user clearly wants an item removed/deleted/taken out from the cart.
* Extract the grocery/product name in simple English.
* For add_item, extract quantity if mentioned. If missing, use "1".
* For remove_item, quantity can be empty unless the user clearly mentions removing a specific count.
* If the message is an address hint, approval, cancellation, greeting, question, or unclear, return action none.
* Do not invent an item name.
""",
            },
            {
                "role": "user",
                "content": message,
            },
        ],
        temperature=0,
    )

    try:
        parsed = json.loads(response.choices[0].message.content)
    except Exception:
        return {"action": "none", "item_name": "", "quantity": ""}

    if parsed.get("action") not in {"add_item", "remove_item"} or not parsed.get("item_name"):
        return {"action": "none", "item_name": "", "quantity": ""}

    return {
        "action": parsed.get("action"),
        "item_name": str(parsed.get("item_name", "")).strip(),
        "quantity": str(parsed.get("quantity") or ("1" if parsed.get("action") == "add_item" else "")).strip(),
    }

def parse_grocery_json(grocery_output):
    cleaned_output = grocery_output.strip()
    if cleaned_output.startswith("```"):
        cleaned_output = cleaned_output.strip("`")
        cleaned_output = cleaned_output.removeprefix("json").strip()

    return json.loads(cleaned_output)

DEFAULT_SABZI_ITEMS = [
    {"name_hi": "फूलगोभी", "name_en": "gobhi", "quantity": "1"},
    {"name_hi": "भिंडी", "name_en": "bhindi", "quantity": "1"},
    {"name_hi": "बीन्स", "name_en": "beans", "quantity": "1"},
    {"name_hi": "गाजर", "name_en": "carrot", "quantity": "1"},
]

SABZI_NAMES = {
    "sabzi",
    "sabji",
    "sabjis",
    "vegetable",
    "vegetables",
    "mixed vegetables",
    "सब्जी",
    "सब्जियां",
    "सब्जियाँ",
}

def expand_default_sabzi_items(items):
    expanded_items = []
    for item in items:
        if isinstance(item, str):
            item_name = item
        else:
            item_name = " ".join(
                str(item.get(key, ""))
                for key in ("name_en", "name_hi", "name")
            )

        normalized_name = item_name.lower().strip()
        if normalized_name in SABZI_NAMES or any(name in normalized_name.split() for name in SABZI_NAMES):
            expanded_items.extend(DEFAULT_SABZI_ITEMS)
        else:
            expanded_items.append(item)

    return expanded_items

def extract_items_from_audio_files(audio_paths):
    transcript_parts = []
    for audio_path in audio_paths:
        mp3_path = convert_audio_to_mp3(audio_path)
        transcript_parts.append(transcribe_audio(str(mp3_path)))

    transcript = "\n".join(transcript_parts)
    grocery_output = extract_grocery_items(transcript)
    grocery_json = parse_grocery_json(grocery_output)
    return {
        "transcript": transcript,
        "items": expand_default_sabzi_items(grocery_json.get("items", [])),
    }

def main():
    audio_files = find_audio_files()
    if not audio_files:
        print("\nNo audio files found.")
        return

    print("\nReading audio notes:")
    for audio_file in audio_files:
        print(f"- {audio_file.name}")

    result = extract_items_from_audio_files(audio_files)
    transcript = result["transcript"]
    print("\nTranscript:")
    print(transcript)
    print("\nExtracting grocery items...")
    try:
        print("\nFinal Grocery JSON:")
        print(json.dumps({"items": result["items"]}, indent=2, ensure_ascii=False))
    except Exception as e:
        print("\nFailed to parse JSON")
        print(e)
if __name__ == "__main__":
    main()
