import json
import os

import httpx

from blinkit import TextMatcher


class SwiggyMCPProvider:
    def __init__(self):
        self.base_url = os.getenv("SWIGGY_MCP_BASE_URL", "").strip()
        self.auth_token = os.getenv("SWIGGY_MCP_AUTH_TOKEN", "").strip()
        self.timeout_seconds = float(os.getenv("SWIGGY_MCP_TIMEOUT_SECONDS", "45"))

    @property
    def configured(self):
        return bool(self.base_url and self.auth_token)

    def create_cart(self, items):
        if not self.configured:
            return {
                "success": False,
                "error": "Swiggy MCP is not configured.",
            }

        payload = {
            "items": [
                {
                    "name": TextMatcher.item_search_name(item),
                    "quantity": item.get("quantity", "1") if isinstance(item, dict) else "1",
                    "raw_item": item,
                }
                for item in items
            ],
            "human_approval_required": True,
        }

        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(self.base_url, headers=headers, json=payload)

        if response.status_code >= 400:
            return {
                "success": False,
                "error": f"Swiggy MCP HTTP {response.status_code}",
                "response_text": response.text,
            }

        try:
            data = response.json()
        except json.JSONDecodeError:
            data = {"raw_text": response.text}

        success = bool(data.get("success", True))
        return {
            "success": success,
            "data": data,
        }
