import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import numpy as np
from loguru import logger
from PIL import Image

from ..config import OCR_WORKERS

_ocr_instance = None
_ocr_lock = threading.Lock()
_gpu_available: bool | None = None


def _check_gpu_available() -> bool:
    global _gpu_available
    if _gpu_available is not None:
        return _gpu_available
    try:
        import onnxruntime as ort

        providers = ort.get_available_providers()
        _gpu_available = 'CUDAExecutionProvider' in providers
        if _gpu_available:
            logger.info('GPU available (CUDA provider found)')
        else:
            logger.info(f'GPU not available, providers: {providers}')
    except ImportError:
        _gpu_available = False
    return _gpu_available


def _get_providers() -> list[str]:
    if _check_gpu_available():
        return ['CUDAExecutionProvider', 'CPUExecutionProvider']
    return ['CPUExecutionProvider']


def _get_ocr(cpu_num_threads: int = 4):
    global _ocr_instance
    if _ocr_instance is not None:
        return _ocr_instance
    with _ocr_lock:
        if _ocr_instance is not None:
            return _ocr_instance
        try:
            from rapidocr_onnxruntime import RapidOCR

            use_gpu = _check_gpu_available()
            logger.info(f'Initializing OCR (GPU={use_gpu})')
            _ocr_instance = RapidOCR(
                cpu_num_threads=cpu_num_threads,
                rec_use_cuda=use_gpu,
                cls_use_cuda=use_gpu,
                det_use_cuda=use_gpu,
            )
        except ImportError:
            raise ImportError('OCR dependencies not installed. Run: uv sync --extra ocr')
    return _ocr_instance


def gif_to_frames(gif_bytes: bytes) -> list[Image.Image]:
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
    gray = np.array(image.convert('L'))
    row_has = (gray < 250).any(axis=1)
    col_has = (gray < 250).any(axis=0)
    rows = np.where(row_has)[0]
    cols = np.where(col_has)[0]
    if len(rows) == 0 or len(cols) == 0:
        return None
    return image.crop((cols[0], rows[0], cols[-1] + 1, rows[-1] + 1))


def find_line_gaps(gray_array: np.ndarray, min_gap: int = 5) -> list[tuple[int, int]]:
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


def gaps_to_lines_bounds(
    gaps: list[tuple[int, int]], height: int, min_gap: int = 5, min_height: int = 10
) -> list[tuple[int, int]]:
    lines_bounds = []
    prev = 0
    for gap_start, gap_end in gaps:
        if gap_start - prev >= min_height:
            lines_bounds.append((prev, gap_start))
        prev = gap_end
    if height - prev >= min_height:
        lines_bounds.append((prev, height))
    return lines_bounds


def _find_text_start_vectorized(line_gray: np.ndarray, min_stroke_run: int = 10) -> int:
    lh, lw = line_gray.shape
    for y in range(lh):
        row = line_gray[y, :]
        dark = row < 200
        d = np.diff(dark.astype(np.int8))
        starts = np.where(d == 1)[0] + 1
        ends = np.where(d == -1)[0] + 1
        if dark[0]:
            starts = np.concatenate([[0], starts])
        if dark[-1]:
            ends = np.concatenate([ends, [lw]])
        if len(starts) > 0 and len(ends) > 0:
            max_run = int(max(ends - starts))
        else:
            max_run = 0
        if max_run >= min_stroke_run:
            return y
    return 0


def _remove_pinyin_from_image(gray: np.ndarray, lines_bounds: list[tuple[int, int]]) -> np.ndarray:
    processed = gray.copy()
    for y_start, y_end in lines_bounds:
        line = gray[y_start:y_end, :]
        text_y = _find_text_start_vectorized(line)
        if text_y > 0:
            processed[y_start : y_start + text_y, :] = 255
    return processed


def _extract_line_images(gray: np.ndarray, lines_bounds: list[tuple[int, int]]) -> list[tuple[int, Image.Image]]:
    h, w = gray.shape
    result = []
    for i, (y_start, y_end) in enumerate(lines_bounds):
        line = gray[y_start:y_end, :]
        row_has = (line < 250).any(axis=1)
        col_has = (line < 250).any(axis=0)
        rows = np.where(row_has)[0]
        cols = np.where(col_has)[0]
        if len(rows) == 0 or len(cols) == 0:
            continue
        img = Image.fromarray(line).crop((cols[0], rows[0], cols[-1] + 1, rows[-1] + 1))
        result.append((i, img))
    return result


def _ocr_line_rec_only(args: tuple[int, Image.Image]) -> tuple[int, str]:
    line_id, img = args
    try:
        ocr = _get_ocr()
        result, _ = ocr(img, use_det=False, use_cls=False, use_rec=True)
        if not result:
            return line_id, ''
        parts = []
        for text, conf in result:
            text = text.strip()
            if text and re.search(r'[\u4e00-\u9fff]', text):
                parts.append(text)
        return line_id, ''.join(parts)
    except Exception as e:
        logger.debug(f'_ocr_line_rec_only: line {line_id} failed: {e}')
        return line_id, ''


def ocr_gif(gif_bytes: bytes, workers: int = OCR_WORKERS, cpu_num_threads: int = 4) -> str:
    start_time = time.perf_counter()
    logger.info(f'ocr_gif: {len(gif_bytes)} bytes')

    frames = gif_to_frames(gif_bytes)
    all_line_images: list[tuple[int, Image.Image]] = []
    frame_offsets: list[int] = []
    global_line_id = 0

    for frame_idx, frame in enumerate(frames):
        cropped = crop_whitespace(frame)
        if cropped is None:
            frame_offsets.append(global_line_id)
            continue

        gray = np.array(cropped.convert('L'))
        h, w = gray.shape

        gaps = find_line_gaps(gray, min_gap=5)
        lines_bounds = gaps_to_lines_bounds(gaps, h, min_gap=5, min_height=10)

        logger.info(f'ocr_gif: frame {frame_idx}, {w}x{h}, {len(lines_bounds)} lines')

        de_pinyin = _remove_pinyin_from_image(gray, lines_bounds)
        line_images = _extract_line_images(de_pinyin, lines_bounds)

        for lid, img in line_images:
            all_line_images.append((global_line_id + lid, img))

        frame_offsets.append(global_line_id)
        global_line_id += len(line_images)

    logger.info(f'ocr_gif: {len(all_line_images)} total lines, processing...')

    _get_ocr(cpu_num_threads=cpu_num_threads)

    all_results: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_ocr_line_rec_only, (lid, img)): lid for lid, img in all_line_images}
        for future in as_completed(futures):
            lid, text = future.result()
            if text:
                all_results[lid] = text

    merged = '\n'.join(all_results[i] for i in sorted(all_results))
    total_elapsed = time.perf_counter() - start_time
    logger.info(f'ocr_gif: done, {len(merged)} chars, {total_elapsed:.1f}s')
    return merged


def remove_pinyin(gif_bytes: bytes) -> list[Image.Image]:
    start_time = time.perf_counter()
    logger.info(f'remove_pinyin: {len(gif_bytes)} bytes')

    frames = gif_to_frames(gif_bytes)
    results = []

    for frame_idx, frame in enumerate(frames):
        cropped = crop_whitespace(frame)
        if cropped is None:
            continue

        gray = np.array(cropped.convert('L'))
        h, w = gray.shape

        gaps = find_line_gaps(gray, min_gap=5)
        lines_bounds = gaps_to_lines_bounds(gaps, h, min_gap=5, min_height=10)

        de_pinyin = _remove_pinyin_from_image(gray, lines_bounds)
        result_img = Image.fromarray(de_pinyin)
        results.append(result_img)
        logger.info(f'remove_pinyin: frame {frame_idx}, {w}x{h}, {len(lines_bounds)} lines')

    total_elapsed = time.perf_counter() - start_time
    logger.info(f'remove_pinyin: done, {len(results)} frames, {total_elapsed:.1f}s')
    return results


def remove_pinyin_gif(gif_bytes: bytes) -> Image.Image:
    frames = remove_pinyin(gif_bytes)
    if not frames:
        raise ValueError('No frames in GIF')
    if len(frames) == 1:
        return frames[0]

    total_h = sum(f.height for f in frames)
    max_w = max(f.width for f in frames)
    combined = Image.new('RGB', (max_w, total_h), (255, 255, 255))
    y = 0
    for f in frames:
        combined.paste(f, (0, y))
        y += f.height
    return combined


def remove_pinyin_to_bytes(gif_bytes: bytes, fmt: str = 'PNG') -> bytes:
    img = remove_pinyin_gif(gif_bytes)
    buf = BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def ocr_image(image_source: str | Path, workers: int = OCR_WORKERS, cpu_num_threads: int = 4) -> str:
    if isinstance(image_source, Path) or not str(image_source).startswith('http'):
        img_bytes = Path(image_source).read_bytes()
    else:
        from ..fetcher import Fetcher

        img_bytes = Fetcher().get_binary(str(image_source))

    suffix = Path(str(image_source)).suffix.lower()
    if suffix == '.gif':
        return ocr_gif(img_bytes, workers, cpu_num_threads)

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

    gray = np.array(cropped.convert('L'))
    gaps = find_line_gaps(gray, min_gap=5)
    lines_bounds = gaps_to_lines_bounds(gaps, gray.shape[0], min_gap=5, min_height=10)

    de_pinyin = _remove_pinyin_from_image(gray, lines_bounds)
    line_images = _extract_line_images(de_pinyin, lines_bounds)

    _get_ocr(cpu_num_threads=cpu_num_threads)
    if line_images:
        _ocr_line_rec_only((0, line_images[0][1]))

    results: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_ocr_line_rec_only, (lid, img)): lid for lid, img in line_images}
        for future in as_completed(futures):
            lid, text = future.result()
            if text:
                results[lid] = text

    return '\n'.join(results[i] for i in sorted(results))


def ocr_bytes(image_bytes: bytes, workers: int = OCR_WORKERS, cpu_num_threads: int = 4) -> str:
    from io import BytesIO

    from PIL import Image

    img = Image.open(BytesIO(image_bytes))
    if img.format == 'GIF':
        return ocr_gif(image_bytes, workers, cpu_num_threads)
    else:
        return ocr_image(img, workers, cpu_num_threads)
