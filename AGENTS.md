# AGENTS.md

## Project Overview

Multi-content-type web scraper for [SF Light Novel (sfacg.com)](https://book.sfacg.com) — a Chinese light novel, comic, and audiobook platform. Written in Python using `requests` + `BeautifulSoup`.

**Status:** Not finished. Learning project.

## Architecture

```
sfacglib/
  __init__.py     # Package exports
  base.py         # Abstract base classes: Container, Section, Item
  config.py       # Centralized constants (URLs, paths, workers)
  fetcher.py      # Smart HTTP fetcher (rotating UA, retry, rate limiting, auth)
  auth.py         # Login, session persistence, cookie management
  selectors.py    # CSS selector registry (loads from selectors.json)
  selectors.json  # All CSS selectors, organized by page type
  ch.py           # Chapter content fetcher (mobile + PC + VIP endpoints)
  novel.py        # Novel downloader (NovelVolume, NovelChapter, ReviewComment)
  comic.py        # Comic downloader (ComicChapter, ComicPage)
  audio.py        # Audiobook downloader (AudioVolume, AudioChapter)
  epub.py         # EPUB generation with three-level TOC
  convert.py      # Format conversion (HTML, EPUB, PDF)
  vip.py          # VIP chapter processing (image download, GIF→PNG, OCR pipeline)
  ocr.py          # OCR engine (RapidOCR, image preprocessing, text extraction)
  llm_vision.py   # LLM Vision API for OCR
  web_llm_vision.py # Browser-based LLM Vision
  progress.py     # Progress tracking with SQLite
  utils.py        # Shared utilities
  audiobooks.json # Cached audiobook catalog
  ui/
    __init__.py   # UI entry point
    pc/
      __init__.py
      app.py      # CustomTkinter main window
      novel_tab.py
      comic_tab.py
      audio_tab.py
      settings_tab.py
    mobile/
      __init__.py
      app.py      # Flet mobile app (Flutter-based)
    web/
      __init__.py
      server.py   # FastAPI web server
      templates/
        index.html

app.py            # Flet Material Design UI (Desktop/Web/Android/iOS)
main.py           # Unified CLI entry point
build.sh          # Build script (desktop/web/apk/ios)
buildozer.spec    # Android APK build config
.cookies.json     # Saved session cookies — gitignored
```

## Three-Layer Abstraction

All content types follow a three-layer hierarchy:

| Content | Container | Section | Item |
|---------|-----------|---------|------|
| Novel | Novel | NovelVolume | NovelChapter |
| Comic | Comic | ComicChapter | ComicPage |
| Audio | Audio | AudioVolume | AudioChapter |
| Reviews | Novel | ReviewSection | ReviewComment |

**Base classes in `base.py`:**
- `Container` - Top-level entity with `get_info()`, `get_sections()`, `download()`
- `Section` - Middle layer with `get_items()`
- `Item` - Atomic unit with `download(save_path)`

**Directory structure:**
```
{title}/
  catalog.json          # Metadata + sections + items mapping
  info.md               # Content info
  001_{section_title}/  # Volume/Chapter with ID prefix
    001_{item_title}.md # Chapter/Page/Comment with ID prefix
    002_{item_title}.md
  002_{section_title}/
    ...
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

## Format Conversion

The `convert.py` module provides standalone format conversion tools:

```python
# Independent usage
from sfacglib.convert import convert_to_html, convert_to_epub, convert_to_pdf, convert_comic

# Convert to specific format
convert_to_html('./output/落樱之剑', local_images=True)
convert_to_epub('./output/落樱之剑')
convert_to_pdf('./output/落樱之剑', padding=0)

# Batch convert
convert_comic('./output/落樱之剑', formats=['html', 'epub', 'pdf'], padding=0)
```

**CLI usage:**
```bash
uv run python main.py convert <comic_dir> -f html,epub,pdf -p 0
```

**PDF padding:**
- `padding=0` — no margin, images fill entire page
- `padding=20` — 20pt margin around images

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

**VIP content validation (`vip.py`):**
- `_validate_gif(gif_bytes, expected_width)` — checks format is GIF and width matches expected `w` parameter
- `_vip_rate_limit()` — global lock + random delay (2-5s) between VIP requests
- Anti-scraping detection: placeholder images (wrong format, wrong width) trigger `AntiScrapingError`

**Novel download workflow (`novel.py`):**
- `Novel.download_novel()` — downloads all chapters with resume support
- Normal chapters → `.md` files via `PCChapter`
- VIP chapters → `.gif` files via `_download_vip_gif()` (no OCR during download)
- `ocr_novel_gifs(nid, path)` — separate OCR step, uses `ocr_fast.py`
- `AntiScrapingError` (in `base.py`) — stops all downloads immediately
- `ValueError` (no subscription) — skips chapter, marks as failed in tracker
- Progress tracked in SQLite (`progress.db`) with resume on restart
- Directory scan on start: existing .gif/.md files auto-marked as done in tracker

## OCR Workflow

**IMPORTANT: Only GIF is valid VIP chapter content.** If the fetched image is not GIF format, the VIP content was not successfully retrieved.

**VIP content format detection:**
- GIF → valid VIP chapter content, process normally
- Non-GIF (PNG/JPG etc.) → VIP content not retrieved, check request or authentication

### Method 1: Local OCR (RapidOCR) + NLP — Recommended

Fast, offline, pure CPU. Best speed/quality ratio.

```
Input: GIF image (w=5000)

1. gif_to_frames() — GIF frame extraction
2. split_lines() — split by line gaps (>= 5px gaps)
3. remove_pinyin() — smart pinyin removal (stroke continuity analysis, max_run >= 10)
4. _ocr_line() — RapidOCR recognition per line (rec_only mode, skip detection)
5. merge_wrapped_lines() — NLP post-processing: merge image-width line breaks
```

**Performance:** ~57s/GIF, 50 chars/s, pure CPU, 4 threads

### Method 2: DeepSeek Web LLM OCR

Browser automation. Accurate but slower, has occasional hallucination errors.

```
Input: GIF image

1. gif_to_frames() — GIF frame extraction
2. split_by_height() — split into segments (max 1500px height)
3. For each segment → new page → navigate to DeepSeek → select Vision mode
4. Upload image → send prompt → wait for response
5. _fix_inline_spaces() — post-process: remove spaces between Chinese chars
6. deduplicate_texts() — merge overlapping segments
```

**Performance:** ~92s/GIF, 23.5 chars/s, requires browser + network

### Performance Comparison (same GIF: ch_081)

| Method | Time | Chars | Accuracy |
|--------|------|-------|----------|
| Local OCR only | 39.2s | 2020 | Low (乱码, 错字) |
| Local OCR + LLM correction | 66.4s | 2074 | High (修正所有乱码) |
| DeepSeek Web LLM | 91.7s | 2153 | Near 100% (少量幻觉) |

**Recommendation:** Local OCR + NLP for speed, LLM correction for quality.

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

**Key functions in `ocr_fast.py`:**
- Optimized local OCR with smart pinyin removal and rec_only mode
- `ocr_gif(gif_bytes, workers, cpu_num_threads)` — fast OCR pipeline (6x faster than ocr.py)
- Smart pinyin removal: uses stroke continuity analysis (`max_run >= 10`) instead of fixed 20% crop
- `rec_only` mode: skips text detection (uses `use_det=False`) since line positions are known from `split_lines`
- Parallel recognition: `ThreadPoolExecutor(max_workers=4)` for concurrent line OCR
- `_find_text_start_vectorized(line_gray, min_stroke_run)` — finds where pinyin ends and text begins
- `_remove_pinyin_from_image(gray, lines_bounds)` — removes pinyin from all lines using numpy operations

**Key functions in `web_llm_vision.py`:**
- `DeepSeekWebOCR` — browser automation for DeepSeek Web LLM OCR
- `_navigate_to_deepseek()` — navigate to DeepSeek and select Vision mode
- `_upload_and_ask()` — upload image and get OCR result
- `_wait_for_response()` — wait for response with stability check
- `_fix_inline_spaces()` — remove spaces between Chinese chars
- `split_by_height()` — split image into segments by max height
- `resize_to_max()` — resize image to max dimension
- `deduplicate_texts()` — merge overlapping text segments

**Key functions in `nlp.py`:**
- `merge_wrapped_lines(text)` — merge lines broken by image width into continuous paragraphs

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
- Progress: single `tqdm` bar with `threading.Lock` for thread-safe updates
- Directory mode: all formats default to directory mode (one file per chapter/page)
- catalog.json: metadata + ordered chapter mapping for assembly
- Single file/EPUB: assembled from directory structure
- No comments in code unless explicitly asked

## Running

```bash
# Install dependencies
uv sync

# Install with OCR support
uv sync --extra ocr

# Run PC GUI (CustomTkinter)
uv run python main.py app

# Run Mobile GUI (Flet/Flutter)
uv run python main.py mobile --target app

# Build APK
uv run python main.py mobile --target apk

# Run Web UI (FastAPI)
uv run python main.py web

# Run CLI - novel
uv run python main.py novel 43708 -f epub -o ./output/

# Run CLI - novel with reviews
uv run python main.py novel 43708 -f epub -r -o ./output/

# Run CLI - comic
uv run python main.py comic <comic_url> -o ./output/

# Run CLI - comic with format
uv run python main.py comic <comic_url> -f epub -o ./output/

# Convert comic directory to other formats
uv run python main.py convert <comic_dir> -f html,epub,pdf

# Run CLI - audio
uv run python main.py audio <id> -o ./output/

# Run CLI - reviews only
uv run python main.py review <novel_url> -o ./output/

# Run OCR on an image
uv run python main.py ocr <image_url_or_path> -o output.txt
```

## MCP Tools Available

- `chrome-devtools-mcp` — Browser automation for diagnosing broken selectors. Use it to navigate pages, take screenshots, evaluate JS, and find correct CSS selectors when the spider breaks.

## Important Files

- `common.gif` — Test VIP chapter image for OCR testing, **DO NOT DELETE**
- `ch_069_第六十八章_我们私奔吧！.gif` — Test GIF for Web LLM OCR prompt tuning. 5 segments (728x6021), last segment is empty (boundary test). Path: `output/反派小姐，瞎撩女主是会被清算的/vol_001_.../ch_069_第六十八章_我们私奔吧！.gif`
