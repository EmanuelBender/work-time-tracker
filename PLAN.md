# WorktimeTracker — Build Plan

A lean macOS menu-bar app that automatically tracks how much time you spend
working on each freelance project.

> **Core model:** a *project* is a folder (one employer/project per folder).
> *Work* is active time spent with that project's documents open — extended by
> rules and manual input to also capture browser, email, AI-agent, call, and
> messaging time that has no project file.

**North star for v1:** a trustworthy **effective-wage gauge**. Projects are
paid a fixed fee, not by the hour — the number that matters is
fee ÷ billable hours: is this project still paying well, or is it eating too
much time? Per-project totals + CSV export back it up.

---

## Key decisions (locked)

| Decision | Choice | Why |
|---|---|---|
| Tracking style | **Automatic + manual fallback** | Auto is primary; you can correct, start/stop manually, and assign untracked blocks before billing. |
| Engine | **Python** (PyObjC + stdlib `sqlite3`) — **validated** | Detection proven on real apps; this is the core and it stays. |
| GUI | **Python + PySide6 (Qt)** — one stack for the menu-bar item *and* the windows | Single event loop → no `rumps`/webview run-loop conflict (the main source of jank). Mature widgets + charts + native dialogs. Chosen over a Swift rewrite to avoid throwing away working code (user's call, 2026-06-18). Web UI (pywebview) is the fallback if a web look is preferred. |
| Primary interaction | **Review-and-assign** (not upfront rule config) | Track everything → bucket the unknowns → assign with one click → assignment can become a rule. No rule ever has to be defined in advance. |
| Storage | **SQLite**, local-only (`sqlite3` now, GRDB if we port) — versioned via `PRAGMA user_version` migrations | Time entries are append-only; no cloud, data stays on your machine. |
| Project = | A registered **folder** with employer + optional fixed **fee** (EUR) | Matches existing organization; zero manual tagging for file work. |
| Billing model | **Fixed fee per project** (decided 2026-07-22) | Freelance payment here is per project, not per hour. The app derives the *effective wage* (fee ÷ lifetime billable hours) per project — the health signal shown in Reports. |

> **Python caveat (personal use only):** macOS attaches the Accessibility
> permission to whatever runs the script (the Terminal app or the Python
> binary), not to a clean app icon. Fine for a tool you run yourself — and one
> of the reasons we'd port to Swift for a real distributable app.

---

## The attribution engine (the heart of it)

You do **not** tag every email, call, or message by hand. The app attributes
work in three ways, ordered by confidence, and *learns* so the manual cost
shrinks toward zero.

**Resolution chain** (first match wins), sampling *(frontmost app, document path,
browser URL, window title, idle?)* every few seconds:

1. **File match** (auto, no setup) — an open document under a registered project
   folder. Covers the bulk of billable work with zero tagging.
2. **Learned rule** (taught once) — an identifier mapped to a project: browser
   URL/domain, title keyword, or whole app. A handful per employer; thereafter
   automatic.
3. **Title match** (auto, no setup — added v0.3.0) — a registered project name
   or folder basename appears in the window title: Terminal/agent sessions
   showing a cwd, Blender's path-in-title, mail subjects naming the project.
   Min-length guard; longest candidate wins.
4. **Session inference** (suggested, not billed) — none of the above, but you
   were *just* in a strong project context, so adjacent non-file work is
   *proposed* for that project. Expires 30 min after the last strong signal.
5. **Unassigned** — nothing matched → bucket for quick review.

**Confidence tiers keep billing trustworthy:**
- **Auto-billable:** file match, learned rule, title match, manual blocks/edits.
- **Suggested (1-click confirm):** session inference, repeated-pattern guesses.
- **Unknown:** unassigned — you pick.

**Attribution coverage** (Reports footer) tracks how much time attributed
itself vs. needed the user — the number that decides where accuracy work goes
next.

**Teach-once loop:** when you assign an unattributed block to a project, the app
offers to remember the mapping as a rule (this domain / number / URL / app →
this project). Manual effort is front-loaded and decays as rules accumulate.

Idle slices (no input past a threshold) are dropped, never billed — with one
deliberate exception: if the frontmost app is actually *playing* (it holds a
no-idle-sleep power assertion), the session continues. Listening passes, video
review, and calls are work; the grace is capped at 30 min without input.

**Mechanism:** the sampler is an **in-memory state machine**, not a row-per-tick
logger. It holds the current activity; when the resolved *(project, app, file/url,
idle)* changes, it closes the open `Session` and starts a new one. Only `Session`
rows hit the database — lean and cheap.

### Defaults & tuning (all configurable later)
- Sample interval: **5 s**
- AFK / idle threshold: **2 min** (no input → stop counting)
- Minimum session length: **15 s** (ignore quick app flicks)
- Max tick gap: **30 s** — silent ticks (sleep, lid, stalls) end the open
  session at the last live sample; gaps are never billed
- Media grace: playback extends past idle, at most **30 min** without input
- Title match: candidates ≥ **5 chars**; inference context TTL **30 min**
- Target rate: **80 €/h** — the wage-health benchmark colouring Reports

### Detection spike findings (validated 2026-06-18; the spike script is
### retired — its logic lives on in `detector.py`)
Real data from the user's machine. The mechanism is proven; these are the rules
it taught us.

- ✅ **Frontmost app:** must come from the **window server**
  (`CGWindowListCopyWindowInfo`, first layer-0 window). `NSWorkspace.frontmost
  Application()` goes **stale** in a long-running CLI/agent process (no run loop).
- ✅ **Logic Pro:** `AXDocument` returns the real `.logicx` path — confirmed on a
  live project: `…/Pandoras Play/Last Christmas/Last Christmas.logicx/` on the
  external 4TB drive. File-match works. **Caveat:** only the main project window
  carries it — plugin/mixer/Startup windows return `None`, so the value
  **flickers**. Fix: scan **all** app windows (`AXWindows`) for one bearing a
  document, and keep the last-known document **sticky per app** until the app
  closes/changes it.
- 📁 **Project folders nest as employer → project** (`Pandoras Play/Last
  Christmas`) and live under `/Volumes/...`. Registration must support both
  "this folder = one project" and "this folder = an employer, each subfolder =
  a project." Folder matching must handle `/Volumes` paths and spaces.
- ❌ **Electron apps (Claude, Codex, and similar AI tools):** `AXDocument` is
  empty, `lsof` shows only GPU-cache noise, window title is useless (`'Claude'`).
  → app-rule + manual project assignment (Phase 4).
- ✉️ **Mail:** no document, but the window title carries the **email subject**
  (`'Re: Aufnahmen'`) and mailbox name. → subject/mailbox → project keyword
  rules (Phase 4).
- 🌐 **Safari:** window title is the **page title** (`'OFFICE — FINANCE - Google
  Sheets'`); `AXDocument` empty, lsof cache-only. For real attribution, read the
  tab **URL** via AppleScript. → URL/title rules (Phase 4).
- 📞 **Telephone (VoIP softphone):** the user's **calls**. Title names the line
  (`'Mac to FritzBox Landline'`) and may name the callee. → app/title rules (P4).
- 🧹 **Noise to ignore:** Dock, Finder transients, Calendar, Spotlight,
  Notification Centre, screensaver, our own Terminal — ignore-list + min dwell.
- 🔤 **Path normalization:** AXDocument is a `file://` URL, percent-encoded, with
  a trailing slash for packages (`.logicx`). Strip scheme, URL-decode, trim.
- ⏳ **Not yet tested:** Photoshop, Blender (likely AXDocument and title-parse
  respectively — confirm with a quick probe before/during Phase 1).

---

## Phases

Ordered to reach the billing output fast via a thin end-to-end slice, then
deepen accuracy and coverage. Check items off as we go.

### Phase 0 — Foundation & scaffolding  ✅ (built 2026-06-18)
- [x] Python project: `rumps` menu-bar app skeleton + virtualenv + deps.
- [x] SQLite schema + migrations.
- [x] Data model (lean, 3 tables):
      `Project(id, name, folder, employer, hourlyRate?, currency, color)`,
      `Session(id, projectId?, appBundleId, appName, title?, filePath?, url?, start, end, billable, confidence)`,
      `Rule(id, projectId, kind, pattern)`  ← used from Phase 4 (app / url rules).
      `confidence ∈ {auto-file, auto-rule, manual, inferred, unassigned}`.
- [x] Accessibility permission check + onboarding (`AXIsProcessTrusted`).
- [x] Project registration (folder, employer, fee) — now GUI-only.
      ↳ TODO: "folder = employer, each subfolder = a project" auto-split + edit UI.

### Phase 1 — Core detection (thin slice)  ✅ mostly built (2026-06-18)
- [x] Sampling loop on a timer (default 5 s).
- [x] Frontmost app via **window server** (`CGWindowListCopyWindowInfo`), not
      `NSWorkspace` (which goes stale without a run loop).
- [x] Idle detection via HID idle time (default AFK threshold 2 min).
- [x] Document detection: scan **all** app windows (`AXWindows`) for one with an
      `AXDocument`; **sticky per app** so plugin/mixer focus doesn't drop it.
      AX messaging timeout set so a busy app can't stall the loop.
- [x] Normalize document URLs (strip `file://`, percent-decode, trailing slash).
- [ ] `lsof` open-file scan as a secondary fallback (filter cache/system noise).
- [x] Ignore-list for system UI (Dock, Spotlight, screensaver, etc.) + min dwell.
- [x] Attribution chain steps 1 + 2 + 5 (file match + learned rule + unassigned).
- [x] State machine emits `Session` rows on activity change; drop sessions
      shorter than the 15 s minimum.
- [x] Fixed: window-title flicker no longer fragments sessions (title removed
      from session identity — this was the "only Claude got captured" bug). Also
      ignore WorktimeTracker's own window.
- [ ] Verify live against real apps (Logic, etc.) end-to-end on the user's Mac.

### Phase 1.5 — GUI (PySide6)  ✅ built (2026-06-18) — dark theme
Replaces the spike's CLI + rumps. Built on the (unchanged) detection engine.
**Review-and-assign is the core.** Layout: status bar + project rail + 3 views.
- [x] One PySide6 app: `QSystemTrayIcon` (live today-total drawn into the icon;
      menu shows current project + today) + main window. Single event loop,
      tracker on a background thread. Dark theme.
- [x] Status bar: current activity + Today + Billable-today metrics.
- [x] **Projects** view: add/edit, native folder picker, employer, rate, and
      **multiple folders per project** (add/remove).
- [x] **Review** view: project rail (colours + today hours) + sessions table;
      unassigned highlighted; assign inline (colour chip); one-click rule.
- [x] **Reports** view: per-project totals (Today / 7 days / month) + CSV export.
- [x] `cli.py` demoted to a dev/debug tool.
- [x] Polish round: per-row remove, taller rows, newest-first, non-disruptive
      auto-refresh, rule sweeps earlier matching entries, crisp menu-bar icon.
- [x] **Session inference** — generic-app activity (Soundly, Claude, browser)
      with no signal is attributed to the *currently active* project (the last
      strong context), tagged `guess` for review; cleared on idle. So the app
      knows what you're working on, not only at file/rule matches.
- [x] **Rules** view — see and delete rules (a wrong app-rule is reversible).
- [x] **Remove project**; bigger window; fixed clipped buttons/dropdowns
      (verified by rendering the window offscreen and inspecting).
- [ ] Live look review on the user's Mac — does the dark UI feel right?

### Phase 2 — Billing & reports  ⭐ (priority output) — reframed to the fee model
- [x] Per-project totals (Today / 7 days / month) via one shared aggregation
      (`db.totals_between`), feeding UI, menu bar, reports and CSV alike.
- [x] Explicit **billable** flag per session (confidence-aware defaults; the
      Review tab confirms guessed time with one click).
- [x] Fixed **fee** per project → **effective €/h** (fee ÷ lifetime billable
      hours) in Reports — the wage-health gauge.
- [x] Menu-bar glance: today's time per project; quick totals.
- [x] **CSV export** (project, employer, tracked/billable hours, fee, eff. €/h).
- [ ] Reports view with date-range picker + per-employer grouping.
- ~~Rounding rules~~ — obsolete under the fixed-fee model.

### Phase 3 — Timeline review & manual fallback
- [x] Timeline / day view of sessions; see what was tracked (`TimelineWidget`).
- [x] Edit session times + reassign (Review ✎); merge/split still open.
- [x] **Manual work blocks** — off-computer project time (calls, meetings,
      studio sessions) added after the fact; billable, part of the wage gauge.
      (Live start/stop timer: declined — review-first instead.)
- [x] Assign unattributed blocks to a project / mark non-billable (Review).
- [ ] "Approve before invoice" — lock a period once reviewed.

### Phase 4 — Activity & browser tracking (non-file work)
- [x] Browser URL detection (Safari + Chrome-family via AppleScript).
- [x] URL/domain → project rules (+ title-contains), created from the Review row.
- [x] App → project rules: Mail, Slack, Messages, AI tools.
- [x] Capture AI-agent work (Claude, Codex, etc.), email, calls, messaging —
      via app/URL/title rules, session inference, or manual assignment.
- [ ] Idle-return prompt: "You were away 20 min — keep / discard / assign?"
- [ ] Ambiguity nudge for sustained unattributed active time.

### Phase 5 — Intelligence & polish
- [ ] Smart suggestions: auto-categorize repeated unattributed patterns.
- [ ] Charts in reports (time per project/employer over time).
- [x] Automatic local backups (rotating daily snapshots, keep 7).
- [ ] Data export/import.
- [ ] Launch at login; lightweight, battery-friendly sampling.
- [ ] App icon, onboarding polish, preferences.

---

## Backlog (prioritised) — lead-dev audit 2026-06-18
> Deferred by the user: packaging waits until real-use testing proves the
> detection foundation is robust. Current focus: **robustness + testing**.
> Done since audit: ✅ **edit-project** (name/rate/employer/colour), ✅
> **browser-URL** (Safari/Chrome-family via AppleScript) + ✅ **url/title rule
> types** (the Review "rule" button now offers app / site / title).
> Declined: manual timer (not needed).
> Code-health pass: ✅ SQLite WAL, ✅ rotating file log
> (`~/Library/Application Support/WorktimeTracker/worktime.log`), ✅ pytest suite
> (`tests/`, 10 engine tests), ✅ dead code removed.
> ✅ **Control Center lifecycle** — local-only reviewed launch/quit, exact PID
> observation, duplicate-instance protection, and graceful session flush. Stats
> remain in WorktimeTracker's own menu rather than being duplicated elsewhere.
> ✅ **Day-timeline** strip in Review — today's sessions as colour-coded blocks on
> an hour axis, live 'now' marker, hover for details (`TimelineWidget`, custom
> QPainter). Next visual idea (parked): weekly summary for invoicing.
> ✅ **Visual overhaul** — glass-inspired dark theme: base colour on the window
> with layered translucent panels (rgba), hairline borders, refined accent/type,
> slim scrollbars, styled menus/tooltips, € on billable, nav pill + divider.
> NB true macOS **Liquid Glass** is a native material Qt can't render — it would
> need the eventual Swift port. (Qt gotcha fixed: style `QHeaderView` widget, not
> just `::section`, or it falls back to the light palette.)

> Cleanup pass 2026-07-22 (lead-dev review, v0.2.0): ✅ gui split into a
> package, ✅ tick-gap guard (sleep is never billed) + midnight session split +
> DST-safe day bounds, ✅ `user_version` migrations (v1: legacy folder column
> folded into `project_folders`, fee replaces hourly_rate/currency, dead
> `note` column and phone/contact rule kinds removed, billable flags
> normalized; pre-migration DB backup), ✅ dead code removed (manual-timer
> plumbing, detect_probe spike, CLI trimmed to `run`/`today`), ✅ shared
> helpers unified (timeutil / reporting / attribution.url_domain), ✅
> status-bar menu no longer rebuilds while open.

> Accuracy sprint 2026-07-22 (v0.3.0): ✅ attribution-coverage metric (Reports
> footer), ✅ playback counts as work (power-assertion idle override, 30-min
> cap; tested against real pmset output — incl. the coreaudiod Created-for-PID
> mapping and Electron's junk assertion), ✅ zero-config title↔project
> matching (`auto-title`), ✅ inference context TTL, ✅ manual work blocks +
> session time editing, ✅ target-rate colouring, ✅ rotating daily backups,
> ✅ offscreen GUI smoke tests.

Remaining, prioritised:
0. **Validate live for a week** — read the coverage number, tune knobs
   (TTL, media cap, title min-length) from real data before adding detectors.
1. **Launch at login + real `.app` bundle** (LSUIElement to hide the dock icon,
   app icon; Accessibility then attaches to the app, not the terminal).
2. **Session merge/split** (edit + reassign exist).
3. **Idle-return prompt** — "you were away N min — keep / discard / assign?"
4. Remember window size & last tab.   5. Empty states + a tag legend.
6. `lsof` fallback — only if the coverage metric proves a real gap.

## Edge cases & notes (don't forget)

- **Logic projects are `.logicx` packages** — represented file is the bundle;
  verify `AXDocument` updates on project switch, else lean on `lsof`.
- **Apps without a document path** — some plugins/web apps; covered by app/URL
  rules or manual assignment.
- **Multiple projects open at once** — frontmost wins; background renders/bounces
  don't count (we only bill active front time).
- **Same file path under two projects** — disallow overlapping project folders, or
  longest-prefix wins.
- **Privacy** — everything local; URL/title capture is sensitive, make it
  toggleable and excludable per app.
- ✅ **Clock changes / sleep / wake** — handled: ticks silent past
  `MAX_TICK_GAP` end the open session at the last live sample; sessions split
  at local midnight so daily totals stay exact.
- **Multi-monitor / Spaces** — frontmost app is global, should be fine.

## Future ideas (parking lot)
- Per-project notes / tags on sessions for invoice line-item detail.
- Weekly summary notification / email.
- Pomodoro or focus stats as a secondary view.
- Natural-language report queries.
- Optional encrypted backup to user's own cloud folder.
- Invoice PDF generation (beyond CSV).
- Menu-bar live timer showing current project + elapsed.

## Prior art
- **Timing.app** (macOS) — proven shape for automatic document/folder tracking.
  We differentiate on: employer/project-folder + billing focus, lean & local,
  no subscription, tuned to audio/media + AI-agent workflow.
