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

def parse_grocery_json(grocery_output):
    cleaned_output = grocery_output.strip()
    if cleaned_output.startswith("```"):
        cleaned_output = cleaned_output.strip("`")
        cleaned_output = cleaned_output.removeprefix("json").strip()

    return json.loads(cleaned_output)

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
        "items": grocery_json.get("items", []),
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
