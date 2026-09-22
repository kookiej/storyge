# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Storyge — fetches Instagram stories from registered accounts, lets the user pick them from a
thumbnail grid, and saves them locally under a filename rule. **There are two products built
from one package, and most rules below apply to only one of them.**

**exe** — a Windows tkinter GUI, shipped as two PyInstaller onefile executables
(`Storyge` / `Storyge_demo`). Logs in with the user's own Instagram account via instagrapi.
Has scheduled collection, a staging area, and a progress log.

**web** — a local Flask server, `python -m storyge serve`, with the browser as the screen.
**No login at all:** stories come from third-party public story-saver sites (fastdl.app,
falling back to igram.world). No scheduling, no staging, no run records. Filenames default
to the original CDN name and can be composed from tokens.

Both share the `storyge` package, the `data\` folder, and the save folder. The exe is
unaffected by the web feature — Flask is imported only inside `__main__.cmd_serve`.

## Commands

### Common

**Always use `.venv\Scripts\python.exe`, never the global `python`.**

```powershell
.venv\Scripts\python.exe -m compileall -q storyge
```

#### Why the venv is mandatory

instagrapi requires `Pillow>=12.2`; the user's **global** Python has moviepy which requires
`pillow<12`. They cannot coexist. **Never `pip install instagrapi` globally** — it silently
breaks moviepy in the user's other projects. The exe bundles its own Pillow, so the global
environment stays untouched.

### exe

```powershell
.venv\Scripts\python.exe run_insta.py        # main GUI (Storyge)
.venv\Scripts\python.exe run.py              # demo GUI (Storyge_demo, classic look)
.venv\Scripts\python.exe -m storyge ls        # console CLI: ls/add/rm/fav/unfav/config/run
.venv\Scripts\python.exe run_insta.py --scheduled   # headless scheduled collection

powershell -ExecutionPolicy Bypass -File build.ps1   # builds BOTH exes into dist\
```

`build.ps1` creates `.venv` on first run and installs `requirements.txt` + pyinstaller into it.

### web

```powershell
.venv\Scripts\python.exe -m storyge serve                 # http://127.0.0.1:8760
.venv\Scripts\python.exe -m storyge serve --port 9000 --no-browser
```

`build.ps1` does **not** package the web version — it is a run-from-source feature. See
"Not done yet" under Web below before trying to make a `Storyge_web.exe`.

### Tests

There is no test suite in the repo. Verification has been throwaway scripts written to the
session scratchpad and run with the venv interpreter — each prints `[OK  ]` / `[FAIL]` lines
and exits non-zero on failure. When adding tests, follow that shape and **redirect `paths.*`
to a temp directory at import time**, before importing any other `storyge` module:

```python
from storyge import paths
paths.DATA_DIR = tmp; paths.CONFIG_FILE = tmp / "config.json"
paths.SESSION_FILE = tmp / "session.json"; paths.CREDENTIAL_FILE = tmp / "credential.bin"
paths.STAGING_DIR = tmp / "staging"; paths.STAGING_INDEX = paths.STAGING_DIR / "index.json"
paths.SCHEDULE_LOG = tmp / "schedule.log"
paths.RUN_STATE = tmp / "run_state.json"; paths.CANCEL_FLAG = tmp / "cancel.flag"
```

Otherwise tests write into the real `data\` folder.

**Never hit the network in tests** — not Instagram, and not the collection sites. Stub
`net.download_to` / `net.get_session`, and inject a fake source with `sources.register(...)`.

Console output: run with `PYTHONIOENCODING=utf-8`, or the Korean lines come out as mojibake.

**exe tests.** Dialogs can be driven headlessly: replace `gui.messagebox` / `picker.messagebox`
with a stub that records instead of showing, stub `schedule._run` so no real task is touched,
and schedule the poking with `root.after(...)` **before** constructing the dialog — its
`wait_window` pumps the event loop, so the callback runs while the constructor blocks. Test
whether a field is showing with `bool(widget.grid_info())`, not `winfo_ismapped()` (always
False under a withdrawn root). A whole window can be built without `mainloop()`:
`MainWindow()`, then `root.withdraw()`, `root.update_idletasks()`, `root.destroy()` — that
exercises `_build()`, which is where shared-code breakage shows up.

**web tests.** `create_app()` + `app.test_client()`. Register a fake source
(`sources.register("fake", ...)`) and pass `{"source": "fake"}` to `/api/fetch` — the registry
exists precisely for this injection. Set `sources.common.DELAY_BETWEEN_ACCOUNTS = 0.0` so the
politeness delay does not make tests crawl. Assert that `Host: evil.example` is rejected.

---

# Shared core — used by both products

### Data location and frozen builds

`paths.py` resolves `data/` next to `sys.executable` when `sys.frozen` is set, otherwise next
to the package. PyInstaller onefile unpacks to a temp dir that is deleted on exit, so anything
keyed off `__file__` would lose config/session every run. All modules must read
`paths.CONFIG_FILE` / `SESSION_FILE` / `CREDENTIAL_FILE` / `DOWNLOADED_FILE` — never build paths.

**The exe and a source run resolve to different folders**: the exe writes `dist\data\`, a source
run writes `<project>\data\`, so a login made in the exe is invisible to
`python -m storyge serve`. The fix is deliberately **partial** — there are two folders, not one:

- `DATA_DIR` — config, download history, staging. **Per product**, so the web and the exe can
  keep different account lists and save folders.
- `LOGIN_DIR` — `session.json` and `credential.bin` only. **Shared**, so one login in the exe
  serves both. `serve` points it at `dist\data` when that looks like a real data folder
  (`paths.looks_like_data_dir`) and prints both folders on startup.

`paths.use_data_dir()` moves both (login follows data); `paths.use_login_dir()` moves only the
login pair, so call it *after*. Both work only because every module reads `paths.X` **at call
time** — that rule is what makes this possible, so keep it. `serve --data` / `--login-dir`
override, and `STORYGE_DATA` (read at import) moves the data dir for every entry point.

One wrinkle: `_from_saved_session` refuses to try without `cfg.login_user`, and that name lives
in the *shared* folder's config. `instagrapi_source._borrowed_login_user()` reads **just that one
field** across the split — it is login info, not settings. After the first successful login
`session._save` writes it into the web's own config, so the lookup stops happening.

### The logo (`assets\`)

One mark for both products: the Instagram story ring with a download arrow inside it,
transparent background. `assets\make_logo.py` is **the only source** — it writes `logo.svg`,
`logo.ico` and `logo.png`, so don't hand-edit those three. It reads `theme.GRADIENT` rather
than repeating hex values, for the same reason `views.css_palettes` does.

Two things in it are load-bearing. The gradient runs along **the ring's own diagonal**
(`GRAD_FROM`/`GRAD_TO`), not the canvas corners — across the full canvas the circle never
reaches the ends and the ring comes out pink-to-purple with no orange or blue. And the SVG
gradient must stay `gradientUnits="userSpaceOnUse"`: the default (`objectBoundingBox`) is
resolved *per shape*, which would cram all four colors into the arrow alone.

`paths.ASSET_DIR` resolves differently from `DATA_DIR` — bundled read-only files live in
`sys._MEIPASS` under a onefile exe, not next to the exe. `build.ps1` therefore passes both
`--icon` (the exe's own icon) and `--add-data` (the copy `gui._set_icon` reads at runtime).
The window icon goes on **both exes**, not behind `theme.is_styled()`: it is the program's
face, not a theme.

The web serves the same files from `/logo.svg` and `/favicon.ico` — two explicit routes
rather than opening the folder — and uses them **for the browser tab only**. There is no
mark in the rail beside the `Storyge` wordmark; that was tried and removed at the user's
request. Don't add one back.

### The item model (`model.py`)

`StoryItemInfo` lives in `model.py`, **not** `fetch.py` — importing `fetch` drags in all of
instagrapi, and the web never logs in. `fetch.py` re-exports the name, so every existing
`from .fetch import StoryItemInfo` still resolves.

Three fields exist only for the web, and **all of them must keep a default**: `staging.py`
builds this dataclass with keyword arguments, so a non-defaulted field appended here breaks
scheduled collection.

- `time_basis` — `"exact"` / `"relative"` / `"fetch"`; how `taken_at` was determined.
- `source` — which provider produced this item.
- `orig_name` — the file name from the CDN path, without extension. This is the web's
  default filename.

**`mediaid` crosses the JSON boundary as a string, always.** Real Instagram pks are ~10^18,
above JavaScript's `2**53`, so a number would silently lose precision. Parse back with `int()`
server-side. Collection-site items have no pk, so `sources.common.synthetic_mediaid` derives
one from the CDN path (query stripped — Instagram signs URLs and the signature rotates). It is
48 bits: under `2**53` so JSON is safe, and three orders of magnitude below a real pk so the
two kinds can never collide inside the shared `data\downloaded.json`.

### Filenames — two rules, one per product

**exe: `naming.py`.** `YYMMDD @account #N` — numbering restarts per (date, account) group, the
` #N` suffix is omitted when a group has exactly one item, and numbering **continues past files
already in the save folder** so a second run on the same day doesn't collide. Extensions are
decided by `net.download_to()` from the response Content-Type, so `naming.py` returns stems only.
**This file's behaviour is frozen** — the web does not use it by default and must not change it.

**web: `filename.py`.** The default is **no template at all**: `item.orig_name`, the name
already in the CDN URL. Turning on "이름 형식 지정" switches to a token template. See the Web
section below for the token set and the generalised numbering.

### The `download.py` seam

`save_one(item, save_dir, stem)` does one file — download plus the `os.utime` that sets mtime to
the story's time — and raises on failure. `download_items` calls it and turns failures into log
lines; the web calls it directly so it can build structured results instead of re-parsing
translated prose. `download_items` also takes `names=None`; passing a dict overrides
`naming.build_names`. Desktop callers pass neither and are unchanged.

### i18n (`i18n.py`)

Korean source strings are the translation keys; `EN` maps them to English and `t()` falls back
to the Korean original when a key is missing. So a forgotten translation degrades to Korean
instead of crashing or showing a key. Interpolation uses **named** placeholders
(`t("추가함: {names}", names=...)`) because word order differs between the languages.
`__main__.py` and `app.py` are console-only and stay Korean.

`i18n._lang` is a module global, so it is not per-request safe. The web accepts this — it is a
single-user localhost tool — and sets it once at startup and on the language endpoint. Most web
labelling is client-side anyway: `views.index` ships the `EN` table to the page and `app.js`
has a `t()` that mirrors the same fall-back-to-Korean rule.

**One table, two products — short Korean words collide.** Because the Korean string *is* the
key, a bare word like `시간`, `일`, `계정` or `확인` means different things in different
screens, and a later duplicate silently wins (it is one dict literal). This already happened
once: the web's filename-token chips defined `시간` → `Time` and `일` → `Day`, which quietly
rewrote the exe's schedule dialog where they mean `hours` and `days`. So **never add a bare
generic word as a key** — phrase it so it cannot collide (`시각`, `일 (두 자리)`,
`계정 이름`). `filename.TOKENS` carries this rule as a comment, and `t_web.py` asserts the chip
groups are not the bare words. When adding keys, check for duplicates first.

### Editing shared files

`model.py`, `config.py`, `download.py`, `naming.py`, `net.py`, `paths.py`, `history.py` and
`i18n.py` are used by both products. After touching any of them, **build both desktop windows
once** (`MainWindow()` under `classic`, `dark` and `light`) and run the web test — that is the
only place this work can silently break the exe.

`config.py` depends on `paths` alone. Keep it that way: the web keys' default template string is
duplicated there as a literal with a pointing comment rather than importing `filename.py`.

---

# Desktop (exe) — tkinter

### One codebase, two executables

`theme.py` decides which product the user sees. `run.py` forces the `"classic"` theme,
`run_insta.py` reads `config.theme`/`config.lang`. Both go through `launcher.launch()`.

**The central convention:** visual changes go behind `theme.is_styled()` (False for classic),
and the `"classic"` palette returns `None` for every color key, meaning *"don't set this,
keep the tkinter default"*. That is how the demo exe stays byte-for-byte identical in
appearance while sharing all the code. Functional changes apply to both.

When touching `gui.py` or `picker.py`, decide up front whether the change is visual
(gate it) or functional (don't), and keep the classic path working.

### GUI threading contract (`gui.py`)

- Network work (login, fetch, download) runs in worker threads.
- tkinter widgets are touched **only** on the main thread.
- Workers hand work over via `self.ui(fn)` (fire and forget) or `self.ui_wait(fn)` (blocks the
  worker until the main thread returns a value — used to raise modal dialogs from a worker).
- `_drain_queue()` pumps that queue every 80 ms and is cancelled on `<Destroy>`.

Changing theme or language **rebuilds the whole window** (`_rebuild()`): ttk styles do not
fully re-apply to existing widgets. Log lines and status text are kept as strings and
re-inserted. Anything added to `_build()` that holds state must survive that rebuild.

### Login flow (`session.py`, `credentials.py`)

`get_client(cfg, force_login=...)` tries, in order: saved session → saved DPAPI credentials →
browser cookies → login dialog. Two subtleties:

- `_session_state()` returns three outcomes, not two: alive, definitely expired, or
  *could not check* (rate limit / network). A session is only discarded on the second.
  Discarding on "could not check" forces a needless re-login every run.
- **`force_login=True` skips the saved session *and* the saved credentials.** The `로그인` /
  `Log in` button uses it, and it is the only way to switch accounts — auto-login would
  otherwise loop back into the same account forever.

Credentials are encrypted with Windows DPAPI (`credentials.py`), decryptable only by the same
Windows user on the same PC. instagrapi's `dump_settings()` stores cookies but not the password,
which is why they are kept separately.

**The web borrows this but never drives it.** `sources/instagrapi_source.py` calls
`get_client(force_login=False)` with `ask_credentials`/`ask_two_factor` callbacks that always
return `None`, so a missing session degrades to `SourceBlocked` and the chain moves on. The
defaults call `input()`, which in a server process would hang the request forever —
`launcher.run_scheduled` guards the same way for the same reason. **The web must never grow a
login screen**; logging in stays the exe's job.

**Expiry is handled in two different places, and both are needed.** `get_client` already
re-logs-in from the saved DPAPI credentials when the stored session is dead — but that only
runs at `open()`. A session can also die *mid-run*, and then every remaining account would fall
through to the scrapers and lose its timestamp. So `_query()` raises a private `_Expired` for
`LoginRequired`/`ClientLoginRequired` and `fetch_account` calls `_relogin()` once and retries
that same account. **Once per run** (`_relogged`): if the password changed or the account is
locked, retrying per account just lengthens the block. Rate limits and `ChallengeRequired` are
deliberately *not* retried — neither is fixable by logging in again.

`_from_saved_session` keeps a session it could not verify (rate limit / network), which used to
mean a dead session poisoned the whole run. With the mid-run re-login that case now self-corrects
on first use.

### Scheduled collection (`schedule.py`, `staging.py`, `launcher.run_scheduled`)

`run_insta.py --scheduled --task <id>` runs with **no Tk window at all** and must finish unattended:

- It passes `ask_credentials`/`ask_two_factor` callbacks that always return `None`. The
  defaults call `input()`, which in a windowed/headless process hangs forever and holds the
  slot until the next run. Anything added to that path must keep this property.
- Output goes to `data\schedule.log` (`schedule.log_line`) — there is no console or window.
  Everything else it touches (`runstate`) swallows its own errors for the same reason.

`schedule.py` registers a Windows task from an **XML definition**, not `schtasks` flags,
because wake-from-sleep (`WakeToRun`) is not reachable any other way. `InteractiveToken`
means no stored password and it still runs while the screen is locked. The XML file handed to
`schtasks /Create /XML` **must be UTF-16** — UTF-8 is rejected as malformed.

**There are N schedules, one Windows task each** (`Storyge_<id>`, id = `uuid4().hex[:8]`).
`config.Schedule.mode` is `daily` / `days` / `hours` / `custom`; the first two become a
`CalendarTrigger` with `ScheduleByDay`, the last two a `TimeTrigger` whose `Repetition` has
**no `Duration`** — that is what makes it repeat indefinitely instead of resetting every day.
`Schedule.once` overrides `mode` entirely: a bare `TimeTrigger` at the next occurrence of
`time`, and `run_scheduled` turns the schedule off (config + `unregister`) in its `finally`
once it has run — success or not, so a failing one-time schedule cannot retry forever.

The schedule log (`data\schedule.log`) deliberately carries **only the stored-count line and
problems**. The start banner, `session.get_client` progress (passed `log=lambda _m: None`) and
the purge line are all omitted — "which schedule ran when" is answered by the list's
per-schedule 마지막 실행 instead. (`fetch_stories` no longer reports "no stories" at all, so
that noise is gone from the window's log too — see below.)
That last-run line comes from `runstate.last_scheduled`, written only for `source="scheduled"`,
because `current` is shared with window runs and would otherwise show a window fetch in the
schedule dialog. `describe_scheduled()` keeps the **same label in every state** — with no record
it returns `"마지막 실행:"` with an empty value rather than swapping in a different sentence.
`schedule.parse_hhmm` is the single `"H:MM"` parser (leading zero optional) shared by the XML
builder and the dialog's validation.

**`save()` omits `schedules` and `staging_retention_days` when they carry nothing** (empty list,
`DEFAULT_RETENTION_DAYS`). Scheduling is exe-only, so the web's own `config.json` should not
sprout an empty schedule list that reads as "this product has scheduling too". Omitting only the
*empty* case is what makes it safe: `load()` has already pulled real schedules into `cfg`, so
even when both products share one folder (`serve --data`) a web save writes them straight back.
A missing key loads as `[]` / `7`.

Two rules about the legacy single-schedule task named `Storyge`:
- `config.load()` migrates the old `"schedule"` key to a one-item `"schedules"` list; `save()`
  stops writing the old key.
- **Only `schedule.sync()` (called from the GUI) deletes the legacy task**, after it has
  registered the replacements. A headless run invoked without `--task` must keep working off
  the first enabled schedule and must *not* delete it — if the user never opens the window,
  the new per-id tasks do not exist yet and scheduling would stop entirely.

### Number-only fields (`gui._only_digits` and friends)

The time and interval fields are **an hour box, a `:` Label, and a minute box** — the colon is
text, so there is nothing to delete or mistype, and `"930"` can never be ambiguous. Helpers:

- `_only_digits(entry, limit)` — a `validate="key"` command. It must **not touch any widget**:
  editing inside a validatecommand makes Tk silently turn validation off. Note it judges whole
  proposed values, so pasting `"ab9"` is rejected outright rather than filtered down to `"9"`.
  Don't use `str.isdigit()` here — it is True for `'²'`, which then explodes in `int()`.
- `_hop_when_full(first, second)` — jumps to the next box, bound to `<KeyRelease>` for the same
  reason. It tests `event.keysym`, not `event.char`, so the numeric keypad (`KP_3`) works too.
- `_clock_box(parent, hour_var, minute_var)` — builds the trio; the caller sets the hour box's
  digit limit (2 for a time, 3 for "365 days") and hides the colon/minute for non-`custom` modes.

Because the fields only accept digits, save-time validation is just "empty or out of range" —
hence the range-worded messages rather than format ones.

### Run state and stopping a job (`runstate.py`)

The window and the headless run are **different processes**, so progress and stop requests go
through files: `data\run_state.json` (`current` + `by_schedule`) and `data\cancel.flag`.

- `runstate.is_running()` is true only if the record says `running` **and** started under 35
  minutes ago — the task's `ExecutionTimeLimit` is `PT30M`, so anything older is a crash
  leftover, and without that check one crash would skip every future run.
- A headless run clears the flag on entry (a stale request must not kill a fresh run) and in
  `finally`. The 예약 window's 중지 button just writes the flag; nothing hard-kills a process
  mid-download.
- In the GUI the same seam is two `threading.Event`s: `MainWindow._should_stop` **blocks while
  paused** and returns True only on cancel, so `fetch`/`download` stay ignorant of pausing —
  they only ever see `should_stop()`. Steps outside those two functions use `_checkpoint()`,
  which raises `JobCancelled`.
- Cancel points are between accounts (`fetch_stories`) and between files (`download_items`) —
  a single account lookup sits inside instagrapi and cannot be interrupted.

**The web does not use `runstate.py`** — it is one process, so its jobs live in memory
(`web/jobs.py`). Do not make the web write `run_state.json`; the desktop would then see a
"running" record it cannot stop.

### Cancelling the window's own job — `job_gen`

`취소` must return the window immediately, but a Python thread blocked in a socket read cannot
be killed: `PyThreadState_SetAsyncExc` does not interrupt one, so it buys nothing and risks
inconsistent state. Instead `MainWindow._cancel_job` **abandons** the worker — it bumps
`self.job_gen`, sets `cancel_event`, writes `runstate.finish("cancelled")`, and clears busy
right away. The worker captures `gen = self.job_gen` at the top of `_work` and everything that
could touch shared state is guarded by `self._alive(gen)`:

- the `finally` (busy flag **and** `runstate.finish`) — otherwise an abandoned worker resets the
  state of the *new* job the user just started
- `log` / `status` (local closures, not `self.log` directly)
- `_should_stop(gen)` returns True for a stale generation, so the loops exit on their own

No half files result: `net.download_to` writes a `.part` and moves it, deleting it on any
exception, and `net.TIMEOUT` bounds our own requests.

**Layout constraint:** the run row does not fit everything at the default 760px width. Scope
radios live on their own row, and `_set_busy(True, cancellable=True)` **hides `run_button`** so
일시정지/취소 can use its place — without that, 취소 is pushed off-screen and unclickable.

`staging.py` keeps collected stories in `data\staging\` with an `index.json`. It saves the
**media and a separate thumbnail** for each item: Instagram CDN URLs die with the story after
24h, so a later review cannot re-fetch anything, and an mp4 cannot serve as its own preview.
Review reuses the normal picker — `picker.load_thumbnails` takes a `fetch_bytes` callback, so
passing `staging.read_bytes` makes it read local files instead of URLs.

### "더 가져오기" in the picker (`picker.py`)

`open_picker(..., fetch_more=..., known_accounts=...)` adds a button that asks for accounts and
appends only unseen items. **Passing no callback is how the button disappears** — the staged
review does that on purpose: it has no logged-in client, and staged items' CDN URLs are dead
anyway. The fetch runs on a picker-owned daemon thread polled with `win.after`; that is safe
only because the original worker is parked inside `ui_wait`, so the instagrapi client is never
used by two threads at once. `_add_items` **rebuilds the whole grid** rather than appending —
`_build_grid` groups by account, so a late append would split one account into two sections.
Selection survives because it lives in `self.selected`, keyed by mediaid.

**The picker window is deliberately not `transient`.** Tk strips the minimize/maximize buttons
and the taskbar entry from transient windows, so it could not be put aside while picking. It
stays modal (`grab_set`), but `<Unmap>`/`<Map>` release and re-take the grab while it is
iconified — otherwise the window is down *and* the main window is locked, which looks frozen.
The trade-off is that it no longer floats above the main window; the taskbar button is the way back.

`ask_accounts` (shared by 더 가져오기 and the main window's `직접 입력` scope) mirrors the main
account list: `extended` selectmode (so Ctrl/Shift **and dragging** work), a 전체 선택/전체 해제
toggle, and double-click to deselect. `<<ListboxSelect>>` **adds** the current selection to the
entry — additive, never removing, so dragging past an account keeps it. The entry holds bare
names without `@`; `config.normalize_id` means a hand-typed `@abc` still parses.

### instagrapi exception ordering (`fetch.py`)

Most instagrapi exceptions inherit from `PrivateError` — including `PleaseWaitFewMinutes`,
`RateLimitError`, `LoginRequired` and `ChallengeRequired`. A chain of `except` clauses catches
the widest first and misreports everything as "private account". `fetch.py` therefore uses one
`except Exception` and checks with `isinstance` from narrowest to widest. **Rate limits must
break out of the account loop**, not continue — hammering a throttled account extends the block.

The returned notes are **problems only**. An account with no stories right now produces no note
at all: with many accounts that one line filled both logs, and the overall outcome is already
reported by the caller (`새로 저장할 스토리가 없습니다` / `보관함에 0개를 넣었습니다`).

---

# Web — Flask

### The source seam (`sources/`)

**This is the most important boundary in the web version.** A scraper site can be blocked or
disappear at any time, so everything above this layer — the job runner, the grid, the filename
engine, the save pipeline, the thumbnail proxy — must not know where items came from.

`StorySource.fetch(...)` is `fetch.fetch_stories` **minus its `client` argument**: the same
`on_account(account, index, total)` progress callback, the same `should_stop` checked between
accounts, the same "notes are problems only" contract. `web/jobs.py` therefore drives any
provider with identical code. There is one extra callback, `on_items(account, items)`, so the
grid fills in as each account finishes instead of waiting for the whole run.

Individual sites subclass `SiteSource` and implement only `open()` and `fetch_account()`.
`ChainSource` owns the account loop, the switching, the delays and every note.

**Switching is per-run, not per-account.** A site that blocked us stays blocked for the rest of
the run, and re-knocking per account only lengthens the block. When `fastdl` raises
`SourceBlocked`, the *same account* is retried on `igram` and every remaining account goes there
too. A private or missing account is **not** a switch reason — the answer would be the same
anywhere, so it produces a note and the loop moves on. `_errors_in_row` must be reset on every
success, or scattered one-off failures eventually discard a working site.

**Switching is silent, and failure is reported exactly once.** The user never picks a site, so
which one blocked us when is not their problem — per-site reasons go into `_failures`, never into
`notes`. Only when every site is exhausted does `ChainSource` set `blocked` and append the single
line `"서버에 연결하지 못했습니다."`. Per-account notes (private, missing) stay, because those
are facts about that account rather than a server fault.

That distinction is the whole point: **`blocked` is what separates "the sites are unreachable"
from "there were no new stories"**, and the two must never share a message. `run_fetch_job` copies
it off the source with `getattr(source, "blocked", False)` — it is an optional attribute on the
protocol, so a source that does not set it still works — and `pollFetch` picks the toast from it.

Register sources with `sources.register(id, factory)`; the factory returns a **new** instance
each time, because a source carries session, token and switching state.

### Politeness is not optional

`sources/common.py` fixes the rules as constants: one landing request per run, one query per
account, strictly sequential, a 2-second gap between accounts, no retries on 4xx, and give up on
a site after two consecutive failures. These are free services; what actually costs them money
is request rate. The Chrome UA from `net._UA` is used deliberately — an honest bot UA is blocked
on the first request — and good citizenship is enforced through *rate* instead. Don't add a
thread pool here.

Collection-site sessions come from `common.new_http()`, **not** `net.get_session()`: a
scraper site's cookies must never ride along on Instagram CDN requests, or the reverse.

### Chain order, and why (`sources/__init__.py`)

`auto` is `instagrapi → saveinsta → fastdl → igram`. The order encodes what each can do:

| | login | posted time | private accounts | works today |
|---|---|---|---|---|
| `instagrapi` | needs a saved session | **exact** | yes (followed) | when a session exists |
| `saveinsta` | none | none — falls back to fetch time | no | yes |
| `fastdl` / `igram` | none | none | no | no (unsigned `/api/convert`) |

**`instagrapi` is first because it is the only source that knows when a story was posted.**
The scraper sites give no timestamp and no relative age, so their items are `time_basis="fetch"`
and the grid marks them `~`. Without a session `open()` raises `SourceBlocked` and the chain
falls through silently — that is "this route is unavailable", not a failure, so no note is shown.

### The scraper that works (`sources/saveinsta.py`)

Of the three no-login sites, **only saveinsta fetches anything** (the other two are blocked on a
signature we cannot compute — see below). Its flow, all server-issued tokens and therefore
reachable from Python:

1. `GET /en1/story` — scrape `k_token` / `k_exp` out of an inline script. Once per run;
   if `k_token` is missing, raise `SourceBlocked` immediately rather than trying every account.
2. `POST /api/userverify` `{url}` → `{token}`. **Once per account** — the target URL is baked
   into that JWT, so it cannot be reused. This is why saveinsta costs two requests per account.
3. `POST /api/ajaxSearch` with those plus `q`/`t=media`/`lang`/`v=v2`/`cftoken`
   → `{"status":"ok","data":"<html>"}`.

The input form is `https://www.instagram.com/stories/{account}` — no story id needed.

**Media arrives wrapped in snapcdn JWTs** (`i.snapcdn.app/photo?token=…`,
`dl.snapcdn.app/saveinsta?token=…`). We read the `url` claim out of the payload and download
**straight from the Instagram CDN** instead of through their proxy. Two reasons, both matter:
it keeps every video byte off a free service, and `orig_name` (the web's default filename) comes
from the CDN path. The signature is never verified — we are reading a claim, not trusting it.

**Do not map "no data" to a private account.** When an account simply has no live story,
saveinsta still answers `Error: Video is private…`. Verified against several public accounts:
`natgeo`/`nasa` returned media, `zuck`/`instagram` returned that same "private" line with nothing
behind it. So an empty `data` means "nothing to fetch" and produces no note at all; only
`Url is not supported` becomes `AccountNotFound`.

saveinsta gives **no post time and no relative age**, so its items are always
`time_basis="fetch"` and the grid marks them `~`.

### One fragile function (`sources/convert_site.py`)

fastdl.app and igram.world are **the same backend** — same `/api/convert`, `/api/captcha`,
`/api/cf`, `/get_country_code`, same `x-token`. So there is one implementation and the two site
files hold nothing but a hostname. Both rotate their path segment (`/en5IW`, `/en2`), which is
why the segment is read from the landing redirect and never hardcoded.

Everything volatile is confined to `_parse_payload`, marked with a banner comment. It returns
**plain dicts**, never `StoryItemInfo` — `common.make_item` does identifier synthesis, time
resolution and the original name. To repair it after a site change: set
`STORYGE_DEBUG_SOURCE=1`, run once to capture `data\source_last.txt`, then edit only that
function until the parser test is green. Never commit the capture — it holds signed CDN URLs.

**Known gap:** `/api/convert` validates an `x-token` signature before it even reads the URL
(an unsigned request returns `URL_IS_EMPTY` whether sent as JSON or as a form). That signature
is computed inside the site's obfuscated `app.js`. `_sign_request` returns `None` until someone
fills it in from a devtools capture, and while it does, both sites raise `SourceBlocked` with a
plain message. **That is deliberate** — failing visibly beats pretending to work and returning
nothing. They stay in the chain behind saveinsta so they take over the moment either that
signature is filled in or saveinsta stops working.

**This is why the seam earned its keep.** saveinsta was added as one new file plus one line in
the registry; nothing above `sources/` changed. Keep it that way.

### Time is estimated, and the UI says so

Scraper sites do not give the original post time. `common.resolve_taken_at` tries, in order:
a real timestamp in the payload (`"exact"`), a relative age like "3시간 전" / "3 hours ago"
counted back from now (`"relative"`), then the fetch time (`"fetch"`). Anything older than 48
hours is rejected — a story cannot be.

Relative ages get the date right nearly always: fetched just after midnight, "1 hour ago" still
lands on yesterday. Precision is about ±1 hour. Anything that is not `"exact"` is shown with a
`~` marker on the cell and a tooltip — **per item, never a page-wide banner** (that was tried and
removed; it repeated what every affected cell already said). Don't quietly present an estimate
as fact.

### While fetching, the grid stays empty

No placeholder cells. Drawing a fixed number of them pretends to know how many stories will
arrive, and the progress bar above already says what is happening. `Grid.loading` exists only to
suppress the `'스토리 가져오기'를 누르면...` hint, which would otherwise read as "nothing here"
in the middle of a run. Items appear per account as `on_items` reports them.

### The progress row must be emptied, not just hidden

The save step **shows the progress row again** after fetch is done. Anything left in it — a
spinning `#spinner`, a `#progress-fill` still at the last run's width — reappears and reads as
"still fetching". So `setBusy(false)` no longer touches the row; **the caller picks one of two
endings**, which is the whole point:

- `progressFinish()` — only when the job reached `done`. Fills the bar to 100%, drops the
  spinner, and clears the row after `PROGRESS_HOLD_MS`. Without the hold you never see the bar
  complete; it just vanishes mid-way and the run looks abandoned.
- `progressClear()` — cancelled, errored, or a failed poll. Hides everything at once.
  **A cancelled run must not show 100%** — that would be a lie about what happened.

Both cancel `_progressTimer`, as does `setBusy(true)`, so a pending "hold" from the previous run
can never wipe the next one's progress. Save drives the same track itself rather than inheriting
whatever fetch left behind.

### Jobs are in-process and polled (`web/jobs.py`)

A background thread works; the browser asks every 500 ms. SSE was rejected: Flask's threaded
server holds a worker thread per open stream and a dropped connection stalls silently. Progress
is per-account, so a 12-account run has 12 meaningful updates — polling is plenty.

**Loading the page stops whatever was running.** `App.boot()` calls `POST /api/reset` before
anything else, and that sets `cancel` on every running job (`JobRegistry.running_all`). The page
could resume a job instead — the job id is right there in `/api/state` — but inheriting a
half-filled grid reads as a glitch, so a refresh is a clean restart. Cancels only land between
accounts and between files, so no half files result. `boot()` then forces the progress row and
spinner hidden rather than trusting them to already be.

**`job.items` is the single source of truth.** The browser never receives a URL; it holds mediaid
strings and nothing else. Both the thumbnail proxy and the save step look items up there.
`JobRegistry.running(kind)` is what makes a second 가져오기 return `409` with the existing job id
— the intent of `runstate.is_running()` without the cross-process file.

### The thumbnail proxy takes no URL

`GET /api/thumb/<job_id>/<mediaid>` looks the URL up in server-side job state. **There is no
parameter anywhere in the API that accepts a URL**, so there is no SSRF surface — keep it that
way. Instagram CDN images often fail when loaded directly by the page (referer checks, no CORS),
which is why they are streamed through the server at all. A small LRU keyed by mediaid avoids
re-hitting the CDN when the grid re-renders.

### Filename templates (`filename.py`)

The default is `item.orig_name`, the name already in the CDN URL — unique on its own, so no
numbering is needed, and `net.download_to` already skips an existing target.
**`naming.py` is not used by this path at all.**

Tokens are `{}`-delimited and case-sensitive (`{mm}` is month, `{MM}` is minute):
`{orig} {date} {yyyy} {yy} {mm} {dd} {time} {HH} {MM} {SS} {account} {@account} {n} {nn} {type}`.
`TOKENS` is the single list the chips and the validator both read.

A `[...]` segment is dropped when the group has exactly one new item and nothing matching
already exists — the same rule as the desktop's conditional ` #N`.

**Continuing past existing files with an arbitrary template** is the one piece of real
machinery: render once with a sentinel in the number slot, then `partition` on it into a literal
prefix and suffix. That handles `{n}` first, last or in the middle in a single pass. The glob
narrows on `commonprefix(prefix, bare)` so a file with the number omitted is still found.
Templates with no number token are de-duplicated inside the batch (` #2`, ` #3`), which is a
warning, not an error.

`build_names` **never raises** — a broken template falls back to the CDN name. Blocking a save
because a setting is malformed leaves the user with no way out; the settings endpoint runs
`validate()` first so it rarely gets that far.

### Local only

`127.0.0.1` binding plus a `Host` header check is the entire security model, and it is
appropriate for a single-user tool. **The Host check is not redundant with the binding:** without
it, any web page the user visits can drive this server (DNS rebinding — point a domain at
127.0.0.1 and the browser treats it as same-origin). There is no login and no CSRF token by
design; don't add one without also adding real multi-user handling.

`use_reloader=False` is required — the reloader forks a second process and every job would be
registered twice.

### The account rail

The rail's width is a drag handle (`.splitter`) between two grid columns, clamped to 180–520px
and remembered in `localStorage` — it is one browser's view preference, not something
`config.json` should carry. Every `localStorage` call is wrapped in try/catch because a private
window throws on access. The default (`Splitter.DEFAULT`, 300px) is duplicated in
`app.css` as `var(--rail-w, 300px)` and **the two must agree**; it is wide enough that
`전체 선택 / 전체 해제 / N개 삭제` still fit on one line once a bulk selection exists.

The handle column is 2px. That is too thin to grab, so `.splitter::before` with `inset: 0 -4px`
widens the hit area without widening the line. Do **not** go back to transparent borders for this —
`box-sizing: border-box` leaves no room for them inside a 2px track.

Collapsing the rail toggles `.app.rail-off`, remembered in `localStorage`. There are **two
buttons, not one**: `#rail-toggle` sits inside the rail on the title line (`.rail-head`, which
needs `align-items: flex-start` or it drifts down to the middle of the two-line brand), and
`#rail-show` sits in the topbar and is hidden by CSS while the rail is open
(`.app:not(.rail-off) #rail-show`). The collapse button disappears with the rail it lives in, so
the topbar one is the only way back — that is why it exists rather than being a second copy.

The **zero-width column rule is scoped to `min-width: 761px`** — the narrow layout stacks rows
instead, so collapsing columns there would push the main pane into a 0-wide track.

Selecting accounts is pointer-driven so a drag can sweep several rows. Two rules make it work:
`dragTo()` recomputes from a **snapshot of the selection taken at pointerdown**, so dragging back
shrinks the selection instead of only ever growing it; and the handlers **repaint the `on` class
instead of re-rendering the list**, because rebuilding the rows mid-drag destroys the element the
pointer is over. `dragOver` uses `elementFromPoint` rather than `pointerover` since touch
implicitly captures the pointer to the first row. The bulk-delete button appears at 2+ selected —
one row is already covered by its own `✕`.

In the account field, `Enter` (and the `추가` button) **only adds to the list**; `Ctrl+Enter`
adds **and immediately fetches just those accounts**. Typing is the common case, so the plain
key must not kick off network work. The Ctrl+Enter handler calls `preventDefault()` because some
browsers also fire `submit` for it, which would add the same names twice.

### Favourites are exe-only

`config.Account.fav` and `config.set_fav` exist for the desktop app. The web has no star, no
favourites filter, and no `/api/accounts/fav`, and `accounts_json` does not even ship the field.
This is safe because `config.add_accounts(..., fav=False)` leaves an existing account's flag
alone and `config.save` rewrites what it loaded — so the web can add and remove accounts all day
without clearing what the exe starred. `t_web.py` asserts exactly that.

### Nothing about *where* items came from reaches the browser

There is no site picker in settings and no provider badge on a cell: `auto` already skips a
blocked site mid-run, so there is nothing to choose. `/api/state` does not ship `sources` and
`item_json` does not ship `source`. `config.web_source` survives as a config-file-only escape
hatch (pin `fastdl` or `igram` by hand when chasing a problem), and `StoryItemInfo.source` stays
on the server-side dataclass — it is just never serialised.

The save folder is set **only** by `폴더 선택`; the path field is `readonly` and there is no
Apply button, so `_check_save_dir()` is the single gate every path passes through.

### Deliberately absent

Scheduled collection, the staging area, run records, Instagram login, the progress log panel,
favourites, and any choice of collection site are **left out on purpose**, at the user's request.
If you notice one missing, it is not an oversight — do not restore it.

### Not done yet

- `_sign_request` (see above) — the web cannot actually fetch until it is filled in.
- Packaging. A `Storyge_web.exe` would need `--add-data` for `storyge/web/static` and
  `templates`, plus `sys._MEIPASS` handling for the static folder. Note that the folder picker
  below shells out to `python -c`, which an onefile exe cannot do — `_picker_python()` already
  returns `None` under `sys.frozen` and the endpoint falls back to "type the path".

### The folder picker runs in its own process

`POST /api/settings/save_dir/browse` opens a real Explorer dialog. The obvious blocker — Tk must
own its process's main thread, and Flask is already sitting on this one — **disappears by
spawning a second process**: `subprocess.run([python, "-c", _PICK_DIR, initial])`, where that
child's main thread belongs to Tk. Details that matter: prefer the `pythonw.exe` next to
`sys.executable` (plain `python.exe` flashes a console), pass `CREATE_NO_WINDOW` otherwise, set
`-topmost` so the dialog does not open behind the browser, always pass a `timeout` (a forgotten
dialog would pin the request forever — Flask is `threaded=True` so only that one request blocks),
and treat an empty stdout as "cancelled", not as an error. The chosen path goes back through
`_check_save_dir()` so the validation rules live in exactly one place.

---

## Gotchas that have bitten before

### Common

- **`build.ps1` must stay UTF-8 *with BOM*.** Windows PowerShell 5.1 reads a BOM-less file as
  CP949, mangling the Korean strings until the script fails to parse.

### exe

- **PyInstaller onefile spawns a child process.** The GUI window belongs to the child, so a
  process check must scan *all* processes with that name, not the PID returned by `Start-Process`.
- **`--windowed` means `sys.stdout is None`** — a stray `print()` raises. `launcher.guard_stdio()`
  redirects to devnull; unexpected errors go to `data\error.log` and a message box.
- **Filtering "falsy" widget options drops `bd=0` / `highlightthickness=0`.** `gui._paint()`
  skips `None` only, and `_flat()` returns `None` in classic mode so those options aren't applied there.
- **clam's ttk checkbutton indicator cannot change glyph** (its element only exposes color
  options). Drawing `☑`/`☐` as text with `widgets.FlatToggle` was tried for both checkboxes
  ("삭제 전 확인", "예약 사용") and **rolled back on request** — both stay plain
  `ttk.Checkbutton`. Don't redo it. `FlatToggle` still backs the language button and `StarButton`.
- **Those colour options are `indicatorbackground` (the disc) and `indicatorforeground` (the
  dot/check) — not `indicatorcolor`**, which silently does nothing here (`style.lookup` returns
  `''`). Setting only the `selected` state leaves clam's white default disc on both states, so
  on a dark background the *unselected* control looks brighter than the selected one and the
  choice reads backwards. Verify such colours by sampling screenshot pixels, not by eye.
- **`Dim.TLabel` has a `surface` background** (meant for cards). On a dialog whose background
  is `bg` it shows as a lighter strip — use `Sub.TLabel` there.
- **`ImageTk.PhotoImage` disappears if unreferenced.** `picker.py` keeps every image in
  `self.photos`; each cell holds two pre-rendered variants (plain / gradient ring) and selection
  swaps `label.configure(image=...)`.
- Browser-cookie login needs administrator rights on this machine (Chrome 127+ App-Bound
  Encryption), so the login dialog is the practical path. That code must never raise — it is a
  convenience step, and a failure there should fall through to the dialog.

### web

- **Don't import constants by value across the source layer.** `sources/__init__.py` reads
  `common.DELAY_BETWEEN_ACCOUNTS` through the module, not `from .common import ...`, or tests
  cannot set the delay to zero and a later edit to one copy silently misses the other.
- **`theme.py` imports tkinter**, so the web process imports it too. That is fine (no `Tk()` is
  ever constructed) and it is what keeps the browser palette and the exe palette identical.
  Don't "fix" it by copying hex values into the CSS.
- The web reloads `config.load()` per request, because the desktop app may be editing the same
  `data\config.json` at the same time.

## Reference

`README.md` is the end-user manual (Korean), with separate sections for the exe and the web.
