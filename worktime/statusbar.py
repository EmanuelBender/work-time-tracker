"""Native macOS menu-bar item (NSStatusItem).

`QSystemTrayIcon` can't show a text title on macOS, so the live time + project
could only be hacked into the icon image — which the system mis-scaled and
clipped. We already depend on PyObjC, so we drive a real `NSStatusItem`: an
auto-sizing text title (clock glyph + "2:14 · Project") plus a richer dropdown
(current activity, today's per-project breakdown with colour dots, and totals).
"""

import AppKit
import objc

from .log import get_logger

log = get_logger("statusbar")


def _dot_image(hex_color, size=12):
    """A small filled circle in the project's colour, as an NSImage."""
    try:
        img = AppKit.NSImage.alloc().initWithSize_((size, size))
        img.lockFocus()
        r = int(hex_color[1:3], 16) / 255.0
        g = int(hex_color[3:5], 16) / 255.0
        b = int(hex_color[5:7], 16) / 255.0
        AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, 1.0).set()
        AppKit.NSBezierPath.bezierPathWithOvalInRect_(
            AppKit.NSMakeRect(1, 1, size - 2, size - 2)).fill()
        img.unlockFocus()
        img.setTemplate_(False)
        return img
    except Exception:
        return None


class _Target(AppKit.NSObject):
    """Receives the menu actions and forwards to Python callables."""

    def initWithOpen_quit_(self, on_open, on_quit):
        self = objc.super(_Target, self).init()
        if self is None:
            return None
        self._on_open = on_open
        self._on_quit = on_quit
        return self

    def openWindow_(self, _sender):
        try:
            self._on_open()
        except Exception:
            log.exception("open-from-menu failed")

    def quitApp_(self, _sender):
        try:
            self._on_quit()
        except Exception:
            log.exception("quit-from-menu failed")


class StatusBar:
    """A native menu-bar item with a readable title and a rich dropdown."""

    def __init__(self, on_open, on_quit):
        self._ok = False
        try:
            self._target = _Target.alloc().initWithOpen_quit_(on_open, on_quit)
            self._item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(
                AppKit.NSVariableStatusItemLength)
            button = self._item.button()
            symbol = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "clock", "WorktimeTracker")
            if symbol is not None:
                symbol.setTemplate_(True)
                button.setImage_(symbol)
                button.setImagePosition_(AppKit.NSImageLeading)
            button.setFont_(AppKit.NSFont.monospacedDigitSystemFontOfSize_weight_(
                13, AppKit.NSFontWeightMedium))
            self._menu = AppKit.NSMenu.alloc().init()
            self._menu.setAutoenablesItems_(False)
            self._item.setMenu_(self._menu)
            self._ok = True
        except Exception:
            log.exception("could not create NSStatusItem; menu-bar item disabled")

    def _disabled(self, title, color=None):
        it = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, None, "")
        it.setEnabled_(False)
        if color:
            img = _dot_image(color)
            if img is not None:
                it.setImage_(img)
        return it

    def _action(self, title, selector, key=""):
        it = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, selector, key)
        it.setTarget_(self._target)
        return it

    def update(self, title, now_text, now_color, projects, total_text):
        if not self._ok:
            return
        try:
            self._item.button().setTitle_(" " + title if title else "")
            m = self._menu
            m.removeAllItems()
            m.addItem_(self._disabled(now_text or "Idle", now_color))
            m.addItem_(AppKit.NSMenuItem.separatorItem())
            if projects:
                m.addItem_(self._disabled("Today"))
                for name, hhmm, color in projects:
                    m.addItem_(self._disabled(f"{name}     {hhmm}", color))
                m.addItem_(AppKit.NSMenuItem.separatorItem())
            if total_text:
                m.addItem_(self._disabled(total_text))
                m.addItem_(AppKit.NSMenuItem.separatorItem())
            m.addItem_(self._action("Open WorktimeTracker", "openWindow:"))
            m.addItem_(self._action("Quit", "quitApp:", "q"))
        except Exception:
            log.exception("status-bar update failed")
