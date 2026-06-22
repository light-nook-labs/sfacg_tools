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
  ocr_fast.py     # Optimized local OCR (smart pinyin removal, rec_only, parallel)
  llm_vision.py   # LLM Vision API for OCR
  web_llm_vision.py # Browser-based LLM Vision (DeepSeek)
  chatbot.py      # Agent with tool calling (OCR, pinyin removal, batch ops)
  nlp.py          # NLP post-processing (merge wrapped lines)
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

main.py           # Unified CLI entry point
buildozer.spec    # Android APK build config
.cookies.json     # Saved session cookies — gitignored
.env              # Chatbot config (CHATBOT_BASE_URL, CHATBOT_API_KEY, CHATBOT_MODEL)
```

## Key Design Patterns

### Three-Layer Abstraction

All content types follow a three-layer hierarchy: Container → Section → Item. See [README.md](README.md#三层抽象) for details.

### Selector Registry

All CSS selectors live in `sfacglib/selectors.json`. When selectors break, update JSON — no code changes needed.

### Authentication

SFACG login requires Tencent CAPTCHA. Import cookies from browser DevTools. See [README.md](README.md#登录) for instructions.

### VIP Chapter Processing

VIP chapters detected via `.icn_vip` badge. Downloaded as `.gif` files, OCR is a separate step. See [README.md](README.md#vip-章节) for OCR workflow and performance comparison.

### Format Conversion

`convert.py` provides standalone format conversion. See [README.md](README.md#格式转换) for usage.

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

See [README.md](README.md#快速开始) for all CLI commands and GUI options.

## MCP Tools Available

- `chrome-devtools-mcp` — Browser automation for diagnosing broken selectors. Use it to navigate pages, take screenshots, evaluate JS, and find correct CSS selectors when the spider breaks.

## Important Files

- `common.gif` — Test VIP chapter image for OCR testing, **DO NOT DELETE**
- `ch_069_第六十八章_我们私奔吧！.gif` — Test GIF for Web LLM OCR prompt tuning. 5 segments (728x6021), last segment is empty (boundary test). Path: `output/反派小姐，瞎撩女主是会被清算的/vol_001_.../ch_069_第六十八章_我们私奔吧！.gif`
