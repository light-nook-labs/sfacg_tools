import json
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from bs4 import BeautifulSoup, Tag
from loguru import logger
from .fetcher import Fetcher
from .selectors import Selectors
from .config import MOBILE_BASE, URL_AUDIO, AUDIOBOOKS_JSON, WORKERS_AUDIO_CHAPTER
from .utils import sanitize_filename, mobile_url, parse_volume_ul, run_tasks


class AudioChapter:

    def __init__(self, title: str, url: str, fetcher: Fetcher | None = None):
        self.title = sanitize_filename(title)
        self.url = mobile_url(url)
        self.fetcher = fetcher or Fetcher()

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

    def download_mp3(self, path: str | Path = './', force: bool = True) -> None:
        path = Path(path)
        file_path = path / f'{self.title}.mp3'
        if not force and file_path.exists():
            return
        mp3_url = self.get_mp3_url()
        if not mp3_url:
            logger.error(f'下载失败: {self.title}')
            return
        content = self.fetcher.get_binary(mp3_url)
        file_path.write_bytes(content)
        logger.bind(force=True).info(f'下载完成 {self.title}')


class AudioVolume:

    def __init__(self, tag: Tag, fetcher: Fetcher | None = None, selectors: Selectors | None = None):
        self.tag: Tag | None = parse_volume_ul(tag)
        self.title: str = tag.string or '未命名卷'
        self.fetcher = fetcher or Fetcher()
        self.sel = selectors or Selectors()

    def get_volume_dict(self) -> dict[str, str]:
        volume_dict: dict[str, str] = {}
        if not self.tag:
            return volume_dict
        for a_tag in self.tag.find_all('a'):
            href = a_tag.get('href', '')
            li = a_tag.li
            title = li.get_text(strip=True) if li else ''
            if href and title:
                volume_dict[href] = title
        return {href: f'{i:03}-{text}' for i, (href, text) in enumerate(volume_dict.items(), start=1)}

    def download_volume(self, path: str | Path = './', force: bool = True) -> None:
        volume_path = Path(path) / sanitize_filename(self.title)
        volume_path.mkdir(parents=True, exist_ok=True)
        volume_dict = self.get_volume_dict()

        def _download(href: str):
            title = volume_dict[href]
            AudioChapter(title, href, fetcher=self.fetcher).download_mp3(volume_path, force)

        run_tasks(volume_dict, _download, WORKERS_AUDIO_CHAPTER, self.title, leave=False)


class Audio:

    def __init__(self, audio_id: int, fetcher: Fetcher | None = None, selectors: Selectors | None = None):
        self.id = audio_id
        self.url = f'{URL_AUDIO}{audio_id}/'
        self.title: str = ''
        self.fetcher = fetcher or Fetcher()
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
    def scan(start: int = 0, end: int = 200, fetcher: Fetcher | None = None, workers: int = 20) -> list[dict[str, int | str]]:
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

    def _get_volume_list(self) -> list[Tag]:
        html = self.fetcher.get_html(self.url)
        soup = BeautifulSoup(html, 'html.parser')
        return soup.find_all(class_='mulu')

    def download(self, path: str | Path = './'):
        download_path = Path(path) / sanitize_filename(self.title)
        download_path.mkdir(parents=True, exist_ok=True)
        volume_tags = self._get_volume_list()
        total = len(volume_tags)
        for i, volume_tag in enumerate(tqdm(volume_tags, desc='Volumes'), start=1):
            volume = AudioVolume(volume_tag, fetcher=self.fetcher, selectors=self.sel)
            volume.download_volume(download_path, force=True)
            logger.bind(force=True).info(f'[{i}/{total}] {volume.title}')


if __name__ == '__main__':
    Audio.scan()
    audio = Audio(153)
    audio.download()
