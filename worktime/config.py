"""Configuration and tuning constants."""

import os

APP_NAME = "WorktimeTracker"

# Database lives in the standard macOS app-support location (override with env).
_SUPPORT_DIR = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
DB_PATH = os.environ.get("WORKTIME_DB", os.path.join(_SUPPORT_DIR, "worktime.db"))

# Sampling / session tuning (seconds). See PLAN.md "Defaults & tuning".
SAMPLE_INTERVAL = 5
IDLE_THRESHOLD = 120        # no input for this long => treat as away (not billed)
MIN_SESSION = 15            # discard sessions shorter than this (quick app flicks)
MAX_TICK_GAP = 30           # ticks silent for this long (sleep, lid, stall) => the
                            # machine wasn't being worked on; end the open session
MEDIA_IDLE_MAX = 1800       # playback (no-idle-sleep assertion) may extend a session
                            # past the idle threshold — listening passes, video review,
                            # calls — but never longer than this without any input
AX_MESSAGING_TIMEOUT = 2.0  # cap AX calls so a busy app (Logic) can't stall the loop

# Frontmost apps we never attribute (transient system UI) — see spike findings.
IGNORE_BUNDLES = {
    "com.apple.dock",
    "com.apple.Spotlight",
    "com.apple.notificationcenterui",
    "com.apple.controlcenter",
    "com.apple.WindowManager",
    "com.apple.loginwindow",
    "com.apple.ScreenSaver.Engine",
}


def support_dir():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return os.path.dirname(DB_PATH)
