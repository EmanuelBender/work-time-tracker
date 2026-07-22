"""Live activity detection — the validated detection-spike logic, promoted.

Key lessons baked in (see PLAN.md "Detection spike findings"):
  - frontmost app must come from the window server (NSWorkspace goes stale in a
    long-running process with no run loop);
  - the project document lives on the main window, so scan ALL windows and keep
    the value sticky per app (plugin/mixer focus must not drop the project);
  - cap AX messaging time so a busy app can't freeze the loop.
"""

import os
import re
import subprocess
import urllib.parse

from AppKit import NSRunningApplication
from ApplicationServices import (
    AXIsProcessTrusted,
    AXUIElementCopyAttributeValue,
    AXUIElementCreateApplication,
    AXUIElementSetMessagingTimeout,
)
from Quartz import (
    CGEventSourceSecondsSinceLastEventType,
    CGWindowListCopyWindowInfo,
    kCGAnyInputEventType,
    kCGEventSourceStateHIDSystemState,
    kCGNullWindowID,
    kCGWindowListOptionOnScreenOnly,
)

from . import config

AX_WINDOWS = "AXWindows"
AX_FOCUSED_WINDOW = "AXFocusedWindow"
AX_DOCUMENT = "AXDocument"
AX_TITLE = "AXTitle"


def accessibility_ok():
    return bool(AXIsProcessTrusted())


def idle_seconds():
    return float(CGEventSourceSecondsSinceLastEventType(
        kCGEventSourceStateHIDSystemState, kCGAnyInputEventType
    ))


def _ax(element, attribute):
    try:
        err, value = AXUIElementCopyAttributeValue(element, attribute, None)
    except Exception:
        return None
    return value if err == 0 else None


def _normalize_doc(doc):
    """file:// URL (percent-encoded, package trailing slash) -> plain path."""
    if not doc:
        return None
    path = str(doc)
    if path.startswith("file://"):
        path = urllib.parse.unquote(urllib.parse.urlparse(path).path)
    return path.rstrip("/") or None


# bundle id -> (AppleScript app name, dialect). Firefox has no usable AppleScript.
BROWSERS = {
    "com.apple.Safari": ("Safari", "safari"),
    "com.apple.SafariTechnologyPreview": ("Safari Technology Preview", "safari"),
    "com.google.Chrome": ("Google Chrome", "chrome"),
    "com.google.Chrome.canary": ("Google Chrome Canary", "chrome"),
    "com.brave.Browser": ("Brave Browser", "chrome"),
    "com.microsoft.edgemac": ("Microsoft Edge", "chrome"),
    "com.vivaldi.Vivaldi": ("Vivaldi", "chrome"),
    "company.thebrowser.Browser": ("Arc", "chrome"),
}


def browser_url(bundle):
    """Current tab URL of the frontmost browser via AppleScript, or None.

    Requires Automation permission for that browser (macOS prompts once); until
    granted, or for unsupported browsers, this returns None — never raises.
    """
    info = BROWSERS.get(bundle)
    if not info:
        return None
    app_name, dialect = info
    tab = "current tab" if dialect == "safari" else "active tab"
    script = f'tell application "{app_name}" to get URL of {tab} of front window'
    try:
        out = subprocess.run(["osascript", "-e", script],
                             capture_output=True, text=True, timeout=2)
        url = out.stdout.strip()
        return url or None
    except Exception:
        return None


# Power assertions that mean "media is actually running". UserIsActive and
# system/background assertions are deliberately absent.
_MEDIA_ASSERTIONS = {
    "PreventUserIdleSystemSleep", "PreventUserIdleDisplaySleep",
    "NoIdleSleepAssertion", "NoDisplaySleepAssertion",
}

_ASSERTION_LINE = re.compile(
    r'\s*pid (\d+)\(.*?\): \[[^\]]*\] [\d:]+ (\w+) named: "(.*?)"')


def _media_pids(pmset_output):
    """pids effectively holding a no-idle-sleep assertion (media running).

    Two quirks, both observed live: coreaudiod holds audio assertions on
    behalf of the playing app — the 'Created for PID:' continuation line
    names the real owner (this is how Logic playback maps to Logic). And
    Electron apps hold a *permanent* NoIdleSleepAssertion named "Electron"
    with nothing playing — ignored, or they would never idle.
    """
    pids, last_was_media = set(), False
    for line in pmset_output.splitlines():
        m = _ASSERTION_LINE.match(line)
        if m:
            pid, kind, name = int(m.group(1)), m.group(2), m.group(3)
            last_was_media = kind in _MEDIA_ASSERTIONS and name != "Electron"
            if last_was_media:
                pids.add(pid)
            continue
        m = re.search(r"Created for PID: (\d+)", line)
        if m and last_was_media:
            pids.add(int(m.group(1)))
    return pids


def media_active(pid):
    """True if this app is audibly/visibly playing — it (or coreaudiod on its
    behalf) holds a no-idle-sleep power assertion. Lets listening passes,
    video review, and calls count as work despite no keyboard/mouse input."""
    if pid is None:
        return False
    try:
        out = subprocess.run(["pmset", "-g", "assertions"],
                             capture_output=True, text=True, timeout=2)
        return pid in _media_pids(out.stdout)
    except Exception:
        return False


def frontmost():
    """(pid, owner_name) of the genuinely active app via the window server."""
    info = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID)
    if not info:
        return None, None
    for win in info:
        try:
            layer = int(win.get("kCGWindowLayer", 0))
        except Exception:
            layer = 0
        if layer == 0:
            pid = win.get("kCGWindowOwnerPID")
            if pid is not None:
                return int(pid), win.get("kCGWindowOwnerName")
    return None, None


def _document_and_title(pid):
    """Scan all of the app's windows for one bearing an AXDocument; plus title."""
    app_el = AXUIElementCreateApplication(pid)
    try:
        AXUIElementSetMessagingTimeout(app_el, config.AX_MESSAGING_TIMEOUT)
    except Exception:
        pass
    doc = None
    for w in (_ax(app_el, AX_WINDOWS) or []):
        d = _ax(w, AX_DOCUMENT)
        if d:
            doc = d
            break
    focused = _ax(app_el, AX_FOCUSED_WINDOW)
    title = _ax(focused, AX_TITLE) if focused is not None else None
    return _normalize_doc(doc), (str(title) if title else None)


class Detector:
    """Stateful sampler that makes the flickering AXDocument sticky per app."""

    def __init__(self):
        self._sticky = {}   # pid -> last known document path

    def media_active(self, pid):
        return media_active(pid)

    def sample(self):
        """Return an activity dict, or None for ignored/transient frontmost."""
        pid, owner = frontmost()
        if pid is None:
            return None
        if pid == os.getpid():
            return None  # don't track time spent in WorktimeTracker's own window
        ra = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
        bundle = ra.bundleIdentifier() if ra else None
        name = (ra.localizedName() if ra else None) or owner

        if bundle in config.IGNORE_BUNDLES:
            return None  # transient system UI -> no state change

        doc, title = _document_and_title(pid)
        if doc:
            self._sticky[pid] = doc
        else:
            doc = self._sticky.get(pid)   # keep project across plugin/mixer focus

        return {
            "pid": pid,
            "app_bundle": bundle,
            "app_name": name,
            "title": title,
            "file_path": doc,
            "url": browser_url(bundle),
            "idle_seconds": idle_seconds(),
        }
