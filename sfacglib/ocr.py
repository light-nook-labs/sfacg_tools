import re
import time
import threading
import numpy as np
from pathlib import Path
from io import BytesIO
from PIL import Image
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import OCR_WORKERS

_ocr_instance = None
_ocr_lock = threading.Lock()


def _get_ocr(cpu_num_threads: int = 4):
    """获取RapidOCR单例实例，线程安全"""
    global _ocr_instance
    if _ocr_instance is None:
        with _ocr_lock:
            if _ocr_instance is None:
                try:
                    from rapidocr_onnxruntime import RapidOCR
                    _ocr_instance = RapidOCR(cpu_num_threads=cpu_num_threads)
                    logger.debug(f'_get_ocr: 初始化RapidOCR，线程数={cpu_num_threads}')
                except ImportError:
                    raise ImportError(
                        "OCR dependencies not installed. Run: uv sync --extra ocr"
                    )
    return _ocr_instance


def gif_to_frames(gif_bytes: bytes) -> list[Image.Image]:
    """GIF → RGBA → 白色背景RGB帧列表."""
    start_time = time.perf_counter()
    logger.debug(f'gif_to_frames: 输入大小 {len(gif_bytes)} bytes')
    
    frames = []
    with Image.open(BytesIO(gif_bytes)) as img:
        logger.debug(f'gif_to_frames: 图像模式 {img.mode}, 尺寸 {img.size}')
        try:
            frame_count = 0
            while True:
                frame_start = time.perf_counter()
                rgba = img.convert('RGBA')
                bg = Image.new('RGB', rgba.size, (255, 255, 255))
                bg.paste(rgba, mask=rgba.split()[3])
                frames.append(bg)
                frame_count += 1
                frame_elapsed = time.perf_counter() - frame_start
                logger.debug(f'gif_to_frames: 帧 {frame_count} 处理完成, 耗时 {frame_elapsed:.3f}s, 尺寸 {bg.size}')
                img.seek(img.tell() + 1)
        except EOFError:
            pass
    
    if not frames:
        logger.debug('gif_to_frames: 无帧，使用fallback')
        with Image.open(BytesIO(gif_bytes)) as fallback:
            rgba = fallback.convert('RGBA')
            bg = Image.new('RGB', rgba.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.split()[3])
            frames.append(bg)
    
    total_elapsed = time.perf_counter() - start_time
    logger.debug(f'gif_to_frames: 完成，共 {len(frames)} 帧，总耗时 {total_elapsed:.3f}s')
    return frames


def crop_whitespace(image: Image.Image) -> Image.Image | None:
    """裁剪上下左右空白区域."""
    start_time = time.perf_counter()
    logger.debug(f'crop_whitespace: 输入尺寸 {image.size}')
    
    gray = np.array(image.convert('L'))
    row_has = (gray < 250).any(axis=1)
    col_has = (gray < 250).any(axis=0)
    rows = np.where(row_has)[0]
    cols = np.where(col_has)[0]
    
    if len(rows) == 0 or len(cols) == 0:
        elapsed = time.perf_counter() - start_time
        logger.debug(f'crop_whitespace: 无内容区域，耗时 {elapsed:.3f}s')
        return None
    
    result = image.crop((cols[0], rows[0], cols[-1] + 1, rows[-1] + 1))
    elapsed = time.perf_counter() - start_time
    logger.debug(f'crop_whitespace: 裁剪 {image.size} -> {result.size}, 耗时 {elapsed:.3f}s')
    return result


def find_line_gaps(gray_array: np.ndarray, min_gap: int = 5) -> list[tuple[int, int]]:
    """找行间隙（连续空白行 >= min_gap）."""
    start_time = time.perf_counter()
    logger.debug(f'find_line_gaps: 输入数组形状 {gray_array.shape}, min_gap={min_gap}')
    
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
    
    elapsed = time.perf_counter() - start_time
    logger.debug(f'find_line_gaps: 找到 {len(gaps)} 个间隙，耗时 {elapsed:.3f}s')
    return gaps


def split_lines(image: Image.Image, min_gap: int = 5, min_height: int = 10) -> list[Image.Image]:
    """按行间隙切分图片."""
    start_time = time.perf_counter()
    logger.debug(f'split_lines: 输入尺寸 {image.size}, min_gap={min_gap}, min_height={min_height}')
    
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
    
    elapsed = time.perf_counter() - start_time
    logger.debug(f'split_lines: 切分出 {len(lines)} 行，耗时 {elapsed:.3f}s')
    return lines


def remove_pinyin(image: Image.Image, pinyin_ratio: float = 0.2) -> Image.Image:
    """裁剪顶部拼音区域."""
    start_time = time.perf_counter()
    logger.debug(f'remove_pinyin: 输入尺寸 {image.size}, pinyin_ratio={pinyin_ratio}')
    
    h = image.height
    crop_top = int(h * pinyin_ratio)
    result = image.crop((0, crop_top, image.width, h))
    
    elapsed = time.perf_counter() - start_time
    logger.debug(f'remove_pinyin: 裁剪 {image.size} -> {result.size}, 耗时 {elapsed:.3f}s')
    return result


def _ocr_line(args: tuple[int, np.ndarray], cpu_num_threads: int = 4) -> tuple[int, str]:
    """OCR单行，返回 (行ID, 文本)."""
    line_id, arr = args
    start_time = time.perf_counter()
    logger.debug(f'_ocr_line: 行 {line_id} 开始，数组形状 {arr.shape}')
    
    try:
        ocr = _get_ocr(cpu_num_threads=cpu_num_threads)
        result, _ = ocr(arr)
        
        if not result:
            elapsed = time.perf_counter() - start_time
            logger.debug(f'_ocr_line: 行 {line_id} 无结果，耗时 {elapsed:.3f}s')
            return line_id, ''

        sorted_result = sorted(result, key=lambda r: min(p[1] for p in r[0]))

        parts = []
        for r in sorted_result:
            text = r[1].strip()
            if text and re.search(r'[\u4e00-\u9fff]', text):
                parts.append(text)
        
        elapsed = time.perf_counter() - start_time
        logger.debug(f'_ocr_line: 行 {line_id} 识别 {len(parts)} 部分，耗时 {elapsed:.3f}s')
        return line_id, ''.join(parts)
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        logger.debug(f'_ocr_line: 行 {line_id} OCR失败: {e}，耗时 {elapsed:.3f}s')
        return line_id, ''


def _prepare_lines(gif_bytes: bytes) -> list[tuple[int, np.ndarray]]:
    """GIF → 帧 → 裁剪 → 切行 → 去拼音 → 返回(id, numpy数组)."""
    start_time = time.perf_counter()
    logger.info(f'_prepare_lines: 开始处理 {len(gif_bytes)} bytes')
    
    frames = gif_to_frames(gif_bytes)
    logger.info(f'_prepare_lines: GIF有 {len(frames)} 帧')

    all_lines: list[tuple[int, np.ndarray]] = []
    line_id = 0

    for frame_idx, frame in enumerate(frames):
        frame_start = time.perf_counter()
        logger.debug(f'_prepare_lines: 处理帧 {frame_idx + 1}/{len(frames)}, 尺寸 {frame.size}')
        
        cropped = crop_whitespace(frame)
        if cropped is None:
            logger.debug(f'_prepare_lines: 帧 {frame_idx + 1} 无内容，跳过')
            continue

        lines = split_lines(cropped)
        logger.debug(f'_prepare_lines: 帧 {frame_idx + 1} 切分出 {len(lines)} 行')
        
        for line_idx, line in enumerate(lines):
            line_start = time.perf_counter()
            no_pinyin = remove_pinyin(line)
            c = crop_whitespace(no_pinyin)
            if c is not None:
                all_lines.append((line_id, np.array(c)))
                line_id += 1
                line_elapsed = time.perf_counter() - line_start
                logger.debug(f'_prepare_lines: 帧 {frame_idx + 1} 行 {line_idx + 1} 准备完成，耗时 {line_elapsed:.3f}s')
        
        frame_elapsed = time.perf_counter() - frame_start
        logger.debug(f'_prepare_lines: 帧 {frame_idx + 1} 处理完成，耗时 {frame_elapsed:.3f}s')

    total_elapsed = time.perf_counter() - start_time
    logger.info(f'_prepare_lines: 完成，共 {len(all_lines)} 行，总耗时 {total_elapsed:.3f}s')
    return all_lines


def ocr_gif(gif_bytes: bytes, workers: int = OCR_WORKERS, cpu_num_threads: int = 4) -> str:
    """完整OCR流程."""
    start_time = time.perf_counter()
    logger.info(f'ocr_gif: 开始处理 {len(gif_bytes)} bytes, workers={workers}, cpu_num_threads={cpu_num_threads}')
    
    all_lines = _prepare_lines(gif_bytes)
    prepare_elapsed = time.perf_counter() - start_time
    logger.info(f'ocr_gif: _prepare_lines 耗时 {prepare_elapsed:.3f}s')

    results: dict[int, str] = {}
    ocr_start = time.perf_counter()
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        logger.debug(f'ocr_gif: 提交 {len(all_lines)} 个OCR任务')
        futures = {
            executor.submit(_ocr_line, (lid, arr), cpu_num_threads): lid
            for lid, arr in all_lines
        }
        
        completed_count = 0
        for future in as_completed(futures):
            lid, text = future.result()
            completed_count += 1
            if text:
                results[lid] = text
                logger.info(f'ocr_gif: [{completed_count}/{len(futures)}] line {lid} = "{text}"')
            else:
                logger.debug(f'ocr_gif: [{completed_count}/{len(futures)}] line {lid} = (empty)')

    ocr_elapsed = time.perf_counter() - ocr_start
    logger.info(f'ocr_gif: OCR识别耗时 {ocr_elapsed:.3f}s')

    merged = '\n'.join(results[i] for i in sorted(results))
    total_elapsed = time.perf_counter() - start_time
    logger.info(f'ocr_gif: 完成，{len(merged)} 字符，{len(results)} 行，总耗时 {total_elapsed:.3f}s')
    return merged


def ocr_image(image_source: str | Path, workers: int = OCR_WORKERS, cpu_num_threads: int = 4) -> str:
    """OCR图片（URL或本地路径）."""
    start_time = time.perf_counter()
    logger.info(f'ocr_image: 开始处理 {image_source}')
    
    if isinstance(image_source, Path) or not str(image_source).startswith('http'):
        img_bytes = Path(image_source).read_bytes()
        logger.debug(f'ocr_image: 读取本地文件 {len(img_bytes)} bytes')
    else:
        from .fetcher import Fetcher
        img_bytes = Fetcher().get_binary(str(image_source))
        logger.debug(f'ocr_image: 下载图片 {len(img_bytes)} bytes')

    suffix = Path(str(image_source)).suffix.lower()
    if suffix == '.gif':
        logger.debug(f'ocr_image: 检测到GIF格式，调用ocr_gif')
        return ocr_gif(img_bytes, workers, cpu_num_threads)

    logger.debug(f'ocr_image: 处理非GIF图像')
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
        logger.debug(f'ocr_image: 无内容区域')
        return ''

    lines = split_lines(cropped)
    logger.debug(f'ocr_image: 切分出 {len(lines)} 行')
    
    all_lines = [(i, np.array(crop_whitespace(remove_pinyin(line)) or line)) for i, line in enumerate(lines)]

    results: dict[int, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_ocr_line, (lid, arr), cpu_num_threads): lid
            for lid, arr in all_lines
        }
        for future in as_completed(futures):
            lid, text = future.result()
            if text:
                results[lid] = text

    total_elapsed = time.perf_counter() - start_time
    result_text = '\n'.join(results[i] for i in sorted(results))
    logger.info(f'ocr_image: 完成，{len(result_text)} 字符，总耗时 {total_elapsed:.3f}s')
    return result_text


def ocr_bytes(image_bytes: bytes, workers: int = OCR_WORKERS, cpu_num_threads: int = 4) -> str:
    """从字节数据OCR."""
    logger.debug(f'ocr_bytes: 调用ocr_gif，输入 {len(image_bytes)} bytes')
    return ocr_gif(image_bytes, workers, cpu_num_threads)


def prepare_lines_as_images(gif_bytes: bytes) -> list[Image.Image]:
    """GIF → 帧 → 裁剪 → 切行 → 去拼音 → 返回PIL Image列表.
    
    用于后续调用LLM Vision API进行OCR。
    """
    start_time = time.perf_counter()
    logger.info(f'prepare_lines_as_images: 开始处理 {len(gif_bytes)} bytes')
    
    frames = gif_to_frames(gif_bytes)
    logger.info(f'prepare_lines_as_images: GIF有 {len(frames)} 帧')

    all_lines: list[Image.Image] = []

    for frame_idx, frame in enumerate(frames):
        frame_start = time.perf_counter()
        logger.debug(f'prepare_lines_as_images: 处理帧 {frame_idx + 1}/{len(frames)}, 尺寸 {frame.size}')
        
        cropped = crop_whitespace(frame)
        if cropped is None:
            logger.debug(f'prepare_lines_as_images: 帧 {frame_idx + 1} 无内容，跳过')
            continue

        lines = split_lines(cropped)
        logger.debug(f'prepare_lines_as_images: 帧 {frame_idx + 1} 切分出 {len(lines)} 行')
        
        for line_idx, line in enumerate(lines):
            line_start = time.perf_counter()
            no_pinyin = remove_pinyin(line)
            c = crop_whitespace(no_pinyin)
            if c is not None:
                all_lines.append(c)
                line_elapsed = time.perf_counter() - line_start
                logger.debug(f'prepare_lines_as_images: 帧 {frame_idx + 1} 行 {line_idx + 1} 准备完成，尺寸 {c.size}，耗时 {line_elapsed:.3f}s')
        
        frame_elapsed = time.perf_counter() - frame_start
        logger.debug(f'prepare_lines_as_images: 帧 {frame_idx + 1} 处理完成，耗时 {frame_elapsed:.3f}s')

    total_elapsed = time.perf_counter() - start_time
    logger.info(f'prepare_lines_as_images: 完成，共 {len(all_lines)} 行，总耗时 {total_elapsed:.3f}s')
    return all_lines


def image_to_bytes(image: Image.Image, format: str = 'PNG') -> bytes:
    """将PIL Image转换为bytes"""
    buffer = BytesIO()
    image.save(buffer, format=format)
    return buffer.getvalue()


def ocr_gif_with_llm(
    gif_bytes: bytes,
    provider: str = 'kimi',
    api_key: str = '',
    base_url: str = '',
    vision_model: str = '',
    text_model: str = '',
    batch_size: int = 10,
    use_web: bool = False,
    headless: bool = False,
) -> str:
    """使用LLM Vision API进行OCR识别.
    
    流程: GIF切分 → 转换为图片bytes → 批量发送给LLM → 合并结果
    
    Args:
        gif_bytes: GIF图片字节数据
        provider: LLM提供商 (kimi, deepseek, openai)
        api_key: API密钥 (use_web=True时可为空)
        base_url: 自定义API地址
        vision_model: 自定义Vision模型名
        text_model: 自定义Text模型名
        batch_size: 每批处理的图片数量
        use_web: 是否使用Web方式 (无需API Key)
        headless: Web方式是否无头模式
        
    Returns:
        OCR识别结果文本
    """
    start_time = time.perf_counter()
    logger.info(f'ocr_gif_with_llm: 开始处理 {len(gif_bytes)} bytes, provider={provider}, use_web={use_web}')
    
    # 1. 切分图片
    lines = prepare_lines_as_images(gif_bytes)
    if not lines:
        logger.warning('ocr_gif_with_llm: 无有效行')
        return ''
    
    logger.info(f'ocr_gif_with_llm: 切分出 {len(lines)} 行，开始LLM OCR')
    
    # 2. 创建LLM客户端
    if use_web:
        from .web_llm_vision import create_web_llm_vision
        llm_client = create_web_llm_vision(provider=provider, headless=headless)
    else:
        from .llm_vision import create_llm_vision
        llm_client = create_llm_vision(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            vision_model=vision_model,
            text_model=text_model,
        )
    
    # 3. 批量处理
    all_results: list[str] = []
    total_batches = (len(lines) + batch_size - 1) // batch_size
    
    for batch_idx in range(0, len(lines), batch_size):
        batch_start = time.perf_counter()
        batch = lines[batch_idx:batch_idx + batch_size]
        batch_num = batch_idx // batch_size + 1
        
        logger.info(f'ocr_gif_with_llm: 处理批次 {batch_num}/{total_batches}, {len(batch)} 张图片')
        
        try:
            if use_web:
                # Web方式: 逐张处理
                for i, img in enumerate(batch):
                    logger.debug(f'ocr_gif_with_llm: Web处理图片 {i+1}/{len(batch)}')
                    result = llm_client.ocr_image(img)
                    all_results.append(result)
            else:
                # API方式: 批量处理
                results = llm_client.ocr_images(batch)
                all_results.extend(results)
            
            batch_elapsed = time.perf_counter() - batch_start
            logger.info(f'ocr_gif_with_llm: 批次 {batch_num} 完成，耗时 {batch_elapsed:.3f}s')
            
        except Exception as e:
            logger.error(f'ocr_gif_with_llm: 批次 {batch_num} 失败: {e}')
            # 添加空结果
            all_results.extend([''] * len(batch))
    
    # 4. 合并结果
    merged = '\n'.join(result for result in all_results if result)
    
    total_elapsed = time.perf_counter() - start_time
    logger.info(f'ocr_gif_with_llm: 完成，{len(merged)} 字符，总耗时 {total_elapsed:.3f}s')
    return merged


def ocr_image_with_llm(
    image_source: str | Path,
    provider: str = 'kimi',
    api_key: str = '',
    base_url: str = '',
    vision_model: str = '',
    text_model: str = '',
    batch_size: int = 10,
    use_web: bool = False,
    headless: bool = False,
) -> str:
    """使用LLM Vision API识别图片.
    
    Args:
        image_source: 图片路径或URL
        provider: LLM提供商 (kimi, deepseek, openai)
        api_key: API密钥 (use_web=True时可为空)
        base_url: 自定义API地址
        vision_model: 自定义Vision模型名
        text_model: 自定义Text模型名
        batch_size: 每批处理的图片数量
        use_web: 是否使用Web方式 (无需API Key)
        headless: Web方式是否无头模式
        
    Returns:
        OCR识别结果文本
    """
    start_time = time.perf_counter()
    logger.info(f'ocr_image_with_llm: 开始处理 {image_source}')
    
    # 读取图片
    if isinstance(image_source, Path) or not str(image_source).startswith('http'):
        img_bytes = Path(image_source).read_bytes()
        logger.debug(f'ocr_image_with_llm: 读取本地文件 {len(img_bytes)} bytes')
    else:
        from .fetcher import Fetcher
        img_bytes = Fetcher().get_binary(str(image_source))
        logger.debug(f'ocr_image_with_llm: 下载图片 {len(img_bytes)} bytes')
    
    suffix = Path(str(image_source)).suffix.lower()
    if suffix == '.gif':
        logger.debug(f'ocr_image_with_llm: 检测到GIF格式')
        return ocr_gif_with_llm(
            img_bytes,
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            vision_model=vision_model,
            text_model=text_model,
            batch_size=batch_size,
            use_web=use_web,
            headless=headless,
        )
    
    # 非GIF图片，直接调用LLM
    logger.debug(f'ocr_image_with_llm: 非GIF图片，直接调用LLM')
    
    if use_web:
        from .web_llm_vision import create_web_llm_vision
        llm_client = create_web_llm_vision(provider=provider, headless=headless)
    else:
        from .llm_vision import create_llm_vision
        llm_client = create_llm_vision(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            vision_model=vision_model,
            text_model=text_model,
        )
    
    result = llm_client.ocr_image(img_bytes)
    
    total_elapsed = time.perf_counter() - start_time
    logger.info(f'ocr_image_with_llm: 完成，{len(result)} 字符，总耗时 {total_elapsed:.3f}s')
    return result
