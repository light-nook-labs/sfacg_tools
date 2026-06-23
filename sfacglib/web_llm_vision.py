import time
import asyncio
import tempfile
import random
from pathlib import Path
from loguru import logger
from PIL import Image

_CASUAL_MESSAGES = [
    '你好',
    '今天天气怎么样',
    '你能帮我解释一下什么是量子力学吗',
    '推荐几本好看的书',
    '你觉得人工智能的未来如何',
    '帮我写一首关于春天的诗',
    '什么是深度学习',
    '如何学好编程',
    '地球上最高的山是什么',
    '中国的四大发明是什么',
    '你能做什么',
    '帮我翻译一下hello world',
    '什么是机器学习',
    '宇宙有多大',
    '人类是怎么起源的',
]

PROMPT = (
    '识别图片中的中文正文，忽略拼音注音和水印"SF轻小说"。'
    '规则：汉字之间禁止加空格，标点紧贴汉字，同一段落内禁止换行。'
    '无正文回复NULL。'
)


def split_by_height(image: Image.Image, max_height: int = 1500) -> list[Image.Image]:
    if image.height <= max_height:
        return [image]
    segments = []
    for y in range(0, image.height, max_height):
        segments.append(image.crop((0, y, image.width, min(y + max_height, image.height))))
    return segments


def resize_to_max(image: Image.Image, max_dim: int = 1000) -> Image.Image:
    w, h = image.size
    if w <= max_dim and h <= max_dim:
        return image
    ratio = min(max_dim / w, max_dim / h)
    return image.resize((int(w * ratio), int(h * ratio)), Image.Resampling.LANCZOS)


def deduplicate_texts(texts: list[str]) -> str:
    if not texts:
        return ''
    result = texts[0]
    for i in range(1, len(texts)):
        current = texts[i]
        overlap = 0
        for j in range(1, min(len(result), len(current))):
            if result.endswith(current[:j]):
                overlap = j
        if overlap > 10:
            result += current[overlap:]
        else:
            result += '\n\n' + current
    return result


def _is_valid_response(text: str) -> bool:
    t = text.strip()
    if not t:
        return False
    if t.lower() == 'null':
        return False
    return True


def _fix_inline_spaces(text: str) -> str:
    import re
    lines = text.split('\n')
    result = []
    for line in lines:
        cleaned = re.sub(r'(?<=[\u4e00-\u9fff，。！？、；：""''（）【】《》…—])\s+(?=[\u4e00-\u9fff，。！？、；：""''（）【】《》…—])', '', line)
        result.append(cleaned)
    return '\n'.join(result)


class DeepSeekWebOCR:

    def __init__(self, headless: bool = False, timeout: int = 60000):
        self.headless = headless
        self.timeout = timeout
        self.playwright = None
        self.context = None
        self.page = None

    async def _init_browser(self):
        from playwright.async_api import async_playwright
        self.playwright = await async_playwright().start()
        user_data_dir = Path.home() / '.sfacg' / 'browser_data'
        user_data_dir.mkdir(parents=True, exist_ok=True)
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=self.headless,
            accept_downloads=False,
        )
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = await self.context.new_page()

    async def _close_browser(self):
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()

    async def _navigate_to_deepseek(self):
        await self.page.goto('https://chat.deepseek.com/', wait_until='networkidle', timeout=self.timeout)
        await asyncio.sleep(1)
        try:
            vision_radio = await self.page.query_selector('input[value="vision"], label:has-text("Vision")')
            if vision_radio:
                await vision_radio.click()
                await asyncio.sleep(1)
            else:
                await self.page.evaluate('''() => {
                    const elements = document.querySelectorAll('*');
                    for (const el of elements) {
                        if (el.textContent === 'Vision' && el.tagName !== 'SCRIPT') {
                            el.click();
                            return true;
                        }
                    }
                    const radios = document.querySelectorAll('input[type="radio"]');
                    for (const radio of radios) {
                        if (radio.value === 'vision' || radio.nextSibling?.textContent?.includes('Vision')) {
                            radio.click();
                            return true;
                        }
                    }
                    return false;
                }''')
                await asyncio.sleep(1)
        except Exception as e:
            logger.debug(f'DeepSeekWebOCR: Vision mode selection failed: {e}')

    async def _send_casual_message(self):
        msg = random.choice(_CASUAL_MESSAGES)
        word_count = random.choice([30, 40, 50, 60, 70, 80])
        full_msg = f'{msg}，请用{word_count}字以内回答。'
        try:
            await self.page.evaluate('''(text) => {
                const textarea = document.querySelector('textarea');
                if (textarea) {
                    const setter = Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype, 'value'
                    ).set;
                    setter.call(textarea, text);
                    textarea.dispatchEvent(new Event('input', { bubbles: true }));
                    textarea.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
                return false;
            }''', full_msg)
            await asyncio.sleep(0.3)
            await self.page.focus('textarea')
            await asyncio.sleep(0.1)
            await self.page.keyboard.press('Enter')
            logger.debug(f'DeepSeekWebOCR: Sent casual message: {msg}')
            await asyncio.sleep(random.uniform(5, 10))
        except Exception as e:
            logger.debug(f'DeepSeekWebOCR: Casual message failed: {e}')

    async def _upload_image(self, image_path: Path):
        upload_input = await self.page.query_selector('input[type="file"]')
        if upload_input:
            logger.debug(f'DeepSeekWebOCR: Uploading image...')
            await upload_input.set_input_files(str(image_path))
            await asyncio.sleep(5)
            logger.debug(f'DeepSeekWebOCR: Image uploaded')
        else:
            logger.error('DeepSeekWebOCR: No file input found!')

    async def _set_prompt_and_send(self, prompt: str):
        textarea = await self.page.query_selector('textarea')
        if textarea:
            await textarea.click()
            await asyncio.sleep(0.2)
        await self.page.evaluate('''(text) => {
            const textarea = document.querySelector('textarea');
            if (textarea) {
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLTextAreaElement.prototype, 'value'
                ).set;
                setter.call(textarea, text);
                textarea.dispatchEvent(new Event('input', { bubbles: true }));
                textarea.dispatchEvent(new Event('change', { bubbles: true }));
                return true;
            }
            return false;
        }''', prompt)
        await asyncio.sleep(0.3)
        await self.page.focus('textarea')
        await asyncio.sleep(0.1)
        logger.debug('DeepSeekWebOCR: Sending prompt...')
        await self.page.keyboard.press('Enter')

    async def _get_page_text(self) -> str:
        return await self.page.evaluate('''() => {
            const allElements = document.querySelectorAll('*');
            const responseTexts = [];
            let foundUserMsg = false;
            for (const el of allElements) {
                if (el.children.length === 0 ||
                    (el.childNodes.length === 1 && el.childNodes[0].nodeType === 3)) {
                    const text = el.innerText || el.textContent || '';
                    if (text.trim()) {
                        if (!foundUserMsg && (
                            text.includes('识别图片中的中文正文') ||
                            text.includes('以下是OCR识别') ||
                            text.includes('请识别') ||
                            text.includes('直接返回修正后的完整文本') ||
                            text.includes('OCR原文：') ||
                            text.includes('这是一张中文网络小说'))) {
                            foundUserMsg = true;
                            continue;
                        }
                        if (foundUserMsg &&
                            !text.includes('DeepThink') &&
                            !text.includes('Search') &&
                            !text.includes('AI-generated') &&
                            !text.includes('Message DeepSeek') &&
                            !text.includes('以下是OCR识别') &&
                            !text.includes('修正错别字')) {
                            responseTexts.push(text.trim());
                        }
                    }
                }
            }
            return responseTexts.join('\\n');
        }''')

    async def _wait_for_response(self, max_wait: int = 300) -> str:
        start_time = time.time()
        last_length = 0
        stable_count = 0
        response_started = False
        current_text = ''

        while time.time() - start_time < max_wait:
            try:
                if self.page.is_closed():
                    return current_text

                current_text = await self._get_page_text()

                current_length = len(current_text) if current_text else 0
                elapsed = time.time() - start_time

                if current_length > 20:
                    response_started = True

                if response_started:
                    if current_length > last_length:
                        last_length = current_length
                        stable_count = 0
                    elif current_length == last_length and current_length > 20:
                        stable_count += 1
                        if stable_count >= 2:
                            logger.debug(f'DeepSeekWebOCR: Response stable after {elapsed:.1f}s, {current_length} chars')
                            return current_text

                if 'null' in current_text.lower():
                    logger.debug(f'DeepSeekWebOCR: Got NULL after {elapsed:.1f}s')
                    return current_text

                if not response_started and elapsed > 30:
                    logger.warning(f'DeepSeekWebOCR: No response after {elapsed:.1f}s, current={current_length} chars')

                await asyncio.sleep(0.5)

            except Exception as e:
                if 'Target closed' in str(e) or 'Page closed' in str(e):
                    return current_text if current_text else ""
                await asyncio.sleep(0.5)

        logger.warning(f'DeepSeekWebOCR: Timeout after {max_wait}s, {len(current_text)} chars')
        return current_text if current_text else ""

    async def _ocr_segment(self, image: Image.Image) -> str:
        img = resize_to_max(image, 1000)
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                img.save(tmp, format='PNG', optimize=True)
                tmp.flush()
                tmp.close()
                tmp_path = Path(tmp.name)
            page = await self.context.new_page()
            self.page = page
            await self._navigate_to_deepseek()
            await self._upload_image(tmp_path)
            await self._set_prompt_and_send(PROMPT)
            text = await self._wait_for_response()
            try:
                await page.close()
            except Exception:
                pass
            return _fix_inline_spaces(text)
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()

    def ocr_gif(self, gif_bytes: bytes, max_height: int = 1500) -> str:
        return asyncio.run(self._ocr_gif_async(gif_bytes, max_height))

    async def _ocr_gif_async(self, gif_bytes: bytes, max_height: int = 1500) -> str:
        from sfacglib.ocr_fast import gif_to_frames

        frames = gif_to_frames(gif_bytes)
        segments = []
        for frame in frames:
            segments.extend(split_by_height(frame, max_height))
        logger.info(f'DeepSeekWebOCR: {len(segments)} segments')

        results = []
        for i, img in enumerate(segments):
            logger.info(f'DeepSeekWebOCR: Segment {i+1}/{len(segments)}')
            text = await self._ocr_segment(img)
            if _is_valid_response(text):
                results.append(text)
            logger.info(f'  Segment {i+1}: {len(text)} chars')

        final = deduplicate_texts(results)
        logger.info(f'DeepSeekWebOCR: Total {len(final)} chars')
        return final

    def ocr_gifs(
        self,
        gif_items: list[tuple[str, bytes]],
        max_height: int = 1500,
        output_path: Path | None = None,
    ) -> list[tuple[str, str]]:
        if output_path:
            output_path = Path(output_path)
            output_path.write_text('', encoding='utf-8')
        return asyncio.run(self._ocr_gifs_async(gif_items, max_height, output_path))

    async def _ocr_gifs_async(
        self,
        gif_items: list[tuple[str, bytes]],
        max_height: int = 1500,
        output_path: Path | None = None,
    ) -> list[tuple[str, str]]:
        from sfacglib.ocr_fast import gif_to_frames

        await self._init_browser()
        logger.info('DeepSeekWebOCR: Browser ready')

        results = []
        for idx, (name, gif_bytes) in enumerate(gif_items):
            logger.info(f'DeepSeekWebOCR: [{idx+1}/{len(gif_items)}] {name}')

            if idx > 0:
                await self._send_casual_message()
                self.page = await self.context.new_page()
                await self._navigate_to_deepseek()
                logger.info('DeepSeekWebOCR: New page ready')
            else:
                await self._navigate_to_deepseek()

            frames = gif_to_frames(gif_bytes)
            segments = []
            for frame in frames:
                segments.extend(split_by_height(frame, max_height))

            texts = []
            for i, img in enumerate(segments):
                logger.info(f'  Segment {i+1}/{len(segments)}')
                text = await self._ocr_segment(img)
                if _is_valid_response(text):
                    texts.append(text)
                logger.info(f'  Segment {i+1}: {len(text)} chars')

            final = deduplicate_texts(texts)
            results.append((name, final))
            logger.info(f'  {name}: {len(final)} chars total')

            if output_path:
                with open(output_path, 'a', encoding='utf-8') as f:
                    f.write(f'## {name}\n\n{final}\n\n---\n\n')

        await self._close_browser()
        return results


def create_web_llm_vision(provider: str = 'deepseek', headless: bool = False) -> DeepSeekWebOCR:
    return DeepSeekWebOCR(headless=headless)
