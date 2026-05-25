import os

from dotenv import load_dotenv
from openai import OpenAI

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CART_ROOT_SELECTOR = '[class*="Cart___StyledDiv-sc-1ptvk5t-1"]'
CART_TITLE_SELECTOR = '[class*="CartWrapper__Title"]'
MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)

load_dotenv(os.path.join(BASE_DIR, ".env"))

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

PRODUCT_SELECTION_PROMPT = """
You choose the best Blinkit search result for an Indian grocery order.

Return STRICT JSON only:
{"index": 1, "reason": "short reason"}

Rules:
* index is 1-based from the candidate list
* choose the item that best matches the requested grocery item
* reject misleading brand/name matches, for example "Dairy Milk" is chocolate, not milk
* prefer plain staple groceries over snacks, sweets, accessories, or unrelated products
* if no candidate is a reasonable match, return {"index": 0, "reason": "no good match"}

"""
