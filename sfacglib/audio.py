import json
import re
from pathlib import Path

from bs4 import BeautifulSoup
from loguru import logger

from .base import Container, Item, Section
from .config import AUDIOBOOKS_JSON, URL_AUDIO
from .fetcher import Fetcher
from .selectors import Selectors
from .utils import mobile_url, parse_volume_ul


class AudioChapter(Item):
    def __init__(self, idx: int, title: str, url: str, fetcher: Fetcher | None = None):
        super().__init__(idx, title, mobile_url(url))
        self.fetcher = fetcher or Fetcher()

    def download(self, save_path: Path, pbar=None, lock=None):
        mp3_url = self.get_mp3_url()
        if not mp3_url:
            logger.error(f'获取音频链接失败: {self.title}')
            return
        content = self.fetcher.get_binary(mp3_url)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(content)
        logger.bind(force=True).info(f'下载完成 {self.title}')
        if pbar and lock:
            with lock:
                pbar.update(1)

    def get_mp3_url(self) -> str | None:
        try:
            html = self.fetcher.get_html(self.url)
            soup = BeautifulSoup(html, 'html.parser')
            mp3_pattern = re.compile(r'https?://[^\s"\']+\.mp3')
            for script in soup.find_all('script'):
                if script.string:
                    match = mp3_pattern.search(script.string)
                    if match:
                        return match.group()
            return None
        except Exception as e:
            logger.error(f'获取音频链接失败: {self.url} - {e}')
            return None


class AudioVolume(Section):
    def __init__(self, idx: int, title: str, chapters: list[AudioChapter]):
        super().__init__(idx, title)
        self.chapters = chapters

    def get_items(self) -> list[AudioChapter]:
        return self.chapters


def _parse_audio_volumes(
    soup: BeautifulSoup,
    fetcher: Fetcher,
) -> list[AudioVolume]:
    volumes: list[AudioVolume] = []
    vol_idx = 0

    for vol_tag in soup.find_all(class_='mulu'):
        vol_idx += 1
        vol_title = vol_tag.string or '未命名卷'
        ul_tag = parse_volume_ul(vol_tag)
        chapters: list[AudioChapter] = []
        if ul_tag:
            ch_idx = 0
            for a in ul_tag.find_all('a'):
                href = a.get('href', '')
                if href:
                    ch_idx += 1
                    li = a.li
                    ch_title = li.get_text(strip=True) if li else ''
                    if ch_title:
                        chapters.append(AudioChapter(ch_idx, ch_title, href, fetcher))
        volumes.append(AudioVolume(vol_idx, vol_title, chapters))

    return volumes


class Audio(Container):
    def __init__(self, audio_id: int, fetcher: Fetcher | None = None, selectors: Selectors | None = None):
        super().__init__(fetcher)
        self.id = str(audio_id)
        self.url = f'{URL_AUDIO}{audio_id}/'
        self.sel = selectors or Selectors()

        if not AUDIOBOOKS_JSON.exists():
            raise FileNotFoundError(f'JSON文件不存在: {AUDIOBOOKS_JSON}\n请调用 Audio.scan() 更新')

        data = json.loads(AUDIOBOOKS_JSON.read_text(encoding='utf-8'))
        for item in data:
            if item.get('id', 0) == audio_id:
                self.title = item.get('title', '')
                break
        if not self.title:
            raise ValueError(f'未找到id为{audio_id}的有声小说，请调用 Audio.scan() 更新')

    @staticmethod
    def scan(
        start: int = 0, end: int = 200, fetcher: Fetcher | None = None, workers: int = 20
    ) -> list[dict[str, int | str]]:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from tqdm import tqdm

        if fetcher is None:
            fetcher = Fetcher(default_delay=0.05)
        valid: list[dict[str, int | str]] = []

        def _check(aid: int) -> dict[str, int | str] | None:
            try:
                html = fetcher.get_html(f'{URL_AUDIO}{aid}/')
                soup = BeautifulSoup(html, 'html.parser')
                title = soup.title.string if soup.title else ''
                if title and title != '出错啦':
                    return {'id': aid, 'title': title.split('音频列表')[0]}
            except Exception:
                pass
            return None

        ids = list(range(start + 1, end + 1))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(_check, aid): aid for aid in ids}
            for future in tqdm(as_completed(futures), total=len(futures), desc='Scanning'):
                result = future.result()
                if result:
                    valid.append(result)
                    logger.bind(force=True).info(f'{result["id"]} {result["title"]}')

        valid.sort(key=lambda x: x['id'])

        if valid:
            AUDIOBOOKS_JSON.write_text(
                json.dumps(valid, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
            logger.bind(force=True).info(f'已更新 {AUDIOBOOKS_JSON}: {len(valid)} 本')
        else:
            logger.warning('未找到有声小说')
        return valid

    @staticmethod
    def list_all() -> list[dict[str, int | str]]:
        if not AUDIOBOOKS_JSON.exists():
            return []
        return json.loads(AUDIOBOOKS_JSON.read_text(encoding='utf-8'))

    def get_info(self) -> tuple[str, str]:
        info_md = f"""
# {self.title}

有声小说地址：{self.url}
"""
        info_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{self.title}</title></head>
<body>
<h1>{self.title}</h1>
<p>有声小说地址：<a href="{self.url}">{self.url}</a></p>
</body>
</html>"""
        return info_md, info_html

    def get_sections(self) -> list[AudioVolume]:
        html = self.fetcher.get_html(self.url)
        soup = BeautifulSoup(html, 'html.parser')
        return _parse_audio_volumes(soup, self.fetcher)

    def _download_item(self, item: AudioChapter, save_path: Path, pbar=None, lock=None):
        item.download(save_path, pbar, lock)


if __name__ == '__main__':
    Audio.scan()
    audio = Audio(153)
    audio.download()
