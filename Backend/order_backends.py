from dataclasses import dataclass
from typing import Optional

from blinkit_bot import run_blinkit_order


@dataclass
class OrderResult:
    provider: str
    success: bool
    screenshot_path: Optional[str]
    added_items: list
    failed_items: list
    raw: dict


class BlinkitProvider:
    def create_cart(self, items, screenshot_path):
        data = run_blinkit_order(items, screenshot_path=screenshot_path)
        return {
            "success": True,
            "data": data,
        }


class OrderingBackend:
    def __init__(self):
        self.blinkit = BlinkitProvider()

    def create_cart(self, items, screenshot_path):
        blinkit_result = self.blinkit.create_cart(items, screenshot_path=screenshot_path)
        data = blinkit_result["data"]
        return OrderResult(
            provider="blinkit",
            success=blinkit_result.get("success", False),
            screenshot_path=screenshot_path,
            added_items=data.get("added_items", []),
            failed_items=data.get("failed_items", []),
            raw=data,
        )
