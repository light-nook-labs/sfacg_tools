import tempfile
import time
import random
import threading
from enum import Enum
from pathlib import Path
from io import BytesIO
from loguru import logger
from PIL import Image

from .fetcher import Fetcher
from .config import OCR_WORKERS

_VIP_DELAY_RANGE = (2.0, 5.0)
_VIP_RETRY_DELAYS = [10, 20, 40]

_vip_lock = threading.Lock()
_vip_last_request = 0.0


def _validate_gif(gif_bytes: bytes, expected_width: int = 0) -> tuple[bool, str]:
    try:
        with Image.open(BytesIO(gif_bytes)) as img:
            if img.format != 'GIF':
                return False, f'not GIF (format={img.format}, size={img.size})'
            w, h = img.size
            if expected_width and w != expected_width:
                return False, f'width mismatch ({w} != expected {expected_width})'
            return True, f'{w}x{h}'
    except Exception as e:
        return False, f'invalid: {e}'


def _vip_rate_limit():
    global _vip_last_request
    with _vip_lock:
        now = time.time()
        elapsed = now - _vip_last_request
        delay = random.uniform(*_VIP_DELAY_RANGE)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        _vip_last_request = time.time()


class VipMode(Enum):
    """Novel VIP chapter processing modes."""
    OCR = 'ocr'
    RAW = 'raw'
    LLM = 'llm'
    DEEPSEEK_WEB = 'deepseek_web'


def llm_correct(text: str, api_key: str = '', base_url: str = '', model: str = '') -> str:
    """Use LLM to correct OCR artifacts and improve text quality."""
    import os
    import requests

    api_key = api_key or os.environ.get('LLM_API_KEY', '')
    base_url = base_url or os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    model = model or os.environ.get('LLM_MODEL', 'gpt-4o-mini')

    if not api_key:
        logger.warning('No LLM API key configured, skipping correction')
        return text

    try:
        prompt = (
            '以下是一段从图片中OCR提取的中文小说文本。'
            '请修正其中的OCR识别错误（如错别字、标点符号错误、断行不当等），'
            '保持原文内容不变，只修正明显的识别错误。'
            '直接返回修正后的文本，不要添加任何解释。\n\n'
            f'{text}'
        )

        resp = requests.post(
            f'{base_url}/chat/completions',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': model,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.1,
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return data['choices'][0]['message']['content'].strip()
    except Exception as e:
        logger.error(f'LLM correction failed: {e}')
        return text


def process_vip_chapter(
    image_url: str,
    mode: VipMode = VipMode.OCR,
    save_dir: Path | None = None,
    workers: int = OCR_WORKERS,
    llm_api_key: str = '',
    llm_base_url: str = '',
    llm_model: str = '',
    fetcher: Fetcher | None = None,
) -> tuple[str, list[Path]]:
    """Download VIP chapter GIF, process according to mode.

    Workflow: download GIF → convert to white-bg PNG → split into lines →
    remove pinyin (crop top) → multi-thread OCR → merge text → optional LLM correction.

    Args:
        image_url: URL of the VIP chapter GIF image.
        mode: Processing mode (OCR, RAW, LLM, KIMI, DEEPSEEK).
        save_dir: Directory to save frames. If None, uses tempdir.
        workers: Number of OCR threads.
        llm_api_key: LLM API key for LLM/KIMI/DEEPSEEK mode.
        llm_base_url: LLM base URL for LLM mode.
        llm_model: LLM model name for LLM mode.

    Returns:
        Tuple of (extracted_text, list_of_saved_frame_paths).
    """
    fetcher = fetcher or Fetcher()

    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(image_url)
    qs = parse_qs(parsed.query)
    expected_w = int(qs.get('w', [0])[0])

    gif_bytes = b''
    for attempt in range(1 + len(_VIP_RETRY_DELAYS)):
        if attempt > 0:
            delay = _VIP_RETRY_DELAYS[attempt - 1]
            logger.warning(f'VIP retry {attempt}/{len(_VIP_RETRY_DELAYS)} after {delay}s...')
            time.sleep(delay)

        _vip_rate_limit()
        logger.info(f'Downloading VIP image (attempt {attempt + 1}): {image_url}')
        resp = fetcher.get(image_url)
        gif_bytes = resp.content

        valid, info = _validate_gif(gif_bytes, expected_w)
        if valid:
            logger.info(f'VIP image OK: {info}')
            break
        logger.warning(f'VIP image invalid ({info}), retrying...')

    valid, info = _validate_gif(gif_bytes, expected_w)
    if not valid:
        raise ValueError(f'VIP图片获取失败: {info} ({image_url})')

    if save_dir:
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        gif_path = save_dir / 'chapter.gif'
        gif_path.write_bytes(gif_bytes)

    if mode == VipMode.RAW:
        from .ocr import gif_to_frames
        frames = gif_to_frames(gif_bytes)
        if save_dir is None:
            save_dir = Path(tempfile.mkdtemp(prefix='sfacg_vip_'))
        frame_paths = []
        for i, frame in enumerate(frames):
            frame_path = save_dir / f'frame_{i:03}.png'
            frame.save(frame_path)
            frame_paths.append(frame_path)
        logger.info(f'Saved {len(frame_paths)} frames to {save_dir}')
        return '', frame_paths

    # DeepSeek Web模式 (无需API Key)
    if mode == VipMode.DEEPSEEK_WEB:
        from .web_llm_vision import DeepSeekWebOCR
        logger.info('Running DeepSeek Web OCR (no API key needed)...')
        try:
            deepseek_web = DeepSeekWebOCR(headless=False)
            text = deepseek_web.ocr_gif(gif_bytes)
            
            if text:
                logger.info(f'DeepSeek Web extracted {len(text)} chars')
            else:
                logger.warning('DeepSeek Web: No text extracted')
            
            frame_paths = []
            if save_dir:
                frame_paths = list(save_dir.glob('frame_*.png'))
            return text, frame_paths
        except Exception as e:
            logger.error(f'DeepSeek Web failed: {e}')
            logger.info('Falling back to standard OCR...')
            from .ocr_fast import ocr_gif
            text = ocr_gif(gif_bytes, workers=workers)
            frame_paths = []
            if save_dir:
                frame_paths = list(save_dir.glob('frame_*.png'))
            return text, frame_paths

    # 标准OCR模式（使用优化版）
    from .ocr_fast import ocr_gif
    logger.info('Running OCR (fast)...')
    text = ocr_gif(gif_bytes, workers=workers)

    # LLM纠正模式
    if mode == VipMode.LLM and text:
        logger.info('Running LLM correction...')
        text = llm_correct(text, api_key=llm_api_key, base_url=llm_base_url, model=llm_model)

    if text:
        logger.info(f'Extracted {len(text)} chars')
    else:
        logger.warning('No text extracted from VIP image')

    frame_paths = []
    if save_dir:
        frame_paths = list(save_dir.glob('frame_*.png'))

    return text, frame_paths
