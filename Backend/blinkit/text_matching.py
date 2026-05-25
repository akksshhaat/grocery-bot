import re

def normalize_match_text(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()

def fuzzy_text_score(needle, haystack):
    needle_tokens = [token for token in normalize_match_text(needle).split() if len(token) >= 2]
    haystack_text = normalize_match_text(haystack)
    haystack_tokens = set(haystack_text.split())
    if not needle_tokens or not haystack_tokens:
        return 0

    score = 0
    for token in needle_tokens:
        if token in haystack_tokens:
            score += 4
        elif any(token in candidate or candidate in token for candidate in haystack_tokens if len(candidate) >= 3):
            score += 2

    if normalize_match_text(needle) and normalize_match_text(needle) in haystack_text:
        score += 8

    return score

def item_search_name(item):
    if isinstance(item, str):
        return item
    return item.get("name_en") or item.get("name_hi") or item.get("name")

class TextMatcher:
    normalize = staticmethod(normalize_match_text)
    fuzzy_score = staticmethod(fuzzy_text_score)
    item_search_name = staticmethod(item_search_name)
