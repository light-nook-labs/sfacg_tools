import base64
import time
from pathlib import Path
from io import BytesIO
from enum import Enum
from typing import Optional

import requests
from loguru import logger
from PIL import Image

from .config import settings, CORRECT_OCR_SYSTEM_PROMPT


class LLMProvider(Enum):
    """支持的LLM提供商"""
    KIMI = 'kimi'
    DEEPSEEK = 'deepseek'
    OPENAI = 'openai'
    CUSTOM = 'custom'


# 提供商默认配置
PROVIDER_CONFIG = {
    LLMProvider.KIMI: {
        'base_url': 'https://api.moonshot.cn/v1',
        'vision_model': 'moonshot-v1-8k-vision-preview',
        'text_model': 'moonshot-v1-8k',
    },
    LLMProvider.DEEPSEEK: {
        'base_url': 'https://api.deepseek.com/v1',
        'vision_model': 'deepseek-vision',
        'text_model': 'deepseek-chat',
    },
    LLMProvider.OPENAI: {
        'base_url': 'https://api.openai.com/v1',
        'vision_model': 'gpt-4o-mini',
        'text_model': 'gpt-4o-mini',
    },
}


class LLMVision:
    """LLM Vision API客户端，支持图片OCR和文本纠正"""

    def __init__(
        self,
        provider: LLMProvider = LLMProvider.KIMI,
        api_key: str = '',
        base_url: str = '',
        vision_model: str = '',
        text_model: str = '',
    ):
        self.provider = provider
        config = PROVIDER_CONFIG.get(provider, {})
        
        self.api_key = api_key or settings.llm_api_key
        self.base_url = base_url or config.get('base_url', '')
        self.vision_model = vision_model or config.get('vision_model', '')
        self.text_model = text_model or config.get('text_model', '')
        
        if not self.api_key:
            raise ValueError(f"API key required for {provider.value}. Set LLM_API_KEY env or pass api_key parameter.")

    def _get_headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
        }

    def _image_to_base64(self, image: Image.Image, format: str = 'PNG') -> str:
        """将PIL Image转换为base64字符串"""
        buffer = BytesIO()
        image.save(buffer, format=format)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    def _image_bytes_to_base64(self, image_bytes: bytes) -> str:
        """将图片字节转换为base64字符串"""
        return base64.b64encode(image_bytes).decode('utf-8')

    def ocr_image(
        self,
        image: Image.Image | bytes | str | Path,
        prompt: str = '',
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        """使用Vision API识别图片中的文字
        
        Args:
            image: PIL Image, 图片字节, 图片URL, 或图片路径
            prompt: 自定义提示词
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            识别出的文字
        """
        start_time = time.perf_counter()
        
        if not prompt:
            prompt = (
                '请识别图片中的所有文字内容。'
                '如果是小说文本，请保持原文格式，包括段落分隔。'
                '只返回识别出的文字，不要添加任何解释。'
            )
        
        # 处理图片输入
        content = []
        
        if isinstance(image, (str, Path)):
            image_str = str(image)
            if image_str.startswith(('http://', 'https://')):
                # URL图片
                content.append({
                    'type': 'image_url',
                    'image_url': {'url': image_str}
                })
            else:
                # 本地文件
                image_path = Path(image_str)
                if not image_path.exists():
                    raise FileNotFoundError(f"Image file not found: {image_path}")
                image_bytes = image_path.read_bytes()
                b64 = self._image_bytes_to_base64(image_bytes)
                suffix = image_path.suffix.lower().replace('.', '')
                if suffix == 'jpg':
                    suffix = 'jpeg'
                content.append({
                    'type': 'image_url',
                    'image_url': {'url': f'data:image/{suffix};base64,{b64}'}
                })
        elif isinstance(image, bytes):
            # 图片字节
            b64 = self._image_bytes_to_base64(image)
            content.append({
                'type': 'image_url',
                'image_url': {'url': f'data:image/png;base64,{b64}'}
            })
        elif isinstance(image, Image.Image):
            # PIL Image
            b64 = self._image_to_base64(image)
            content.append({
                'type': 'image_url',
                'image_url': {'url': f'data:image/png;base64,{b64}'}
            })
        else:
            raise ValueError(f"Unsupported image type: {type(image)}")
        
        content.append({'type': 'text', 'text': prompt})
        
        payload = {
            'model': self.vision_model,
            'messages': [{'role': 'user', 'content': content}],
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        
        try:
            logger.debug(f'LLMVision.ocr_image: 调用 {self.provider.value} Vision API')
            for attempt in range(3):
                try:
                    resp = requests.post(
                        f'{self.base_url}/chat/completions',
                        headers=self._get_headers(),
                        json=payload,
                        timeout=120,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    result = data['choices'][0]['message']['content'].strip()

                    elapsed = time.perf_counter() - start_time
                    logger.debug(f'LLMVision.ocr_image: 完成，耗时 {elapsed:.3f}s，结果长度 {len(result)}')
                    return result
                except (requests.ConnectionError, requests.Timeout) as e:
                    if attempt < 2:
                        logger.warning(f'LLMVision.ocr_image: 重试 {attempt+1}/3: {e}')
                        time.sleep(2 ** attempt)
                    else:
                        raise
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.error(f'LLMVision.ocr_image: 失败 {e}，耗时 {elapsed:.3f}s')
            raise

    def ocr_images(
        self,
        images: list[Image.Image | bytes | str | Path],
        prompt: str = '',
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> list[str]:
        """批量识别多张图片
        
        Args:
            images: 图片列表
            prompt: 自定义提示词
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            识别结果列表
        """
        results = []
        for i, image in enumerate(images):
            logger.debug(f'LLMVision.ocr_images: 处理图片 {i+1}/{len(images)}')
            try:
                result = self.ocr_image(image, prompt, temperature, max_tokens)
                results.append(result)
            except Exception as e:
                logger.error(f'LLMVision.ocr_images: 图片 {i+1} 失败: {e}')
                results.append('')
        return results

    def correct_text(
        self,
        text: str,
        prompt: str = '',
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        """使用LLM纠正OCR文本
        
        Args:
            text: OCR识别的原始文本
            prompt: 自定义提示词
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            纠正后的文本
        """
        start_time = time.perf_counter()
        
        if not prompt:
            prompt = f'{CORRECT_OCR_SYSTEM_PROMPT}\n\n以下是需要纠正的文本：\n\n{text}'
        
        payload = {
            'model': self.text_model,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': temperature,
            'max_tokens': max_tokens,
        }
        
        try:
            logger.debug(f'LLMVision.correct_text: 调用 {self.provider.value} Text API')
            resp = requests.post(
                f'{self.base_url}/chat/completions',
                headers=self._get_headers(),
                json=payload,
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()
            result = data['choices'][0]['message']['content'].strip()
            
            elapsed = time.perf_counter() - start_time
            logger.debug(f'LLMVision.correct_text: 完成，耗时 {elapsed:.3f}s，结果长度 {len(result)}')
            return result
            
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            logger.error(f'LLMVision.correct_text: 失败 {e}，耗时 {elapsed:.3f}s')
            raise

    def ocr_and_correct(
        self,
        image: Image.Image | bytes | str | Path,
        ocr_prompt: str = '',
        correct_prompt: str = '',
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        """OCR识别图片并纠正文本
        
        Args:
            image: 图片
            ocr_prompt: OCR提示词
            correct_prompt: 纠正提示词
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            纠正后的文本
        """
        # 第一步: OCR识别
        ocr_text = self.ocr_image(image, ocr_prompt, temperature, max_tokens)
        
        if not ocr_text:
            return ''
        
        # 第二步: 纠正文本
        corrected_text = self.correct_text(ocr_text, correct_prompt, temperature, max_tokens)
        
        return corrected_text


def create_llm_vision(
    provider: str = 'kimi',
    api_key: str = '',
    base_url: str = '',
    vision_model: str = '',
    text_model: str = '',
) -> LLMVision:
    """创建LLMVision客户端的便捷函数
    
    Args:
        provider: 提供商名称 (kimi, deepseek, openai, custom)
        api_key: API密钥
        base_url: 自定义API地址
        vision_model: 自定义Vision模型名
        text_model: 自定义Text模型名
        
    Returns:
        LLMVision实例
    """
    try:
        provider_enum = LLMProvider(provider.lower())
    except ValueError:
        raise ValueError(f"Unsupported provider: {provider}. Supported: {[p.value for p in LLMProvider]}")
    
    return LLMVision(
        provider=provider_enum,
        api_key=api_key,
        base_url=base_url,
        vision_model=vision_model,
        text_model=text_model,
    )