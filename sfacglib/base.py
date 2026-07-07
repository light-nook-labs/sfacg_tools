import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from loguru import logger
from tqdm import tqdm

from .config import DEFAULT_DOWNLOAD_DIR, WORKERS_CHAPTER
from .fetcher import Fetcher
from .utils import load_json
from .utils import sanitize_filename as _sanitize_filename


class AntiScrapingError(Exception):
    pass


class InvalidNovelError(Exception):
    pass


class Item(ABC):
    def __init__(self, idx: int, title: str, url: str):
        self.idx = idx
        self.title = title
        self.url = url

    @abstractmethod
    def download(self, save_path: Path, pbar=None, lock=None): ...

    def to_dict(self) -> dict:
        return {'idx': self.idx, 'title': self.title, 'url': self.url}


class Section(ABC):
    def __init__(self, idx: int, title: str):
        self.idx = idx
        self.title = title

    @abstractmethod
    def get_items(self) -> list[Item]: ...

    def to_dict(self) -> dict:
        return {'idx': self.idx, 'title': self.title}

    def create_chapter(self, idx: int) -> Item | None:
        for item in self.get_items():
            if item.idx == idx:
                return item
        return None

    def download(
        self,
        dir_path: Path,
        ext: str,
        item_prefix: str = 'item',
        pbar=None,
        lock=None,
        executor: ThreadPoolExecutor | None = None,
    ):
        dir_name = getattr(self, 'dir_name', None) or f'sec_{self.idx:03d}_{_sanitize_filename(self.title)}'
        section_dir = dir_path / dir_name
        section_dir.mkdir(parents=True, exist_ok=True)

        items = self.get_items()

        def _download_one(item):
            safe_title = _sanitize_filename(item.title)
            if safe_title:
                filename = f'{item_prefix}_{item.idx:03d}_{safe_title}.{ext}'
            else:
                filename = f'{item_prefix}_{item.idx:03d}.{ext}'
            save_path = section_dir / filename
            try:
                item.download(save_path, pbar, lock)
                return {
                    'idx': item.idx,
                    'title': item.title,
                    'file': str(save_path.relative_to(dir_path)),
                }
            except Exception as e:
                logger.error(f'Failed: {item.title} - {e}')
                if pbar and lock:
                    with lock:
                        pbar.update(1)
                return None

        if executor:
            futures = {executor.submit(_download_one, item): item for item in items}
            catalog_items = []
            for future in as_completed(futures):
                result = future.result()
                if result:
                    catalog_items.append(result)
        else:
            catalog_items = []
            for item in items:
                result = _download_one(item)
                if result:
                    catalog_items.append(result)

        return {
            'idx': self.idx,
            'title': self.title,
            'dir': section_dir.name,
            'items': catalog_items,
        }


class Container(ABC):
    def __init__(self, output_dir: str | Path | None = None, fetcher: Fetcher | None = None):
        self.fetcher = fetcher or Fetcher()
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_DOWNLOAD_DIR
        self.id: str = ''
        self.title: str = ''
        self.author: str = ''
        self.cover: str = ''
        self.dir_path: Path = Path()

    def _download_cover(self) -> str:
        """下载封面图片到本地，返回本地文件名。"""
        if not self.cover or not self.dir_path:
            return ''
        try:
            cover_data = self.fetcher.get_binary(self.cover)
            from io import BytesIO

            from PIL import Image

            img = Image.open(BytesIO(cover_data))
            fmt = img.format or 'JPEG'
            ext = '.' + fmt.lower()
            if ext == '.jpeg':
                ext = '.jpg'
            cover_path = self.dir_path / f'cover{ext}'
            img.save(cover_path)
            return cover_path.name
        except Exception as e:
            logger.warning(f'封面下载失败: {e}')
            return ''

    @abstractmethod
    def setup(self) -> bool:
        """初始化：创建目录 + 获取元信息 + 生成 catalog.json。成功返回 True。"""
        ...

    @abstractmethod
    def get_download_items(self) -> list[tuple[Section, Item]]:
        """从 catalog.json 重建对象"""
        ...

    def download(self, ext: str = 'md', item_prefix: str = 'item', workers: int = WORKERS_CHAPTER):
        items = self.get_download_items()

        if not items:
            logger.error('没有可下载的内容')
            return

        skip_count = 0
        to_download: list[tuple[Section | None, Item]] = []
        for section, item in items:
            if section is None:
                safe_title = _sanitize_filename(item.title)
                if safe_title:
                    filename = f'{item_prefix}_{item.idx:03d}_{safe_title}.{ext}'
                else:
                    filename = f'{item_prefix}_{item.idx:03d}.{ext}'
                save_path = self.dir_path / filename
            else:
                safe_section = _sanitize_filename(section.title)
                section_dir = self.dir_path / f'sec_{section.idx:03d}_{safe_section}'
                safe_title = _sanitize_filename(item.title)
                if safe_title:
                    filename = f'{item_prefix}_{item.idx:03d}_{safe_title}.{ext}'
                else:
                    filename = f'{item_prefix}_{item.idx:03d}.{ext}'
                save_path = section_dir / filename

            if save_path.exists():
                skip_count += 1
                continue
            to_download.append((section, item))

        if skip_count:
            logger.bind(force=True).info(f'跳过已下载: {skip_count} 项')

        if not to_download:
            logger.bind(force=True).info('所有内容已下载完成')
            return self.dir_path

        lock = threading.Lock()
        pbar = tqdm(total=len(to_download), desc=self.title, unit='item')

        anti_scraping = None

        logger.bind(force=True).info(f'共 {len(to_download)} 项待下载')

        section_items: dict[int, list[Item]] = {}
        for section, item in to_download:
            if section is not None:
                section_items.setdefault(section.idx, []).append(item)

        section_map = {s.idx: s for s, _ in items if s is not None}

        with ThreadPoolExecutor(max_workers=workers) as executor:

            def _download_section(sec_idx):
                section = section_map[sec_idx]
                section.download(
                    self.dir_path,
                    ext=ext,
                    item_prefix=item_prefix,
                    pbar=pbar,
                    lock=lock,
                    executor=executor,
                )

            section_futures = {executor.submit(_download_section, idx): idx for idx in section_items}

            for future in as_completed(section_futures):
                try:
                    future.result()
                except AntiScrapingError as e:
                    logger.error(f'反爬检测，停止所有下载: {e}')
                    anti_scraping = e
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                except Exception as e:
                    logger.error(f'Failed section: {e}')

        pbar.close()

        if anti_scraping:
            raise anti_scraping

        logger.bind(force=True).info(f'保存到 {self.dir_path}')
        return self.dir_path

    def assemble(self) -> str:
        catalog = self._load_catalog()
        parts = []

        info_path = self.dir_path / catalog.get('info_file', 'info.md')
        if info_path.exists():
            parts.append(info_path.read_text(encoding='utf-8'))

        for section in catalog.get('sections', []):
            if section.get('title'):
                parts.append(f'## {section["title"]}')
            for item in section.get('items', []):
                if not item.get('file'):
                    continue
                item_path = self.dir_path / item['file']
                if item_path.exists():
                    parts.append(item_path.read_text(encoding='utf-8'))

        return '\n\n'.join(parts)

    def _load_catalog(self) -> dict:
        return load_json(self.dir_path / 'catalog.json')
