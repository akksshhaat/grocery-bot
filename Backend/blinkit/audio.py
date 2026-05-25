import json

from app import extract_items_from_audio_files, find_audio_files

def get_grocery_items_from_audio():
    audio_files = find_audio_files()
    if not audio_files:
        print("\nNo audio files found.")
        return []

    print("\nReading audio notes:")
    for audio_file in audio_files:
        print(f"- {audio_file.name}")

    result = extract_items_from_audio_files(audio_files)
    transcript = result["transcript"]
    print("\nTranscript:")
    print(transcript)

    print("\nFinal Grocery JSON:")
    grocery_items = result["items"]
    print(json.dumps({"items": grocery_items}, indent=2, ensure_ascii=False))
    return grocery_items

class AudioGroceryReader:
    get_items = staticmethod(get_grocery_items_from_audio)
