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
    MOBILE_BASE, PC_BASE, COMIC_BASE, PASSPORT_BASE,
    API_HTML5, API_COMIC_PICS, API_VIP_IMAGE,
    URL_NOVEL_INDEX, URL_NOVEL_MENU, URL_REVIEW_LIST, URL_REVIEW_DETAIL,
    URL_AUDIO, SELECTORS_PATH, COOKIE_PATH, AUDIOBOOKS_JSON,
    DEFAULT_DELAY, MAX_RETRIES, TIMEOUT,
    WORKERS_CHAPTER, WORKERS_IMAGE, WORKERS_AUDIO_CHAPTER,
    WORKERS_AUDIO_VOLUME, WORKERS_EPUB_IMG,
)
from .fetcher import Fetcher
from .auth import Auth
from .selectors import Selectors, SelectorError
from .ch import Chapter, MobileChapter, PCChapter, VIPChapter
from .book import Novel, Volume
from .comic import Comic, ComicChapter
from .audio import Audio, AudioChapter, AudioVolume
from .epub import download_epub
from .progress import ProgressTracker
from .utils import sanitize_filename, mobile_url, parse_volume_ul, run_tasks

__all__ = [
    'Fetcher', 'Auth',
    'Selectors', 'SelectorError',
    'Chapter', 'MobileChapter', 'PCChapter', 'VIPChapter',
    'Novel', 'Volume',
    'Comic', 'ComicChapter',
    'Audio', 'AudioChapter', 'AudioVolume',
    'download_epub',
    'ProgressTracker',
    'sanitize_filename', 'mobile_url', 'parse_volume_ul', 'run_tasks',
]
