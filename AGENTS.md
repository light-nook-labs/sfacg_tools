# AGENTS.md

## Project Overview

Multi-content-type web scraper for [SF Light Novel (sfacg.com)](https://book.sfacg.com) — a Chinese light novel, comic, and audiobook platform. Written in Python using `requests` + `BeautifulSoup`.

**Status:** Not finished. Learning project. No CLI — API changes frequently during development.

## Architecture

```
sfacglib/
  __init__.py     # Package exports
  base.py         # Abstract base classes: Container, Section, Item
  config.py       # Centralized constants + Pydantic Settings + migration
  fetcher.py      # Smart HTTP fetcher (rotating UA, retry, rate limiting, dual-session auth)
  auth.py         # Login, session persistence, cookie management (GetLoginInfo API)
  selectors.py    # CSS selector registry (loads from selectors.toml via tomllib)
  novel.py        # Novel downloader (Novel, NovelVolume, NovelChapter, ReviewComment, Review)
  comic.py        # Comic downloader (Comic, ComicChapter, ComicPage)
  audio.py        # Audiobook downloader (Audio, AudioVolume, AudioChapter)
  lolobun_novel.py # LoLoBun English novel downloader (LoLoBunNovel, LoLoBunNovelChapter)
  lolobun_comic.py # LoLoBun English comic downloader (LoLoBunComic, LoLoBunComicChapter)
  search.py       # Search API (keyword, related novels, author works)
  nlp.py          # NLP post-processing (merge wrapped lines)
  models/         # Pydantic models
    __init__.py   # Re-exports all catalog types
    catalog.py    # Per-type catalog models (NovelCatalog, ComicCatalog, AudioCatalog, etc.)
    search.py     # SearchItem model
  utils/          # Shared utilities
    __init__.py   # sanitize_filename, fix_url_protocol, validate_gif, run_tasks, load_json, save_json
    json.py       # JSON file utilities (load_json, save_json)
    convert.py    # Format conversion (HTML, EPUB, PDF — auto-detect novel/comic)
    epub.py       # EPUB generation with three-level TOC
  ocr/            # OCR package
    __init__.py   # Re-exports ChatBot, ocr_gif, remove_pinyin, etc.
    engine.py     # OCR engine (RapidOCR, smart pinyin removal, rec_only, parallel, GPU auto-detect)
    chatbot.py    # Agent with tool calling (OCR, pinyin removal, batch ops)

scripts/
  check_docs.py   # Verify AGENTS.md and README.md are in sync with codebase

opencode.json     # opencode project config
.env              # Chatbot config (CHATBOT_BASE_URL, CHATBOT_API_KEY, CHATBOT_MODEL)
```

## Content Structure

| Content | Container | Section | Item |
|---------|-----------|---------|------|
| Novel | Novel | NovelVolume | NovelChapter |
| Comic | Comic | (flat, chapters as sections) | (pages fetched dynamically) |
| Audio | Audio | AudioVolume | AudioChapter |
| Review | Review | (flat, comments as sections) | (reviews downloaded directly) |
| LoLoBun Novel | LoLoBunNovel | LoLoBunNovelVolume | LoLoBunNovelChapter |
| LoLoBun Comic | LoLoBunComic | (flat, chapters as sections) | (pages fetched via API) |

### Container

- Provides `setup()` — fetches metadata, downloads cover, generates catalog.json
- Provides `get_download_items()` — returns list of Items from catalog
- Provides `download(ext, item_prefix)` — downloads all content to a directory
- Provides `_download_cover()` — downloads cover image using PIL, saves as `cover.{ext}`
- Manages catalog.json, info.md

### Section

- Provides `get_items()` — returns list of Items
- Provides `download(dir_path, ext, item_prefix)` — downloads all items (used for partial/single-section downloads)

### Item

- Provides `download(save_path)` — downloads single item
- Provides `to_dict()` — serialization

### Factory Methods

```python
novel = Novel(43708)
vol = novel.create_vol(1)        # → NovelVolume
chapter = vol.create_chapter(3)  # → NovelChapter
review = novel.create_review()   # → Review (independent)

comic = Comic('LYZJ')           # takes cid, not URL

lolobun_novel = LoLoBunNovel(5320265)  # takes nid from lolobun.com
lolobun_comic = LoLoBunComic(20106)    # takes cid from lolobun.com
```

## Download Flow

`container.download()` always produces the actual format directory:
- Novel → `.md` files
- Comic → `.jpg` files
- Audio → `.mp3` files

Conversion to other formats (HTML, EPUB, PDF) is done by `utils/convert.py` from the directory.

### Concurrency Model

Hierarchical thread pool (Novel/Comic/Review):
- `Container.download()` submits `section.download()` concurrently
- `Section.download()` submits `item.download()` concurrently
- All share a single `ThreadPoolExecutor(max_workers=WORKERS_CHAPTER)`

Audio uses async I/O:
- `Audio.setup()` pre-fetches MP3 URLs via `ThreadPoolExecutor(max_workers=WORKERS_AUDIO_CHAPTER)`
- `Audio.download()` uses `asyncio.run()` with `aiohttp.ClientSession`
- `Semaphore(50)` limits concurrent connections
- Streaming download (no full file in memory)

### Container Lifecycle

```python
novel = Novel(nid, output_dir=Path('~/Downloads'), fetcher=fetcher)
# __init__ calls setup() which fetches homepage + catalog, generates catalog.json
# setup() returns True if successful, False if not
novel.download()                  # downloads all chapters as .md
novel.download(ext='epub')        # downloads then converts to epub

vol = novel.create_vol(1)
vol.download(dir_path)            # download single volume

chapter = vol.create_chapter(3)
chapter.download(save_path)       # download single chapter

review = novel.create_review()
review.download()                 # reviews as .md in reviews/ dir
```

## Key Design Patterns

### Selector Registry

All CSS selectors live in `sfacglib/selectors.toml`. When selectors break, update TOML — no code changes needed. Loaders use stdlib `tomllib` (Python >=3.11).

### Config Directory

Persistent config files live in `~/.config/sfacg/`:
- `selectors.toml` — CSS selectors
- `audiobooks.json` — cached audiobook catalog
- `.cookies.json` — login cookies (0600 permissions)

Fallback copies exist in the package dir and are auto-migrated on first run.

### Authentication

SFACG login requires Tencent CAPTCHA. Import cookies from browser DevTools. See README for instructions.

Cookie validation uses `passport.sfacg.com/Ajax/GetLoginInfo.ashx` API. Cookies are set in request header directly for correct domain matching.

### VIP Chapter Processing

VIP chapters have two types tracked by `NovelCatalogItem.is_gif` (boolean):
- `False` (free or image VIP) — normal download
- `True` (encrypted VIP) — downloaded as `.gif`, requires OCR

Detection: `Novel._parse_pc_catalog()` checks for `.icn_vip` and `.icn` span content during catalog generation (not at download time).

Download routing in `NovelChapter.download()`:
- Encrypted VIP (`is_gif=True`): `_download_vip_gif()` → `.gif` + OCR
- Free/Image VIP (`is_gif=False`): `_download_normal()` → `.md` or `_download_vip_image()` → `.jpg`

### Dual-Session Fetcher

- `public_session` — delay=0, no rate limit, for public content
- `auth_session` — delay=0.2s, max_concurrent=10, for VIP content
- VIP calls pass `vip=True` to use auth session

### Catalog Format

`catalog.json` is generated during `Container.setup()` and stores the complete structure:
- `id`, `title`, `author`, `cover` — metadata
- `cover_file` — local cover filename (e.g., `cover.jpg`)
- `info_file` — filename for info.md (novel only)
- `sections[]` — list of volumes/chapters:
  - `idx`, `title`, `vol_id?`, `dir`
  - `items[]` — list of chapters/pages:
    - `idx`, `title`, `chapter_id?`, `is_gif`, `file`
    - Audio: `mp3_url` (pre-fetched during setup)
    - Comic: `image_urls[]` (pre-fetched during setup)

`config.py` uses `pydantic-settings` for `.env` configuration via the `Settings` class.

### Audio Catalog Format

Audio has a simplified catalog (no `author`, `info_file`, or per-item `cover`):
- `id`, `title`, `cover` — metadata (cover from chapter page `<img>`)
- `cover_file` — local cover filename
- `sections[]` — list of volumes:
  - `idx`, `title`, `dir`
  - `items[]` — list of chapters:
    - `idx`, `title`, `url` (full URL), `file`, `mp3_url`

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
- Concurrency: hierarchical `ThreadPoolExecutor` for parallel downloads (Novel/Comic/Review), `asyncio` + `aiohttp` for Audio
- Cookie file: stored in `~/.config/sfacg/.cookies.json` with `0600` permissions
- Config files: `selectors.toml`, `audiobooks.json` in `~/.config/sfacg/` (with package fallbacks)
- Directory mode: all formats default to directory mode (one file per chapter/page)
- catalog.json: metadata + ordered chapter mapping for assembly (no status/error fields)
- Single file/EPUB: assembled from directory structure
- No comments in code unless explicitly asked

## MCP Tools Available

- `chrome-devtools-mcp` — Browser automation for diagnosing broken selectors. Use it to navigate pages, take screenshots, evaluate JS, and find correct CSS selectors when the spider breaks.

## Important Files

- `common.gif` — Test VIP chapter image for OCR testing, **DO NOT DELETE**
- `selectors.toml` — CSS selectors (both package dir and `~/.config/sfacg/`)
- `audiobooks.json` — Audiobook catalog (both package dir and `~/.config/sfacg/`)
