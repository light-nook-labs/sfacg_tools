import os
import time
import asyncio
import tempfile
from pathlib import Path
from io import BytesIO
from enum import Enum
from typing import Optional

from loguru import logger
from PIL import Image


class WebLLMProvider(Enum):
    """支持的Web LLM提供商"""
    KIMI = 'kimi'
    DEEPSEEK = 'deepseek'


# 提供商Web配置
WEB_PROVIDER_CONFIG = {
    WebLLMProvider.KIMI: {
        'url': 'https://kimi.moonshot.cn/',
        'name': 'Kimi',
    },
    WebLLMProvider.DEEPSEEK: {
        'url': 'https://chat.deepseek.com/',
        'name': 'DeepSeek',
    },
}


class WebLLMVision:
    """通过Web界面调用LLM Vision，无需API Key"""

    def __init__(
        self,
        provider: WebLLMProvider = WebLLMProvider.KIMI,
        headless: bool = False,
        timeout: int = 60000,
    ):
        self.provider = provider
        self.headless = headless
        self.timeout = timeout
        self.config = WEB_PROVIDER_CONFIG.get(provider, {})
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def _init_browser(self):
        """初始化浏览器（使用持久化上下文保存登录状态）"""
        try:
            from playwright.async_api import async_playwright
            self.playwright = await async_playwright().start()
            
            # 使用持久化上下文目录保存cookie和登录状态
            user_data_dir = Path.home() / '.sfacg' / 'browser_data'
            user_data_dir.mkdir(parents=True, exist_ok=True)
            
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=self.headless,
                accept_downloads=False,
            )
            # 获取或创建页面
            if self.context.pages:
                self.page = self.context.pages[0]
            else:
                self.page = await self.context.new_page()
            
            logger.debug(f'WebLLMVision: 浏览器初始化完成 (数据目录: {user_data_dir})')
        except ImportError:
            raise ImportError(
                "Playwright not installed. Run: uv sync --extra web && uv run playwright install chromium"
            )

    async def _close_browser(self):
        """关闭浏览器"""
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
        logger.debug(f'WebLLMVision: 浏览器已关闭')

    async def _navigate_to_provider(self):
        """导航到提供商网站"""
        url = self.config.get('url', '')
        logger.debug(f'WebLLMVision: 导航到 {url}')
        await self.page.goto(url, wait_until='networkidle', timeout=self.timeout)
        await asyncio.sleep(2)  # 等待页面加载
        
        # DeepSeek需要选择Vision模式
        if self.provider == WebLLMProvider.DEEPSEEK:
            await self._select_deepseek_vision_mode()

    async def _select_deepseek_vision_mode(self):
        """选择DeepSeek的Vision模式"""
        try:
            # 查找Vision单选按钮
            vision_radio = await self.page.query_selector('input[value="vision"], label:has-text("Vision")')
            if vision_radio:
                await vision_radio.click()
                await asyncio.sleep(1)
                logger.debug('WebLLMVision: 已选择Vision模式')
            else:
                # 尝试通过JavaScript选择
                await self.page.evaluate('''() => {
                    // 查找包含"Vision"文本的元素并点击
                    const elements = document.querySelectorAll('*');
                    for (const el of elements) {
                        if (el.textContent === 'Vision' && el.tagName !== 'SCRIPT') {
                            el.click();
                            return true;
                        }
                    }
                    // 或者直接选择radio
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
                logger.debug('WebLLMVision: 尝试选择Vision模式')
        except Exception as e:
            logger.debug(f'WebLLMVision: 选择Vision模式失败: {e}')

    async def _upload_image_and_ask(self, image_path: Path, prompt: str) -> str:
        """上传图片并提问
        
        Args:
            image_path: 图片路径
            prompt: 提示词
            
        Returns:
            LLM响应文本
        """
        logger.debug(f'WebLLMVision: 上传图片 {image_path}')
        
        # 根据不同提供商处理
        if self.provider == WebLLMProvider.KIMI:
            return await self._kimi_upload_and_ask(image_path, prompt)
        elif self.provider == WebLLMProvider.DEEPSEEK:
            return await self._deepseek_upload_and_ask(image_path, prompt)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    async def _kimi_upload_and_ask(self, image_path: Path, prompt: str) -> str:
        """Kimi上传图片并提问"""
        try:
            # 等待页面完全加载
            await asyncio.sleep(3)
            
            # 查找文件上传按钮
            # Kimi的上传按钮通常在输入框附近
            upload_button = await self.page.wait_for_selector(
                'input[type="file"], [data-testid="upload"], .upload-btn, button[aria-label*="upload"], button[aria-label*="上传"]',
                timeout=10000
            )
            
            if upload_button:
                # 设置文件
                await upload_button.set_input_files(str(image_path))
                logger.debug(f'WebLLMVision: Kimi图片已上传')
                
                # 等待上传完成
                await asyncio.sleep(3)
            
            # 查找输入框
            input_box = await self.page.wait_for_selector(
                'textarea, [contenteditable="true"], input[type="text"]',
                timeout=10000
            )
            
            if input_box:
                # 输入提示词
                await input_box.fill(prompt)
                await asyncio.sleep(1)
                
                # 发送消息
                send_button = await self.page.query_selector(
                    'button[type="submit"], button[aria-label*="send"], button[aria-label*="发送"]'
                )
                if send_button:
                    await send_button.click()
                else:
                    # 尝试按Enter发送
                    await input_box.press('Enter')
                
                logger.debug(f'WebLLMVision: Kimi消息已发送')
                
                # 等待响应
                await asyncio.sleep(5)
                
                # 等待响应完成（检测是否有新的消息出现）
                response_text = await self._wait_for_response()
                return response_text
            
            return ""
            
        except Exception as e:
            logger.error(f'WebLLMVision: Kimi上传失败: {e}')
            raise

    async def _deepseek_upload_and_ask(self, image_path: Path, prompt: str) -> str:
        """DeepSeek上传图片并提问"""
        try:
            # 等待页面完全加载
            await asyncio.sleep(3)
            
            # 检查图片尺寸，如果太大则缩小
            max_dim = 1000
            file_size = image_path.stat().st_size
            
            # 用PIL检查尺寸
            from PIL import Image as PILImage
            with PILImage.open(image_path) as img:
                w, h = img.size
            
            if w > max_dim or h > max_dim:
                logger.debug(f'WebLLMVision: 图片尺寸太大({w}x{h})，缩小中...')
                img = PILImage.open(image_path)
                ratio = min(max_dim / w, max_dim / h)
                new_size = (int(w * ratio), int(h * ratio))
                img = img.resize(new_size, PILImage.Resampling.LANCZOS)
                compressed_path = image_path.with_suffix('.png')
                img.save(compressed_path, format='PNG', optimize=True)
                image_path = compressed_path
                logger.debug(f'WebLLMVision: 缩小后 {new_size[0]}x{new_size[1]}')
            
            # DeepSeek的文件上传input是隐藏的，直接操作
            upload_input = await self.page.query_selector('input[type="file"]')
            
            if upload_input:
                # 设置文件（即使元素隐藏也可以操作）
                await upload_input.set_input_files(str(image_path))
                logger.debug(f'WebLLMVision: DeepSeek图片已上传')
                
                # 等待图片加载完成
                await asyncio.sleep(5)
            
            # 使用JavaScript设置textarea值（React兼容）
            await self.page.evaluate('''(text) => {
                const textarea = document.querySelector('textarea');
                if (textarea) {
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype, 'value'
                    ).set;
                    nativeInputValueSetter.call(textarea, text);
                    textarea.dispatchEvent(new Event('input', { bubbles: true }));
                    textarea.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
                return false;
            }''', prompt)
            
            await asyncio.sleep(1)
            
            # 按Enter发送（DeepSeek用Enter发送）
            await self.page.keyboard.press('Enter')
            
            logger.debug(f'WebLLMVision: DeepSeek消息已发送')
            
            # 等待响应
            await asyncio.sleep(5)
            
            # 等待响应完成
            response_text = await self._wait_for_deepseek_response()
            return response_text
            
        except Exception as e:
            logger.error(f'WebLLMVision: DeepSeek上传失败: {e}')
            raise

    async def _deepseek_upload_and_ask_text_only(self, prompt: str) -> str:
        """DeepSeek只发送文字（不上传图片）"""
        try:
            await asyncio.sleep(2)
            
            # 使用JavaScript设置textarea值
            await self.page.evaluate('''(text) => {
                const textarea = document.querySelector('textarea');
                if (textarea) {
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype, 'value'
                    ).set;
                    nativeInputValueSetter.call(textarea, text);
                    textarea.dispatchEvent(new Event('input', { bubbles: true }));
                    textarea.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
                return false;
            }''', prompt)
            
            await asyncio.sleep(1)
            
            # 按Enter发送
            await self.page.keyboard.press('Enter')
            logger.debug(f'WebLLMVision: DeepSeek文字消息已发送')
            
            # 等待响应
            await asyncio.sleep(5)
            
            # 等待响应完成
            response_text = await self._wait_for_deepseek_response()
            return response_text
            
        except Exception as e:
            logger.error(f'WebLLMVision: DeepSeek文字发送失败: {e}')
            raise

    async def _wait_for_response(self, max_wait: int = 60) -> str:
        """等待LLM响应完成（通用版本）
        
        Args:
            max_wait: 最大等待时间（秒）
            
        Returns:
            响应文本
        """
        logger.debug(f'WebLLMVision: 等待响应...')
        
        start_time = time.time()
        last_text = ""
        stable_count = 0
        
        while time.time() - start_time < max_wait:
            # 获取所有消息
            messages = await self.page.query_selector_all('.message, .chat-message, [data-testid*="message"]')
            
            if messages:
                # 获取最后一条消息的文本
                current_text = await messages[-1].inner_text()
                
                if current_text == last_text:
                    stable_count += 1
                    # 如果文本稳定了3秒，认为响应完成
                    if stable_count >= 3:
                        logger.debug(f'WebLLMVision: 响应完成，长度 {len(current_text)}')
                        return current_text
                else:
                    stable_count = 0
                    last_text = current_text
            
            await asyncio.sleep(1)
        
        logger.warning(f'WebLLMVision: 等待响应超时')
        return last_text

    async def _wait_for_deepseek_response(self, max_wait: int = 300) -> str:
        """等待DeepSeek响应完成
        
        Args:
            max_wait: 最大等待时间（秒）
            
        Returns:
            响应文本
        """
        logger.debug(f'WebLLMVision: 等待DeepSeek响应...')
        
        start_time = time.time()
        last_length = 0
        stable_count = 0
        response_started = False
        
        while time.time() - start_time < max_wait:
            try:
                # 检查页面是否还活着
                if self.page.is_closed():
                    logger.warning('WebLLMVision: 页面已关闭')
                    return ""
                
                # 提取响应文本（跳过用户消息和UI元素）
                current_text = await self.page.evaluate('''() => {
                    const allElements = document.querySelectorAll('*');
                    const responseTexts = [];
                    let inResponse = false;
                    
                    for (const el of allElements) {
                        if (el.children.length === 0 || 
                            (el.childNodes.length === 1 && el.childNodes[0].nodeType === 3)) {
                            const text = el.innerText || el.textContent || '';
                            if (text.trim()) {
                                // 找到用户消息标记，之后就是响应
                                if (text.includes('请识别图片中的中文文字') || 
                                    text.includes('直接返回修正后的完整文本') ||
                                    text.includes('OCR原文：')) {
                                    inResponse = true;
                                    continue;
                                }
                                // 跳过UI元素
                                if (inResponse && 
                                    !text.includes('DeepThink') && 
                                    !text.includes('Search') && 
                                    !text.includes('AI-generated') &&
                                    !text.includes('Message DeepSeek')) {
                                    responseTexts.push(text.trim());
                                }
                            }
                        }
                    }
                    return responseTexts.join('\\n');
                }''')
                
                current_length = len(current_text) if current_text else 0
                
                # 检测响应是否开始
                if current_length > 50:
                    response_started = True
                
                if response_started:
                    # 检查内容是否还在增长
                    if current_length > last_length:
                        last_length = current_length
                        stable_count = 0
                        logger.debug(f'WebLLMVision: 响应进行中... {current_length} chars')
                    elif current_length == last_length and current_length > 50:
                        # 内容长度大于50且稳定时认为完成
                        stable_count += 1
                        # 内容稳定3秒后认为完成
                        if stable_count >= 3:
                            logger.debug(f'WebLLMVision: DeepSeek响应完成，长度 {current_length}')
                            return current_text
                
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.warning(f'WebLLMVision: 等待响应时出错: {e}')
                # 如果页面关闭，返回已有的内容
                if 'Target closed' in str(e) or 'Page closed' in str(e):
                    return current_text if current_text else ""
                await asyncio.sleep(1)
        
        logger.warning(f'WebLLMVision: DeepSeek等待响应超时')
        return current_text if current_text else ""

    async def _copy_response_from_page(self) -> str:
        """通过点击复制按钮获取响应文本
        
        Returns:
            复制的文本，失败返回空字符串
        """
        try:
            # DeepSeek的复制按钮在响应下方的工具栏中
            # 找到所有 role="button" 的元素
            buttons = await self.page.query_selector_all('[role="button"]')
            
            # 复制按钮通常是响应区域的第一个按钮（clipboard icon）
            # 从后往前找，因为最新的响应在最后
            for btn in reversed(buttons):
                # 检查是否包含SVG（图标按钮）
                svg = await btn.query_selector('svg')
                if not svg:
                    continue
                
                # 获取SVG的path来识别复制按钮
                path = await svg.query_selector('path')
                if path:
                    path_d = await path.get_attribute('d')
                    # 复制图标的path特征：包含 "M6.14929" (clipboard icon)
                    if path_d and 'M6.14929' in path_d:
                        # 点击复制按钮
                        await btn.click()
                        await asyncio.sleep(1)
                        
                        # 尝试从剪贴板读取
                        try:
                            clipboard_text = await self.page.evaluate('''async () => {
                                try {
                                    return await navigator.clipboard.readText();
                                } catch (e) {
                                    return '';
                                }
                            }''')
                            if clipboard_text and len(clipboard_text) > 10:
                                return clipboard_text
                        except Exception:
                            pass
                        
                        # 剪贴板读取失败，从按钮的父元素获取文本
                        # 向上找到响应容器
                        response_text = await btn.evaluate('''(el) => {
                            // 向上找到包含响应文本的容器
                            let container = el.parentElement;
                            while (container && !container.querySelector('[class*="message"]')) {
                                container = container.parentElement;
                            }
                            if (container) {
                                // 获取容器中的文本（排除按钮区域）
                                const textElements = container.querySelectorAll('div, p, span');
                                let texts = [];
                                for (const t of textElements) {
                                    const text = t.innerText || '';
                                    if (text && text.length > 5 && !t.querySelector('[role="button"]')) {
                                        texts.push(text);
                                    }
                                }
                                return texts.join('\\n');
                            }
                            return '';
                        }''')
                        if response_text and len(response_text) > 10:
                            return response_text
            
            return ""
        except Exception as e:
            logger.debug(f'_copy_response_from_page: 失败 {e}')
            return ""

    def _extract_deepseek_response(self, full_text: str) -> str:
        """从DeepSeek页面文本中提取响应内容
        
        Args:
            full_text: 页面完整文本
            
        Returns:
            提取的响应文本
        """
        # 过滤掉UI元素
        skip_patterns = [
            'Message DeepSeek', 'DeepThink', 'Search', 'AI-generated',
            'Start chatting', 'Instant', 'Expert', 'Vision',
            'New chat', '⌘ J'
        ]
        
        lines = full_text.split('\n')
        clean_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if any(skip in line for skip in skip_patterns):
                continue
            # 跳过纯数字行（侧边栏日期）
            if line.isdigit() and len(line) == 4:
                continue
            clean_lines.append(line)
        
        if not clean_lines:
            return ""
        
        # 找到用户消息的结束位置（通常是 "OCR原文：" 之后的内容）
        user_msg_end = -1
        for i, line in enumerate(clean_lines):
            # 找到OCR原文的最后一行
            if '这个图案并不明显' in line or '阳光才能看到' in line:
                user_msg_end = i
                break
            # 或者找 "直接返回修正后的完整文本" 之后
            if '直接返回修正后的完整文本' in line:
                user_msg_end = i
                break
        
        if user_msg_end != -1 and user_msg_end < len(clean_lines) - 1:
            # 返回用户消息之后的内容
            response_lines = clean_lines[user_msg_end + 1:]
            return '\n'.join(response_lines)
        
        # 备选：返回最后的内容（跳过可能的用户消息）
        # 假设用户消息在前半部分，响应在后半部分
        mid = len(clean_lines) // 2
        if mid > 0:
            return '\n'.join(clean_lines[mid:])
        
        return '\n'.join(clean_lines)

    async def ocr_image_async(
        self,
        image: Image.Image | bytes | str | Path,
        prompt: str = '',
    ) -> str:
        """异步OCR识别图片
        
        Args:
            image: PIL Image, 图片字节, 图片URL, 或图片路径
            prompt: 自定义提示词
            
        Returns:
            识别出的文字
        """
        if not prompt:
            prompt = (
                '请识别图片中的所有文字内容。'
                '如果是小说文本，请保持原文格式，包括段落分隔。'
                '只返回识别出的文字，不要添加任何解释。'
            )
        
        # 处理图片输入
        if isinstance(image, (str, Path)):
            image_path = Path(image)
            if not image_path.exists():
                raise FileNotFoundError(f"Image file not found: {image_path}")
        elif isinstance(image, bytes):
            # 保存到临时文件
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp.write(image)
                image_path = Path(tmp.name)
        elif isinstance(image, Image.Image):
            # 保存到临时文件
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                image.save(tmp, format='PNG')
                image_path = Path(tmp.name)
        else:
            raise ValueError(f"Unsupported image type: {type(image)}")
        
        try:
            # 初始化浏览器
            await self._init_browser()
            
            # 导航到提供商网站
            await self._navigate_to_provider()
            
            # 上传图片并提问
            result = await self._upload_image_and_ask(image_path, prompt)
            
            return result
            
        finally:
            # 关闭浏览器
            await self._close_browser()
            
            # 清理临时文件
            if 'image_path' in locals() and image_path.exists():
                try:
                    image_path.unlink()
                except:
                    pass

    def ocr_image(
        self,
        image: Image.Image | bytes | str | Path,
        prompt: str = '',
    ) -> str:
        """同步OCR识别图片
        
        Args:
            image: PIL Image, 图片字节, 图片URL, 或图片路径
            prompt: 自定义提示词
            
        Returns:
            识别出的文字
        """
        return asyncio.run(self.ocr_image_async(image, prompt))

    async def correct_text_async(
        self,
        text: str,
        prompt: str = '',
    ) -> str:
        """异步纠正文本
        
        Args:
            text: OCR识别的原始文本
            prompt: 自定义提示词
            
        Returns:
            纠正后的文本
        """
        if not prompt:
            prompt = (
                '你是一位中文小说编辑。以下是从图片OCR识别的文本，存在识别错误、断行、缺字等问题。\n\n'
                '任务：\n'
                '1. 将断行的句子拼接成完整句子\n'
                '2. 修正错别字\n'
                '3. 如果有语义不通或明显缺失的内容，根据上下文适当补充，使文本通顺\n'
                '4. 保持轻小说风格，段落简短\n'
                '5. 直接返回修正后的完整文本\n\n'
                f'OCR原文：\n{text}'
            )
        
        try:
            # 初始化浏览器
            await self._init_browser()
            
            # 导航到提供商网站
            await self._navigate_to_provider()
            
            # 根据提供商选择不同的处理方式
            if self.provider == WebLLMProvider.DEEPSEEK:
                # DeepSeek使用JavaScript设置值 + Enter发送
                await self.page.evaluate('''(text) => {
                    const textarea = document.querySelector('textarea');
                    if (textarea) {
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLTextAreaElement.prototype, 'value'
                        ).set;
                        nativeInputValueSetter.call(textarea, text);
                        textarea.dispatchEvent(new Event('input', { bubbles: true }));
                        textarea.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                    return false;
                }''', prompt)
                
                await asyncio.sleep(1)
                await self.page.keyboard.press('Enter')
                
                logger.debug(f'WebLLMVision: DeepSeek消息已发送')
                
                # 等待响应
                await asyncio.sleep(5)
                response_text = await self._wait_for_deepseek_response()
            else:
                # Kimi等其他提供商使用传统方式
                input_box = await self.page.wait_for_selector(
                    'textarea, [contenteditable="true"], input[type="text"]',
                    timeout=10000
                )
                
                if input_box:
                    await input_box.fill(prompt)
                    await asyncio.sleep(1)
                    
                    send_button = await self.page.query_selector(
                        'button[type="submit"], button[aria-label*="send"], button[aria-label*="发送"]'
                    )
                    if send_button:
                        await send_button.click()
                    else:
                        await input_box.press('Enter')
                    
                    logger.debug(f'WebLLMVision: 消息已发送')
                    
                    await asyncio.sleep(5)
                    response_text = await self._wait_for_response()
                else:
                    response_text = ""
            
            return response_text
            
        finally:
            # 关闭浏览器
            await self._close_browser()

    def correct_text(
        self,
        text: str,
        prompt: str = '',
    ) -> str:
        """同步纠正文本
        
        Args:
            text: OCR识别的原始文本
            prompt: 自定义提示词
            
        Returns:
            纠正后的文本
        """
        return asyncio.run(self.correct_text_async(text, prompt))

    async def ocr_and_correct_async(
        self,
        image: Image.Image | bytes | str | Path,
        ocr_prompt: str = '',
        correct_prompt: str = '',
    ) -> str:
        """异步OCR识别图片并纠正文本
        
        Args:
            image: 图片
            ocr_prompt: OCR提示词
            correct_prompt: 纠正提示词
            
        Returns:
            纠正后的文本
        """
        # 第一步: OCR识别
        ocr_text = await self.ocr_image_async(image, ocr_prompt)
        
        if not ocr_text:
            return ''
        
        # 第二步: 纠正文本
        corrected_text = await self.correct_text_async(ocr_text, correct_prompt)
        
        return corrected_text

    def ocr_and_correct(
        self,
        image: Image.Image | bytes | str | Path,
        ocr_prompt: str = '',
        correct_prompt: str = '',
    ) -> str:
        """同步OCR识别图片并纠正文本
        
        Args:
            image: 图片
            ocr_prompt: OCR提示词
            correct_prompt: 纠正提示词
            
        Returns:
            纠正后的文本
        """
        return asyncio.run(self.ocr_and_correct_async(image, ocr_prompt, correct_prompt))


def create_web_llm_vision(
    provider: str = 'kimi',
    headless: bool = False,
    timeout: int = 60000,
) -> WebLLMVision:
    """创建WebLLMVision客户端的便捷函数
    
    Args:
        provider: 提供商名称 (kimi, deepseek)
        headless: 是否无头模式
        timeout: 超时时间（毫秒）
        
    Returns:
        WebLLMVision实例
    """
    try:
        provider_enum = WebLLMProvider(provider.lower())
    except ValueError:
        raise ValueError(f"Unsupported provider: {provider}. Supported: {[p.value for p in WebLLMProvider]}")
    
    return WebLLMVision(
        provider=provider_enum,
        headless=headless,
        timeout=timeout,
    )