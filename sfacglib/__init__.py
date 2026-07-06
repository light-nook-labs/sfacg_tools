from loguru import logger as _logger
from tqdm import tqdm as _tqdm

_logger.remove()


def _tqdm_sink(message):
    record = message.record
    if record['level'].no >= 30 or record['extra'].get('force'):
        _tqdm.write(message, end='')


_logger.add(_tqdm_sink, format='{time:HH:mm:ss} | {level: <8} | {message}')

from .audio import Audio, AudioChapter, AudioVolume
from .auth import Auth
from .base import Container, Item, Section
from .comic import Comic, ComicChapter
from .config import (
    API_BOOK,
    API_COMIC_PICS,
    API_COMIC_VIP,
    API_HTML5,
    API_VIP_IMAGE,
    AUDIOBOOKS_JSON,
    COMIC_BASE,
    COMIC_READER_BASE,
    COOKIE_PATH,
    DEFAULT_DELAY,
    MAX_RETRIES,
    MOBILE_BASE,
    OCR_BRIGHTNESS_THRESHOLD,
    OCR_STRIP_HEIGHT,
    OCR_WORKERS,
    PASSPORT_BASE,
    PC_BASE,
    SELECTORS_PATH,
    TIMEOUT,
    URL_AUDIO,
    URL_NOVEL_INDEX,
    URL_NOVEL_MENU,
    URL_REVIEW_DETAIL,
    URL_REVIEW_LIST,
    VIP_IMAGE_WIDTH,
    WORKERS_AUDIO_CHAPTER,
    WORKERS_AUDIO_VOLUME,
    WORKERS_CHAPTER,
    WORKERS_EPUB_IMG,
    WORKERS_IMAGE,
    Settings,
    VipMode,
    settings,
)
from .epub import convert_html_to_epub, convert_md_to_epub, download_epub
from .fetcher import Fetcher
from .models import Catalog, CatalogItem, CatalogSection, SearchItem
from .novel import Novel, NovelChapter, process_vip_chapter
from .ocr import (
    ChatBot,
    interactive_chat,
    merge_wrapped_lines,
    ocr_bytes,
    ocr_gif,
    ocr_image,
    remove_pinyin,
    remove_pinyin_gif,
    remove_pinyin_to_bytes,
)
from .progress import ProgressTracker
from .search import (
    NovelItem,
    get_author_works,
    get_related,
    predictive_comic,
    predictive_novel,
    search,
    search_comic,
    search_comic_api,
    search_lolobun,
    search_lolobun_comic,
    search_lolobun_novel,
    search_novel,
    search_novel_api,
)
from .selectors import SelectorError, Selectors
from .utils import mobile_url, parse_volume_ul, run_tasks, sanitize_filename, validate_gif

__all__ = [
    'API_BOOK',
    'OCR_BRIGHTNESS_THRESHOLD',
    'OCR_STRIP_HEIGHT',
    'OCR_WORKERS',
    'VIP_IMAGE_WIDTH',
    'Audio',
    'AudioChapter',
    'AudioVolume',
    'Auth',
    'Catalog',
    'CatalogItem',
    'CatalogSection',
    'ChatBot',
    'Comic',
    'ComicChapter',
    'Container',
    'Fetcher',
    'Item',
    'Novel',
    'NovelChapter',
    'NovelItem',
    'ProgressTracker',
    'SearchItem',
    'Section',
    'SelectorError',
    'Selectors',
    'Settings',
    'VipMode',
    'convert_html_to_epub',
    'convert_md_to_epub',
    'download_epub',
    'get_author_works',
    'get_related',
    'interactive_chat',
    'merge_wrapped_lines',
    'mobile_url',
    'ocr_bytes',
    'ocr_gif',
    'ocr_image',
    'parse_volume_ul',
    'predictive_comic',
    'predictive_novel',
    'process_vip_chapter',
    'remove_pinyin',
    'remove_pinyin_gif',
    'remove_pinyin_to_bytes',
    'run_tasks',
    'sanitize_filename',
    'search',
    'search_comic',
    'search_comic_api',
    'search_lolobun',
    'search_lolobun_comic',
    'search_lolobun_novel',
    'search_novel',
    'search_novel_api',
    'settings',
    'validate_gif',
]
