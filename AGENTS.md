# AGENTS.md

## Project Overview

Multi-content-type web scraper for [SF Light Novel (sfacg.com)](https://book.sfacg.com) — a Chinese light novel, comic, and audiobook platform. Written in Python using `requests` + `BeautifulSoup`.

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
uv run python app.py  # Navigate to Account → Paste Cookie

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

**IMPORTANT: Only GIF is valid VIP chapter content.** If the fetched image is not GIF format, the VIP content was not successfully retrieved.

**VIP content format detection:**
- GIF → valid VIP chapter content, process normally
- Non-GIF (PNG/JPG etc.) → VIP content not retrieved, check request or authentication

### Method 1: Local OCR (RapidOCR)

Slower but works offline. Processes each line individually.

```
Input: GIF image (w=5000)

1. gif_to_frames() — GIF frame extraction
2. crop_whitespace() — crop whitespace margins
3. split_lines() — split by line gaps (>= 5px gaps)
4. remove_pinyin() — crop top 20% of each line
5. crop_whitespace() — crop again
6. _ocr_line() — RapidOCR recognition per line
7. Merge results by line_id
```

### Method 2: LLM Vision OCR (Recommended)

Fast and accurate. Uses DeepSeek Vision API.

```
Input: GIF image

1. gif_to_frames() — GIF frame extraction
2. split_by_height() — split into segments (max 1500px height)
3. For each segment → resize to max 1000px → upload to LLM
4. LLM recognizes Chinese text (no pinyin)
5. Local deduplication to remove overlapping content
```

**Performance comparison:**
| Method | Time | Quality |
|--------|------|---------|
| Local OCR + LLM correction | ~20 min | Medium |
| LLM Vision direct | ~1.5 min | High |

**Key functions in `ocr.py`:**
- `gif_to_frames(gif_bytes)` — GIF frame extraction
- `crop_whitespace(image)` — crop whitespace margins
- `find_line_gaps(gray_array, min_gap)` — find line gaps
- `split_lines(image, min_gap, min_height)` — split image by line gaps
- `remove_pinyin(image, pinyin_ratio)` — remove top pinyin area
- `_ocr_line(args, cpu_num_threads)` — single line OCR, returns (line_id, text)
- `_prepare_lines(gif_bytes)` — full preprocessing: GIF → frames → crop → split lines → remove pinyin
- `ocr_gif(gif_bytes, workers)` — full local OCR pipeline
- `ocr_image(image_source)` — entry function, supports URL/local path
- `prepare_lines_as_images(gif_bytes)` — returns PIL Image list for LLM Vision

**Key functions in `web_llm_vision.py`:**
- `WebLLMVision` — browser automation for LLM Vision API
- `_select_deepseek_vision_mode()` — select Vision mode in DeepSeek
- `_deepseek_upload_and_ask()` — upload image and get OCR result
- `_wait_for_deepseek_response()` — wait for response with stability check

**Dependencies:**
- Local OCR: `rapidocr_onnxruntime` (install with `uv sync --extra ocr`)
- LLM Vision: `playwright` (install with `uv sync --extra web && uv run playwright install chromium`)

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

## Important Files

- `common.gif` — Test VIP chapter image for OCR testing, **DO NOT DELETE**
