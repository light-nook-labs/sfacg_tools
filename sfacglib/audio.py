import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup
from loguru import logger

from .base import Container, InvalidNovelError, Item, Section
from .config import AUDIOBOOKS_JSON, URL_AUDIO, WORKERS_AUDIO_CHAPTER, _ensure_config
from .fetcher import Fetcher
from .models.catalog import AudioCatalog, AudioCatalogItem, AudioCatalogSection
from .selectors import Selectors
from .utils import mobile_url, parse_volume_ul
from .utils import sanitize_filename as _sanitize_filename


class AudioChapter(Item):
    def __init__(self, idx: int, title: str, url: str, fetcher: Fetcher | None = None, mp3_url: str | None = None):
        super().__init__(idx, title, mobile_url(url))
        self.fetcher = fetcher or Fetcher()
        self.mp3_url = mp3_url

    def get_mp3_url(self) -> str | None:
        if self.mp3_url:
            return self.mp3_url
        try:
            html = self.fetcher.get_html(self.url)
            soup = BeautifulSoup(html, 'html.parser')
            mp3_pattern = re.compile(r'audioPlayer\.loadAudio\("([^"]+)"')
            for script in soup.find_all('script'):
                if script.string:
                    match = mp3_pattern.search(script.string)
                    if match:
                        self.mp3_url = match.group(1)
                        return self.mp3_url
            return None
        except Exception as e:
            logger.error(f'获取音频链接失败: {self.url} - {e}')
            return None

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

    async def download_async(
        self,
        save_path: Path,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        lock: asyncio.Lock,
        counter: dict,
        total: int,
    ):
        mp3_url = self.get_mp3_url()
        if not mp3_url:
            async with lock:
                counter['failed'] += 1
            logger.error(f'获取音频链接失败: {self.title}')
            return
        async with semaphore:
            try:
                async with session.get(mp3_url) as resp:
                    resp.raise_for_status()
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(save_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(64 * 1024):
                            f.write(chunk)
                async with lock:
                    counter['done'] += 1
                    done = counter['done']
                logger.bind(force=True).info(f'[{done}/{total}] 下载完成 {self.title}')
            except Exception as e:
                async with lock:
                    counter['failed'] += 1
                logger.error(f'下载失败: {self.title} - {e}')


class AudioVolume(Section):
    def __init__(self, idx: int, title: str, chapters: list[AudioChapter]):
        super().__init__(idx, title)
        self.chapters = chapters

    def get_items(self) -> list[AudioChapter]:
        return self.chapters


def _parse_audio_volumes(
    soup: BeautifulSoup,
    fetcher: Fetcher,
) -> list[dict]:
    sections = []
    vol_idx = 0

    for vol_tag in soup.find_all(class_='mulu'):
        vol_idx += 1
        vol_title = vol_tag.string or '未命名卷'
        ul_tag = parse_volume_ul(vol_tag)
        items = []
        if ul_tag:
            ch_idx = 0
            for a in ul_tag.find_all('a'):
                href = a.get('href', '')
                if href:
                    ch_idx += 1
                    li = a.li
                    ch_title = li.get_text(strip=True) if li else ''
                    if ch_title:
                        items.append(
                            {
                                'idx': ch_idx,
                                'title': ch_title,
                                'url': href,
                            }
                        )
        sections.append(
            {
                'idx': vol_idx,
                'title': vol_title,
                'dir': f'sec_{vol_idx:03d}_{_sanitize_filename(vol_title)}',
                'items': items,
            }
        )

    return sections


def _fetch_mp3_url(item: dict, fetcher: Fetcher) -> dict:
    try:
        html = fetcher.get_html(mobile_url(item['url']))
        soup = BeautifulSoup(html, 'html.parser')
        img_tag = soup.find('img')
        if img_tag and img_tag.get('src'):
            item['cover'] = img_tag['src']
        mp3_pattern = re.compile(r'audioPlayer\.loadAudio\("([^"]+)"')
        for script in soup.find_all('script'):
            if script.string:
                match = mp3_pattern.search(script.string)
                if match:
                    item['mp3_url'] = match.group(1)
                    return item
    except Exception:
        pass
    item['mp3_url'] = None
    return item


class Audio(Container):
    def __init__(
        self,
        audio_id: int,
        output_dir: str | Path | None = None,
        fetcher: Fetcher | None = None,
        selectors: Selectors | None = None,
    ):
        super().__init__(output_dir, fetcher)
        self.id = str(audio_id)
        self.url = f'{URL_AUDIO}{audio_id}/'
        self.sel = selectors or Selectors()
        _ensure_config()

        if not AUDIOBOOKS_JSON.exists():
            Audio.scan()

        try:
            data = json.loads(AUDIOBOOKS_JSON.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f'读取有声目录失败: {e}')
            data = []

        for item in data:
            if item.get('id', 0) == audio_id:
                self.title = item.get('title', '')
                break
        if not self.title:
            raise InvalidNovelError(f'未找到id为{audio_id}的有声小说，请调用 Audio.scan() 更新')

        if not self.setup():
            raise InvalidNovelError(f'HTTP错误或URL无效 (aid={audio_id})')

    def _load_catalog(self) -> AudioCatalog:
        return AudioCatalog.load(self.dir_path / 'catalog.json')

    @staticmethod
    def scan(
        start: int = 0, end: int = 500, fetcher: Fetcher | None = None, workers: int = 20, force: bool = False
    ) -> list[dict[str, int | str]]:
        from tqdm import tqdm

        _ensure_config()
        if not force and AUDIOBOOKS_JSON.exists():
            try:
                data = json.loads(AUDIOBOOKS_JSON.read_text(encoding='utf-8'))
                logger.bind(force=True).info(f'从缓存加载 {len(data)} 本有声小说')
                return data
            except (json.JSONDecodeError, OSError):
                pass

        if fetcher is None:
            fetcher = Fetcher(default_delay=0.05)
        valid: list[dict[str, int | str]] = []

        def _check(aid: int) -> dict[str, int | str] | None:
            try:
                html = fetcher.get_html(f'{URL_AUDIO}{aid}/')
                soup = BeautifulSoup(html, 'html.parser')
                title = soup.title.get_text(strip=True) if soup.title else ''
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
        _ensure_config()
        if not AUDIOBOOKS_JSON.exists():
            return []
        try:
            return json.loads(AUDIOBOOKS_JSON.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            return []

    def setup(self) -> bool:
        try:
            self.dir_path = self.output_dir / _sanitize_filename(self.title)
            self.dir_path.mkdir(parents=True, exist_ok=True)

            html = self.fetcher.get_html(self.url)
            soup = BeautifulSoup(html, 'html.parser')
            raw_sections = _parse_audio_volumes(soup, self.fetcher)

            all_items = []
            for sec in raw_sections:
                for item in sec['items']:
                    safe_title = _sanitize_filename(item['title'])
                    item['file'] = f'{sec["dir"]}/item_{item["idx"]:03d}_{safe_title}.mp3'
                    item['url'] = f'https://m.sfacg.com{item["url"]}' if item['url'].startswith('/') else item['url']
                    all_items.append(item)

            logger.bind(force=True).info(f'预取 MP3 链接: {len(all_items)} 项')
            cover_url = ''
            with ThreadPoolExecutor(max_workers=WORKERS_AUDIO_CHAPTER) as executor:
                futures = {executor.submit(_fetch_mp3_url, item, self.fetcher): item for item in all_items}
                for future in as_completed(futures):
                    result = future.result()
                    if not cover_url and result.get('cover'):
                        cover_url = result['cover']
                    result.pop('cover', None)
            fetched = sum(1 for item in all_items if item.get('mp3_url'))
            logger.bind(force=True).info(f'预取完成: {fetched}/{len(all_items)} 成功')

            self.cover = cover_url
            cover_file = self._download_cover()

            sections = []
            for sec in raw_sections:
                audio_items = []
                for item in sec['items']:
                    audio_items.append(
                        AudioCatalogItem(
                            idx=item['idx'],
                            title=item['title'],
                            url=item['url'],
                            file=item.get('file', ''),
                            mp3_url=item.get('mp3_url'),
                        )
                    )
                sections.append(
                    AudioCatalogSection(
                        idx=sec['idx'],
                        title=sec['title'],
                        dir=sec['dir'],
                        items=audio_items,
                    )
                )

            catalog = AudioCatalog(
                id=self.id,
                title=self.title,
                cover=cover_url,
                cover_file=cover_file,
                sections=sections,
            )
            catalog.save(self.dir_path / 'catalog.json')

            return True
        except Exception as e:
            logger.error(f'Setup failed: {e}')
            return False

    def get_download_items(self) -> list[tuple[AudioVolume, AudioChapter]]:
        catalog = self._load_catalog()
        items = []
        for sec in catalog.sections:
            chapters = []
            for item in sec.items:
                chapters.append(
                    AudioChapter(
                        idx=item.idx,
                        title=item.title,
                        url=item.url,
                        fetcher=self.fetcher,
                        mp3_url=item.mp3_url,
                    )
                )
            volume = AudioVolume(sec.idx, sec.title, chapters)
            for chapter in chapters:
                items.append((volume, chapter))
        return items

    def download(self, ext: str = 'mp3', item_prefix: str = 'item'):
        items = self.get_download_items()
        if not items:
            logger.error('没有可下载的内容')
            return

        skip_count = 0
        to_download: list[tuple[AudioVolume, AudioChapter]] = []
        for volume, chapter in items:
            safe_section = _sanitize_filename(volume.title)
            section_dir = self.dir_path / f'sec_{volume.idx:03d}_{safe_section}'
            safe_title = _sanitize_filename(chapter.title)
            filename = (
                f'{item_prefix}_{chapter.idx:03d}_{safe_title}.{ext}'
                if safe_title
                else f'{item_prefix}_{chapter.idx:03d}.{ext}'
            )
            save_path = section_dir / filename
            if save_path.exists():
                skip_count += 1
                continue
            to_download.append((volume, chapter))

        if skip_count:
            logger.bind(force=True).info(f'跳过已下载: {skip_count} 项')

        if not to_download:
            logger.bind(force=True).info('所有内容已下载完成')
            return self.dir_path

        asyncio.run(self._download_async(to_download, item_prefix, ext))

        logger.bind(force=True).info(f'保存到 {self.dir_path}')
        return self.dir_path

    async def _download_async(
        self,
        to_download: list[tuple[AudioVolume, AudioChapter]],
        item_prefix: str,
        ext: str,
    ):
        total = len(to_download)
        logger.bind(force=True).info(f'共 {total} 项待下载')

        semaphore = asyncio.Semaphore(WORKERS_AUDIO_CHAPTER)
        lock = asyncio.Lock()
        counter = {'done': 0, 'failed': 0}

        connector = aiohttp.TCPConnector(limit=WORKERS_AUDIO_CHAPTER, ttl_dns_cache=300)
        timeout = aiohttp.ClientTimeout(total=300, connect=30)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            tasks = []
            for volume, chapter in to_download:
                safe_section = _sanitize_filename(volume.title)
                section_dir = self.dir_path / f'sec_{volume.idx:03d}_{safe_section}'
                safe_title = _sanitize_filename(chapter.title)
                filename = (
                    f'{item_prefix}_{chapter.idx:03d}_{safe_title}.{ext}'
                    if safe_title
                    else f'{item_prefix}_{chapter.idx:03d}.{ext}'
                )
                save_path = section_dir / filename
                tasks.append(chapter.download_async(save_path, session, semaphore, lock, counter, total))

            await asyncio.gather(*tasks)

        if counter['failed']:
            logger.bind(force=True).warning(
                f'下载完成: {total - counter["failed"]}/{total} 成功, {counter["failed"]} 失败'
            )
        else:
            logger.bind(force=True).info(f'全部下载完成: {total}/{total}')
