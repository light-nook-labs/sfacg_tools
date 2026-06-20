import re
import numpy as np
from pathlib import Path
from io import BytesIO
from PIL import Image
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import OCR_WORKERS

_ocr_instance = None


def _get_ocr():
    global _ocr_instance
    if _ocr_instance is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_instance = RapidOCR()
        except ImportError:
            raise ImportError(
                "OCR dependencies not installed. Run: uv sync --extra ocr"
            )
    return _ocr_instance


def gif_to_frames(gif_bytes: bytes) -> list[Image.Image]:
    """GIF → RGBA → 白色背景RGB帧列表."""
    frames = []
    with Image.open(BytesIO(gif_bytes)) as img:
        try:
            while True:
                rgba = img.convert('RGBA')
                bg = Image.new('RGB', rgba.size, (255, 255, 255))
                bg.paste(rgba, mask=rgba.split()[3])
                frames.append(bg)
                img.seek(img.tell() + 1)
        except EOFError:
            pass
    if not frames:
        with Image.open(BytesIO(gif_bytes)) as fallback:
            rgba = fallback.convert('RGBA')
            bg = Image.new('RGB', rgba.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.split()[3])
            frames.append(bg)
    return frames


def crop_whitespace(image: Image.Image) -> Image.Image | None:
    """裁剪上下左右空白区域."""
    gray = np.array(image.convert('L'))
    row_has = (gray < 250).any(axis=1)
    col_has = (gray < 250).any(axis=0)
    rows = np.where(row_has)[0]
    cols = np.where(col_has)[0]
    if len(rows) == 0 or len(cols) == 0:
        return None
    return image.crop((cols[0], rows[0], cols[-1] + 1, rows[-1] + 1))


def find_line_gaps(gray_array: np.ndarray, min_gap: int = 5) -> list[tuple[int, int]]:
    """找行间隙（连续空白行 >= min_gap）."""
    row_black = (gray_array < 250).sum(axis=1)

    gaps = []
    in_gap = False
    gap_start = 0
    for i in range(len(row_black)):
        if row_black[i] == 0 and not in_gap:
            in_gap = True
            gap_start = i
        elif row_black[i] > 0 and in_gap:
            in_gap = False
            if i - gap_start >= min_gap:
                gaps.append((gap_start, i))
    if in_gap and len(row_black) - gap_start >= min_gap:
        gaps.append((gap_start, len(row_black)))
    return gaps


def split_lines(image: Image.Image, min_gap: int = 5, min_height: int = 10) -> list[Image.Image]:
    """按行间隙切分图片."""
    gray = np.array(image.convert('L'))
    gaps = find_line_gaps(gray, min_gap)

    lines = []
    prev = 0
    for gap_start, gap_end in gaps:
        if gap_start - prev >= min_height:
            lines.append(image.crop((0, prev, image.width, gap_start)))
        prev = gap_end
    if image.height - prev >= min_height:
        lines.append(image.crop((0, prev, image.width, image.height)))
    return lines


def remove_pinyin(image: Image.Image, pinyin_ratio: float = 0.2) -> Image.Image:
    """裁剪顶部拼音区域."""
    h = image.height
    crop_top = int(h * pinyin_ratio)
    return image.crop((0, crop_top, image.width, h))


def _ocr_line(args: tuple[int, np.ndarray]) -> tuple[int, str]:
    """OCR单行，返回 (行ID, 文本)."""
    line_id, arr = args
    try:
        ocr = _get_ocr()
        result, _ = ocr(arr)
        if not result:
            return line_id, ''

        sorted_result = sorted(result, key=lambda r: min(p[1] for p in r[0]))

        parts = []
        for r in sorted_result:
            text = r[1].strip()
            if text and re.search(r'[\u4e00-\u9fff]', text):
                parts.append(text)
        return line_id, ''.join(parts)
    except Exception as e:
        logger.debug(f'Line {line_id} OCR failed: {e}')
        return line_id, ''


def _prepare_lines(gif_bytes: bytes) -> list[tuple[int, np.ndarray]]:
    """GIF → 帧 → 裁剪 → 切行 → 去拼音 → 返回(id, numpy数组)."""
    frames = gif_to_frames(gif_bytes)
    logger.info(f'GIF has {len(frames)} frame(s)')

    all_lines: list[tuple[int, np.ndarray]] = []
    line_id = 0

    for frame in frames:
        cropped = crop_whitespace(frame)
        if cropped is None:
            continue

        lines = split_lines(cropped)
        for line in lines:
            no_pinyin = remove_pinyin(line)
            c = crop_whitespace(no_pinyin)
            if c is not None:
                all_lines.append((line_id, np.array(c)))
                line_id += 1

    logger.info(f'Split into {len(all_lines)} lines')
    return all_lines


def ocr_gif(gif_bytes: bytes, workers: int = OCR_WORKERS) -> str:
    """完整OCR流程."""
    all_lines = _prepare_lines(gif_bytes)

    results: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_ocr_line, (lid, arr)): lid
            for lid, arr in all_lines
        }
        for future in as_completed(futures):
            lid, text = future.result()
            if text:
                results[lid] = text

    merged = '\n'.join(results[i] for i in sorted(results))
    logger.info(f'OCR done: {len(merged)} chars from {len(results)} lines')
    return merged


def ocr_image(image_source: str | Path, workers: int = OCR_WORKERS) -> str:
    """OCR图片（URL或本地路径）."""
    if isinstance(image_source, Path) or not str(image_source).startswith('http'):
        img_bytes = Path(image_source).read_bytes()
    else:
        from .fetcher import Fetcher
        img_bytes = Fetcher().get_binary(str(image_source))

    suffix = Path(str(image_source)).suffix.lower()
    if suffix == '.gif':
        return ocr_gif(img_bytes, workers)

    img = Image.open(BytesIO(img_bytes))
    if img.mode == 'P' and 'transparency' in img.info:
        rgba = img.convert('RGBA')
        bg = Image.new('RGB', rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[3])
        img.close()
        img = bg

    cropped = crop_whitespace(img)
    img.close()
    if cropped is None:
        return ''

    lines = split_lines(cropped)
    all_lines = [(i, np.array(crop_whitespace(remove_pinyin(line)) or line)) for i, line in enumerate(lines)]

    results: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_ocr_line, (lid, arr)): lid
            for lid, arr in all_lines
        }
        for future in as_completed(futures):
            lid, text = future.result()
            if text:
                results[lid] = text

    return '\n'.join(results[i] for i in sorted(results))


def ocr_bytes(image_bytes: bytes, workers: int = OCR_WORKERS) -> str:
    """从字节数据OCR."""
    return ocr_gif(image_bytes, workers)
