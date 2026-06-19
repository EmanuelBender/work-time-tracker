#!/usr/bin/env python3
"""
WorktimeTracker — detection spike.

Answers the make-or-break question: for each app you actually work in
(Logic Pro, Photoshop, Blender, ...), can we see the open document's file path?

Because you can't watch live Terminal output while another app is frontmost,
this logs to `probe_log.txt` and records only *transitions* (when the frontmost
app / document / window title changes). So:

    1. ./.venv/bin/python detect_probe.py
    2. Click into Logic Pro (real project open), wait ~3s.
    3. Click into Photoshop, wait ~3s. Then Blender, a browser, Mail, etc.
    4. Come back to Terminal, press Ctrl-C.
    5. Tell Claude you're done — it reads probe_log.txt.

First run triggers a one-time Accessibility prompt for your Terminal. Grant it
(System Settings > Privacy & Security > Accessibility), reopen Terminal, re-run.
"""

import datetime
import subprocess
import sys
import time

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

AX_FOCUSED_WINDOW = "AXFocusedWindow"
AX_DOCUMENT = "AXDocument"
AX_TITLE = "AXTitle"

LOG_PATH = "probe_log.txt"
SELF_PREFIX = "/Volumes/4TB HighSpeed/PROJECTS/_PROJECTS/WorktimeTracker"


def _ax_value(element, attribute):
    try:
        err, value = AXUIElementCopyAttributeValue(element, attribute, None)
    except Exception:
        return None
    return value if err == 0 else None


def focused_doc_and_title(pid):
    app_el = AXUIElementCreateApplication(pid)
    # Critical: cap how long an AX call may block, or a busy app (e.g. Logic)
    # can freeze the whole loop. 2s is generous; real reads are instant.
    try:
        AXUIElementSetMessagingTimeout(app_el, 2.0)
    except Exception:
        pass
    window = _ax_value(app_el, AX_FOCUSED_WINDOW)
    if window is None:
        return None, None
    return _ax_value(window, AX_DOCUMENT), _ax_value(window, AX_TITLE)


def open_files_via_lsof(pid, limit=8):
    try:
        out = subprocess.run(
            ["lsof", "-p", str(pid), "-F", "tn"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return []
    files, is_reg = [], False
    for line in out.splitlines():
        tag, val = line[:1], line[1:]
        if tag == "t":
            is_reg = (val == "REG")
        elif tag == "n" and is_reg:
            if val.startswith(("/Users/", "/Volumes/")) and not val.startswith(SELF_PREFIX):
                files.append(val)
    seen, uniq = set(), []
    for f in files:
        if f not in seen:
            seen.add(f); uniq.append(f)
    return uniq[:limit]


def idle_seconds():
    return CGEventSourceSecondsSinceLastEventType(
        kCGEventSourceStateHIDSystemState, kCGAnyInputEventType
    )


def frontmost_pid_and_name():
    """Live frontmost app via the window server (no run loop needed).

    NSWorkspace.frontmostApplication() goes stale in a CLI process; the window
    list is ordered front-to-back, so the first normal-layer (layer 0) window's
    owner is the genuinely active app.
    """
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
            name = win.get("kCGWindowOwnerName")
            if pid is not None:
                return int(pid), str(name) if name is not None else None
    return None, None


def sample():
    pid, owner_name = frontmost_pid_and_name()
    if pid is None:
        return None
    ra = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid)
    name = (ra.localizedName() if ra else None) or owner_name
    bundle = ra.bundleIdentifier() if ra else None
    doc, title = focused_doc_and_title(pid)
    return {
        "name": name,
        "bundle": bundle,
        "pid": pid,
        "title": title,
        "doc": doc,
        "files": open_files_via_lsof(pid),
    }


def render(rec):
    lines = [
        f"app    : {rec['name']}  [{rec['bundle']}]",
        f"title  : {rec['title']!r}",
        f"AXDoc  : {rec['doc']!r}",
    ]
    if rec["files"]:
        lines.append("lsof   :")
        lines += [f"         {f}" for f in rec["files"]]
    else:
        lines.append("lsof   : (no user document files detected)")
    return "\n".join(lines)


def key(rec):
    # a transition = change in app / document / title
    return (rec["bundle"], rec["doc"], rec["title"]) if rec else None


def main():
    trusted = AXIsProcessTrusted()
    header = []
    if not trusted:
        header.append("WARNING: Accessibility NOT granted — AXDoc/title will be empty.")
        header.append("Grant Terminal in System Settings > Privacy & Security > Accessibility, then re-run.")

    with open(LOG_PATH, "w") as log:
        for h in header:
            print(h); log.write(h + "\n")
        msg = "probe running — switch between your apps now; Ctrl-C when done.\n"
        print(msg); log.write(msg); log.flush()

        last = object()
        ticks = 0
        try:
            while True:
                ticks += 1
                try:
                    rec = sample()
                except Exception as e:
                    rec = None
                    print(f"[sample error] {e}")
                if rec is not None and key(rec) != last:
                    last = key(rec)
                    stamp = datetime.datetime.now().strftime("%H:%M:%S")
                    block = f"[{stamp}] idle={idle_seconds():.0f}s\n{render(rec)}\n" + "-" * 60
                    print(block); log.write(block + "\n"); log.flush()
                # heartbeat so you can see the loop is alive (stdout only)
                here = rec["name"] if rec else "?"
                print(f"\r  tick {ticks:>4}  front={here:<24}", end="", flush=True)
                time.sleep(1)
        except KeyboardInterrupt:
            bye = "\nstopped."
            print(bye); log.write(bye + "\n")


if __name__ == "__main__":
    main()
