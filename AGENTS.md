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
  ch.py           # Chapter content fetcher (mobile + PC + VIP endpoints)
  book.py         # Novel downloader (text, HTML, EPUB)
  comic.py        # Comic/manga downloader
  audio.py        # Audiobook downloader
  epub.py         # EPUB generation with three-level TOC
  vip.py          # VIP chapter processing (image download, GIF→PNG, OCR pipeline)
  ocr.py          # OCR engine (RapidOCR, image preprocessing, text extraction)
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

## VIP Chapter Processing

VIP chapters are detected during catalog parsing via `.icn_vip` badge.

**Chapter class has two parsers:**
- `PCChapter` / `MobileChapter` — normal chapters
- `VIPChapter` — VIP chapters (imports from `vip.py`)

**VIP image URL construction:**
```
API_VIP_IMAGE?op=getChapPic&cid=xxx&nid=xxx&font=16&lang=&w=5000
```
- `w=5000` ensures most paragraphs display on single lines for better OCR accuracy

## OCR Workflow

The OCR pipeline processes VIP chapter images through multiple stages:

```
Input: GIF image (w=5000)

1. GIF → PNG conversion
   gif_to_frames() → list[Image] (white background, RGB)

2. Remove left/right whitespace (original image)
   crop_whitespace() → cropped image
   - Find rows/columns with content (pixels < 128)
   - Crop to content bounds

3. Fragment by line gaps
   find_gaps() → list[(start, end)]
   - Find blank rows (no content)
   - Split into fragments at gaps ≥ threshold

4. Remove left/right whitespace (each fragment)
   crop_whitespace(fragment) → cropped fragment

5. Split fragments into strips
   - Each fragment may contain multiple lines
   - Split at blank rows within fragment

6. Remove left/right whitespace (each strip)
   crop_whitespace(strip) → cropped strip

7. OCR each strip
   - RapidOCR recognition
   - Sort by y-position
   - Filter: keep only text with Chinese characters

8. Merge results
   - Sort by strip ID
   - Concatenate text
```

**Key functions in `ocr.py`:**
- `gif_to_frames(gif_bytes)` — Split GIF into RGB frames
- `remove_pinyin(image)` — Convert to black/white binary
- `crop_whitespace(image)` — Remove blank borders
- `find_gaps(image, threshold)` — Find blank row gaps
- `split_at_gaps(image, max_height)` — Split at blank rows
- `ocr_image(source)` — Full OCR pipeline for URL/path
- `ocr_bytes(image_bytes)` — OCR from raw bytes
- `ocr_bytes_list(images)` — OCR from list of image bytes

**Dependencies:** `rapidocr_onnxruntime` (install with `uv sync --extra ocr`)

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

# Install with OCR support
uv sync --extra ocr

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

# Run OCR on an image
uv run python main.py ocr <image_url_or_path> -o output.txt
```

## MCP Tools Available

- `chrome-devtools-mcp` — Browser automation for diagnosing broken selectors. Use it to navigate pages, take screenshots, evaluate JS, and find correct CSS selectors when the spider breaks.
