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
from .chatbot import ChatBot, interactive_chat
from .comic import Comic, ComicChapter
from .config import (
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
from .llm_vision import LLMProvider, LLMVision, create_llm_vision
from .models import Catalog, CatalogItem, CatalogSection, SearchItem
from .novel import Novel, NovelChapter, process_vip_chapter
from .ocr_fast import (
    image_to_bytes,
    ocr_bytes,
    ocr_gif,
    ocr_gif_with_llm,
    ocr_image,
    ocr_image_with_llm,
    prepare_lines_as_images,
    remove_pinyin,
    remove_pinyin_gif,
    remove_pinyin_to_bytes,
)
from .progress import ProgressTracker
from .search import (
    get_author_works,
    get_related,
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
from .web_llm_vision import DeepSeekWebOCR, create_web_llm_vision, deduplicate_texts, resize_to_max, split_by_height

__all__ = [
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
    'DeepSeekWebOCR',
    'Fetcher',
    'Item',
    'LLMProvider',
    'LLMVision',
    'Novel',
    'NovelChapter',
    'ProgressTracker',
    'SearchItem',
    'Section',
    'SelectorError',
    'Selectors',
    'Settings',
    'VipMode',
    'convert_html_to_epub',
    'convert_md_to_epub',
    'create_llm_vision',
    'deduplicate_texts',
    'download_epub',
    'get_author_works',
    'get_related',
    'image_to_bytes',
    'interactive_chat',
    'mobile_url',
    'ocr_bytes',
    'ocr_gif',
    'ocr_gif_with_llm',
    'ocr_image',
    'ocr_image_with_llm',
    'parse_volume_ul',
    'prepare_lines_as_images',
    'process_vip_chapter',
    'remove_pinyin',
    'remove_pinyin_gif',
    'remove_pinyin_to_bytes',
    'resize_to_max',
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
    'split_by_height',
    'validate_gif',
]
