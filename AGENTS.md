# AGENTS.md

## Project Overview

Multi-content-type web scraper for [SF Light Novel (sfacg.com)](https://book.sfacg.com) — a Chinese light novel, comic, and audiobook platform. Written in Python using `requests` + `BeautifulSoup`.

**Status:** Not finished. Learning project.

## Architecture

```
sfacglib/
  __init__.py     # Package exports
  models/         # Pydantic data models
    __init__.py   # Re-exports SearchItem, Catalog, CatalogSection, CatalogItem
    search.py     # SearchItem model
    catalog.py    # Catalog, CatalogSection, CatalogItem models
  base.py         # Abstract base classes: Container, Section, Item + _filter_items
  config.py       # Centralized constants + Pydantic Settings + VipMode enum + migration
  fetcher.py      # Smart HTTP fetcher (rotating UA, retry, rate limiting, dual-session auth)
  auth.py         # Login, session persistence, cookie management (GetLoginInfo API)
  selectors.py    # CSS selector registry (loads from selectors.toml via tomllib)
  novel.py        # Novel downloader (Novel, NovelVolume, NovelChapter, ReviewComment)
  comic.py        # Comic downloader (Comic, ComicChapter)
  audio.py        # Audiobook downloader (Audio, AudioVolume, AudioChapter)
  search.py       # Search API (keyword, related novels, author works)
  nlp.py          # NLP post-processing (merge wrapped lines)
  progress.py     # Progress tracking with SQLite (batch commits, finalize_task)
  utils/          # Shared utilities
    __init__.py   # sanitize_filename, fix_url_protocol, validate_gif, run_tasks, etc.
    convert.py    # Format conversion (HTML, EPUB, PDF — auto-detect novel/comic)
    epub.py       # EPUB generation with three-level TOC
  ocr/            # OCR package
    __init__.py   # Re-exports ChatBot, ocr_gif, remove_pinyin, etc.
    engine.py     # OCR engine (RapidOCR, smart pinyin removal, rec_only, parallel, GPU auto-detect)
    chatbot.py    # Agent with tool calling (OCR, pinyin removal, batch ops)

main.py           # Unified CLI entry point
buildozer.spec    # Android APK build config
.env              # Chatbot config (CHATBOT_BASE_URL, CHATBOT_API_KEY, CHATBOT_MODEL)
```

## Key Design Patterns

### ChatBot Agent

`ocr/chatbot.py` implements an agent (not just a chatbot) that can:
- Chat with users naturally
- Execute tasks via tool calling (OCR, pinyin removal, batch operations)
- Refuse complex tasks and output CLI commands instead

See [README.md](README.md#chatbot-agent) for usage examples.

### Three-Layer Abstraction

All content types follow a three-layer hierarchy: Container → Section → Item.

| Content | Container | Section | Item |
|---------|-----------|---------|------|
| Novel | Novel | NovelVolume | NovelChapter |
| Comic | Comic | ComicChapter | ComicPage |
| Audio | Audio | AudioVolume | AudioChapter |
| Review | Review | ReviewSection | ReviewComment |

**Container** provides concrete `download()`, `get_info()`, `get_sections()`. Subclasses implement `_download_item()`.

Review is independent — has own catalog.json, progress.db, dir. Can bind to Novel (`Review(novel=novel)`) or standalone (`Review(nid=5976, title='...', output_dir='./')`). Review progress tracker only tracks review-level downloads, not sub-comments (which are short JSON).

### Selector Registry

All CSS selectors live in `sfacglib/selectors.toml`. When selectors break, update TOML — no code changes needed. Loaders use stdlib `tomllib` (Python >=3.11).

### Config Directory

Persistent config files live in `~/.config/sfacg/`:
- `selectors.toml` — CSS selectors
- `audiobooks.json` — cached audiobook catalog
- `.cookies.json` — login cookies (0600 permissions)

Fallback copies exist in the package dir and are auto-migrated on first run.

### Authentication

SFACG login requires Tencent CAPTCHA. Import cookies from browser DevTools. See [README.md](README.md#登录) for instructions.

Cookie validation uses `passport.sfacg.com/Ajax/GetLoginInfo.ashx` API. Cookies are set in request header directly for correct domain matching.

### VIP Chapter Processing

VIP chapters have three modes tracked by `CatalogItem.vip_mode` (string):
- `''` (free) — no special handling
- `'encrypted'` — downloaded as `.gif`, requires OCR
- `'image'` — has `\ue905` icon in catalog, downloaded as `.md` with embedded images

Detection: `Novel._parse_pc_catalog()` checks for `.icn_vip` and `.icn` span content. VIP GIF download constructs URL directly from chapter ID, includes `Referer` header.

See [README.md](README.md#vip-章节与-ocr) for OCR workflow and performance comparison.

### Format Conversion

`utils/convert.py` provides standalone format conversion for both novels and comics. Auto-detects content type from file extensions. HTML output features sidebar TOC, responsive layout, and print-to-PDF support. See [README.md](README.md#格式转换) for usage.

### Search API

`search.py` provides novel/comic search via `s.sfacg.com` HTML scraping and `m.sfacg.com` JSON API. Also supports related novels (`get_related`) and author works (`get_author_works`). See [README.md](README.md#搜索) for usage.

### Pydantic Models

`models/` package defines data models for type safety and validation:
- `SearchItem` — search results
- `Catalog` — nested catalog structure (with `load()`/`save()`/`_migrate()`)
- `CatalogSection` — volume/chapter section
- `CatalogItem` — individual chapter/page (fields: idx, title, url, file, vip_mode)

`config.py` uses `pydantic-settings` for `.env` configuration via the `Settings` class.

### Container Lifecycle

```python
novel = Novel(nid, output_dir=Path('~/Downloads'), fetcher=fetcher)
# __init__ validates ID, creates dir_path, catalog.json, info.md, progress.db
novel.download(ext='md', range_str='1-10')  # downloads missing items only
novel._download_reviews(ext='md')           # optional: download reviews to reviews/ subdir
```

### Concurrency Model

Hierarchical thread pool — `Container.download()` submits `section.download()` concurrently, each `section.download()` submits `item.download()` concurrently. All share a single `ThreadPoolExecutor(max_workers=50)`.

### Dual-Session Fetcher

- `public_session` — delay=0, no rate limit, for public content
- `auth_session` — delay=0.2s, max_concurrent=10, for VIP content
- VIP calls pass `vip=True` to use auth session

### Progress Tracking

SQLite-based with batch commits (`BATCH_SIZE=20`). `ProgressTracker` uses `threading.Lock`. `finalize_task()` calls `flush()` before reading completion status.

## Coding Conventions

> [!CRITICAL]
> **On every refactor, module move, file add/delete, or API change, you MUST update both `AGENTS.md` and `README.md`.**
> This is mandatory — skipping doc updates is equivalent to leaving the task incomplete.
>
> Checklist:
> - Architecture tree (files added/moved/deleted?)
> - Key design patterns (behavior changed?)
> - Coding conventions (conventions changed?)
> - README project structure (matches actual directories?)
> - README import paths (match actual code?)
>
> After updating, run `uv run python scripts/check_docs.py` to verify docs are in sync.

- Python 3.11+, use `uv` for package management (not pip)
- Package imports use relative imports within sfacglib (e.g. `from .fetcher import Fetcher`)
- All constants in `sfacglib/config.py` (no hardcoded URLs/paths)
- Logging via `loguru` (not stdlib logging)
- Rate limiting: always respect delays between requests (0.2s–3s depending on context)
- Concurrency: flat `ThreadPoolExecutor` for parallel downloads
- Progress: `ProgressTracker` with SQLite (thread-safe with `threading.Lock`, batch commits)
- Cookie file: stored in `~/.config/sfacg/.cookies.json` with `0600` permissions
- Config files: `selectors.toml`, `audiobooks.json` in `~/.config/sfacg/` (with package fallbacks)
- Directory mode: all formats default to directory mode (one file per chapter/page)
- catalog.json: metadata + ordered chapter mapping for assembly (no status/error fields)
- Single file/EPUB: assembled from directory structure
- No comments in code unless explicitly asked

## Running

See [README.md](README.md#快速开始) for all CLI commands and GUI options.

## MCP Tools Available

- `chrome-devtools-mcp` — Browser automation for diagnosing broken selectors. Use it to navigate pages, take screenshots, evaluate JS, and find correct CSS selectors when the spider breaks.

## Important Files

- `common.gif` — Test VIP chapter image for OCR testing, **DO NOT DELETE**
- `selectors.toml` — CSS selectors (both package dir and `~/.config/sfacg/`)
- `audiobooks.json` — Audiobook catalog (both package dir and `~/.config/sfacg/`)
- `review_*.md` — Review files (downloaded per novel, in `{novel_dir}/reviews/`)
