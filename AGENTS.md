# AGENTS.md

## Project Overview

Multi-content-type web scraper for [SF轻小说 (sfacg.com)](https://book.sfacg.com) — a Chinese light novel, comic, and audiobook platform. Written in Python using `requests` + `BeautifulSoup`.

**Status:** Not finished. Learning project.

## Architecture

```
sfacglib/
  __init__.py     # Package exports
  config.py       # Centralized constants (URLs, paths, workers)
  fetcher.py      # Smart HTTP fetcher (rotating UA, retry, rate limiting, auth)
  auth.py         # Login, session persistence, cookie management
  selectors.py    # CSS selector registry (loads from selectors.json)
  selectors.json  # All CSS selectors, organized by page type
  ch.py           # Chapter content fetcher (mobile + PC endpoints)
  book.py         # Novel downloader (text, HTML, EPUB)
  comic.py        # Comic/manga downloader
  audio.py        # Audiobook downloader
  epub.py         # EPUB generation with three-level TOC
  audiobooks.json # Cached audiobook catalog

app.py            # Flet Material Design UI (Desktop/Web/Android/iOS)
review.py         # Review downloader (CLI)
main.py           # Unified CLI entry point
build.sh          # Build script (desktop/web/apk/ios)
.cookies.json     # Saved session cookies — gitignored
```

## Authentication

SFACG login requires Tencent CAPTCHA. Password login is not supported.
Import cookies from browser DevTools instead.

**To login:**
```bash
# Option 1: Use the GUI (recommended)
uv run python app.py  # Navigate to 账号 → 粘贴 Cookie

# Option 2: CLI
uv run python -c "
from sfacglib.fetcher import Fetcher
f = Fetcher()
f.import_cookies('paste_your_cookie_string_here')
"
```

**How to get cookies:**
1. Open https://m.sfacg.com/ in browser and login
2. F12 → Network → refresh page → click any request
3. Copy the `Cookie` header value
4. Paste into the app

## Key Design: Selector Registry

All CSS selectors live in `sfacglib/selectors.json`. When selectors break:

1. The spider raises `SelectorError` with context (page, field, selector, URL)
2. Error message tells you to use chrome-devtools-mcp to diagnose
3. You update `selectors.json` with the correct selector
4. Spider retries — no code changes needed

**To fix a broken selector:**
```
1. Use chrome-devtools-mcp to navigate to the failing URL
2. Take a screenshot to see the current page layout
3. Use evaluate to test CSS selectors: document.querySelectorAll('.candidate')
4. Update sfacglib/selectors.json with the working selector
```

## Coding Conventions

- Python 3.10+, use `uv` for package management (not pip)
- Package imports use relative imports within sfacglib (e.g. `from .fetcher import Fetcher`)
- All constants in `sfacglib/config.py` (no hardcoded URLs/paths)
- Logging via `loguru` (not stdlib logging)
- Rate limiting: always respect delays between requests (0.2s–3s depending on context)
- Concurrency: `concurrent.futures.ThreadPoolExecutor` for parallel downloads
- Progress: `tqdm` for all download loops
- All content returns `(markdown_str, html_str)` tuple
- No comments in code unless explicitly asked

## Running

```bash
# Install dependencies
uv sync

# Run the modern GUI (Desktop)
uv run python app.py

# Run in web browser
uv run flet run app.py --web

# Build APK (requires Android SDK)
./build.sh apk

# Build desktop executable
./build.sh desktop

# Run specific modules
uv run python -m sfacglib.book
uv run python -m sfacglib.comic
uv run python -m sfacglib.audio

# Run review downloader
uv run python review.py

# Run CLI
uv run python main.py novel 43708 -f epub -o ./output/
```

## MCP Tools Available

- `chrome-devtools-mcp` — Browser automation for diagnosing broken selectors. Use it to navigate pages, take screenshots, evaluate JS, and find correct CSS selectors when the spider breaks.
