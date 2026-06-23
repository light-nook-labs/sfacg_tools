from tqdm import tqdm as _tqdm
from loguru import logger as _logger

_logger.remove()

def _tqdm_sink(message):
    record = message.record
    if record['level'].no >= 30:
        _tqdm.write(message, end='')
    elif record['extra'].get('force'):
        _tqdm.write(message, end='')

_logger.add(_tqdm_sink, format='{time:HH:mm:ss} | {level: <8} | {message}')

from .config import (
    MOBILE_BASE, PC_BASE, COMIC_BASE, COMIC_READER_BASE, PASSPORT_BASE,
    API_HTML5, API_COMIC_PICS, API_VIP_IMAGE, API_COMIC_VIP,
    URL_NOVEL_INDEX, URL_NOVEL_MENU, URL_REVIEW_LIST, URL_REVIEW_DETAIL,
    URL_AUDIO, SELECTORS_PATH, COOKIE_PATH, AUDIOBOOKS_JSON,
    DEFAULT_DELAY, MAX_RETRIES, TIMEOUT,
    WORKERS_CHAPTER, WORKERS_IMAGE, WORKERS_AUDIO_CHAPTER,
    WORKERS_AUDIO_VOLUME, WORKERS_EPUB_IMG,
    VIP_IMAGE_WIDTH, OCR_STRIP_HEIGHT, OCR_WORKERS, OCR_BRIGHTNESS_THRESHOLD,
)
from .fetcher import Fetcher
from .auth import Auth
from .selectors import Selectors, SelectorError
from .ch import Chapter, MobileChapter, PCChapter, VIPChapter
from .base import Container, Section, Item
from .novel import Novel
from .comic import Comic, ComicChapter
from .audio import Audio, AudioChapter, AudioVolume
from .epub import download_epub, convert_html_to_epub, convert_md_to_epub
from .progress import ProgressTracker
from .utils import sanitize_filename, mobile_url, parse_volume_ul, run_tasks
from .vip import VipMode, process_vip_chapter
from .ocr_fast import (
    ocr_image, ocr_bytes, ocr_gif,
    prepare_lines_as_images, image_to_bytes,
    ocr_gif_with_llm, ocr_image_with_llm,
    remove_pinyin, remove_pinyin_gif, remove_pinyin_to_bytes,
)
from .llm_vision import LLMVision, LLMProvider, create_llm_vision
from .web_llm_vision import DeepSeekWebOCR, split_by_height, resize_to_max, deduplicate_texts, create_web_llm_vision
from .chatbot import ChatBot, interactive_chat

__all__ = [
    'Fetcher', 'Auth',
    'Selectors', 'SelectorError',
    'Chapter', 'MobileChapter', 'PCChapter', 'VIPChapter',
    'Container', 'Section', 'Item',
    'Novel',
    'Comic', 'ComicChapter',
    'Audio', 'AudioChapter', 'AudioVolume',
    'download_epub', 'convert_html_to_epub', 'convert_md_to_epub',
    'ProgressTracker',
    'sanitize_filename', 'mobile_url', 'parse_volume_ul', 'run_tasks',
    'VipMode', 'process_vip_chapter',
    'ocr_image', 'ocr_bytes', 'ocr_gif',
    'prepare_lines_as_images', 'image_to_bytes',
    'ocr_gif_with_llm', 'ocr_image_with_llm',
    'remove_pinyin', 'remove_pinyin_gif', 'remove_pinyin_to_bytes',
    'LLMVision', 'LLMProvider', 'create_llm_vision',
    'DeepSeekWebOCR', 'split_by_height', 'resize_to_max', 'deduplicate_texts',
    'ChatBot', 'interactive_chat',
    'VIP_IMAGE_WIDTH', 'OCR_STRIP_HEIGHT', 'OCR_WORKERS', 'OCR_BRIGHTNESS_THRESHOLD',
]
