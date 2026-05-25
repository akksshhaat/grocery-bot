from .constants import BASE_DIR, MOBILE_USER_AGENT

import os

def launch_blinkit_context(playwright, mobile=True, checkout=False):
    context_options = {
        "user_data_dir": os.path.join(BASE_DIR, "blinkit-user-data"),
        "headless": False,
    }
    if checkout:
        context_options.update(
            {
                "viewport": {"width": 400, "height": 648},
                "device_scale_factor": 1,
                "is_mobile": False,
                "has_touch": False,
            }
        )
    elif mobile:
        context_options.update(
            {
                "viewport": {"width": 390, "height": 844},
                "device_scale_factor": 2,
                "is_mobile": True,
                "has_touch": True,
                "user_agent": MOBILE_USER_AGENT,
            }
        )
    else:
        context_options.update(
            {
                "viewport": {"width": 1365, "height": 900},
                "device_scale_factor": 1,
                "is_mobile": False,
                "has_touch": False,
            }
        )

    return playwright.chromium.launch_persistent_context(**context_options)

class BlinkitBrowser:
    launch_context = staticmethod(launch_blinkit_context)
