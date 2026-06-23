from pathlib import Path
from pydantic_settings import BaseSettings

PACKAGE_DIR = Path(__file__).parent
PROJECT_DIR = PACKAGE_DIR.parent

_CONFIG_DIR = Path.home() / '.config' / 'sfacg'

MOBILE_BASE = 'https://m.sfacg.com'
PC_BASE = 'https://book.sfacg.com'
COMIC_BASE = 'https://mm.sfacg.com'
COMIC_READER_BASE = 'https://manhua.sfacg.com'
PASSPORT_BASE = 'https://passport.sfacg.com'
SEARCH_BASE = 'https://s.sfacg.com'

API_HTML5 = f'{MOBILE_BASE}/API/HTML5.ashx'
API_COMIC_PICS = f'{COMIC_BASE}/ajax/Common.ashx'
API_VIP_IMAGE = f'{PC_BASE}/ajax/ashx/common.ashx'
API_COMIC_VIP = f'{COMIC_READER_BASE}/ajax/Common.ashx'

VIP_IMAGE_WIDTH: int = 5000
VIP_DELAY_RANGE: tuple[float, float] = (2.0, 5.0)
VIP_RETRY_DELAYS: list[int] = [10, 20, 40]
VIP_TIMEOUT: tuple[int, int] = (10, 20)

OCR_STRIP_HEIGHT: int = 800
OCR_WORKERS: int = 4
OCR_BRIGHTNESS_THRESHOLD: int = 130
OCR_WHITESPACE_THRESHOLD: int = 250
OCR_DARK_PIXEL_THRESHOLD: int = 200
OCR_MIN_GAP: int = 5
OCR_MIN_LINE_HEIGHT: int = 10
OCR_MIN_STROKE_RUN: int = 10

COOKIE_DOMAIN: str = '.sfacg.com'

LLM_MAX_TOKENS: int = 4096
LLM_TEMPERATURE: float = 0.1
LLM_TIMEOUT: int = 120

CHATBOT_MAX_FILE_SIZE: int = 500_000
CHATBOT_MAX_PAGES: int = 100

SEARCH_SNIPPET_LENGTH: int = 200
REVIEW_PAGE_SIZE: int = 60

CORRECT_OCR_SYSTEM_PROMPT = """你是一个专业的中文OCR文本纠错助手。你的任务是纠正OCR识别产生的错误，包括：

1. 乱码/错别字：修正识别错误的汉字（如"已"→"己"，"末"→"未"）
2. 标点符号：修正全角/半角混用、缺失的标点
3. 段落断行：合并被错误断开的句子，保留合理的段落分隔
4. OCR伪影：删除页码、页眉页脚、乱码符号等非正文内容
5. 繁简转换：如有需要，统一为简体中文

规则：
- 保持原文风格和语气不变
- 不要添加或删减内容
- 不要改变原文意思
- 只修正明显的OCR错误，不要"润色"文字
- 如果原文看起来已经正确，直接返回原文
- 返回纠正后的纯文本，不要加任何解释"""


URL_NOVEL_INDEX = f'{MOBILE_BASE}/b/'
URL_NOVEL_MENU = f'{MOBILE_BASE}/i/'
URL_REVIEW_LIST = f'{MOBILE_BASE}/cmt/l/list/'
URL_REVIEW_DETAIL = f'{MOBILE_BASE}/cmt/l/'
URL_AUDIO = f'{MOBILE_BASE}/ai/'
URL_LOGIN_PC = f'{PASSPORT_BASE}/Login.aspx'
URL_LOGIN_API_PC = f'{PASSPORT_BASE}/Ajax/QuickLogin.ashx'
URL_LOGIN_API_MOB = f'{PASSPORT_BASE}/Ajax/QuickLoginCross.ashx'
URL_CHECK_AUTH = f'{MOBILE_BASE}/'

SELECTORS_PATH: Path = PACKAGE_DIR / 'selectors.json'
COOKIE_PATH: Path = _CONFIG_DIR / '.cookies.json'
AUDIOBOOKS_JSON: Path = PACKAGE_DIR / 'audiobooks.json'

DEFAULT_DELAY: float = 0.2
MAX_RETRIES: int = 3
TIMEOUT: tuple[int, int] = (15, 30)

WORKERS_CHAPTER: int = 50
WORKERS_IMAGE: int = 20
WORKERS_AUDIO_CHAPTER: int = 20
WORKERS_AUDIO_VOLUME: int = 5
WORKERS_EPUB_IMG: int = 10


class Settings(BaseSettings):
    cookie: str = ''
    chatbot_base_url: str = ''
    chatbot_api_key: str = ''
    chatbot_model: str = ''
    llm_api_key: str = ''
    llm_base_url: str = ''
    llm_model: str = ''

    model_config = {
        'env_file': str(PROJECT_DIR / '.env'),
        'env_file_encoding': 'utf-8',
        'extra': 'ignore',
    }


settings = Settings()

__all__ = [
    'PACKAGE_DIR', 'PROJECT_DIR',
    'MOBILE_BASE', 'PC_BASE', 'COMIC_BASE', 'COMIC_READER_BASE', 'PASSPORT_BASE', 'SEARCH_BASE',
    'API_HTML5', 'API_COMIC_PICS', 'API_VIP_IMAGE', 'API_COMIC_VIP',
    'URL_NOVEL_INDEX', 'URL_NOVEL_MENU', 'URL_REVIEW_LIST', 'URL_REVIEW_DETAIL',
    'URL_AUDIO', 'URL_LOGIN_PC', 'URL_LOGIN_API_PC', 'URL_LOGIN_API_MOB', 'URL_CHECK_AUTH',
    'SELECTORS_PATH', 'COOKIE_PATH', 'AUDIOBOOKS_JSON',
    'DEFAULT_DELAY', 'MAX_RETRIES', 'TIMEOUT',
    'WORKERS_CHAPTER', 'WORKERS_IMAGE', 'WORKERS_AUDIO_CHAPTER',
    'WORKERS_AUDIO_VOLUME', 'WORKERS_EPUB_IMG',
    'VIP_IMAGE_WIDTH', 'VIP_DELAY_RANGE', 'VIP_RETRY_DELAYS', 'VIP_TIMEOUT',
    'OCR_STRIP_HEIGHT', 'OCR_WORKERS', 'OCR_BRIGHTNESS_THRESHOLD',
    'OCR_WHITESPACE_THRESHOLD', 'OCR_DARK_PIXEL_THRESHOLD',
    'OCR_MIN_GAP', 'OCR_MIN_LINE_HEIGHT', 'OCR_MIN_STROKE_RUN',
    'COOKIE_DOMAIN',
    'LLM_MAX_TOKENS', 'LLM_TEMPERATURE', 'LLM_TIMEOUT',
    'CHATBOT_MAX_FILE_SIZE', 'CHATBOT_MAX_PAGES',
    'SEARCH_SNIPPET_LENGTH', 'REVIEW_PAGE_SIZE',
    'CORRECT_OCR_SYSTEM_PROMPT',
    'Settings', 'settings',
]
