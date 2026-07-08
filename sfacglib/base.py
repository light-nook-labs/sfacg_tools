import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from loguru import logger
from tqdm import tqdm

from .config import DEFAULT_DOWNLOAD_DIR, WORKERS_CHAPTER
from .fetcher import Fetcher
from .models.catalog import Catalog
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
        self.dir_name = f'sec_{idx:03d}_{_sanitize_filename(title)}'

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
        ext: str = 'md',
        item_prefix: str = 'item',
    ):
        section_dir = dir_path / self.dir_name
        section_dir.mkdir(parents=True, exist_ok=True)

        items = self.get_items()
        lock = threading.Lock()
        pbar = tqdm(total=len(items), desc=self.title, unit='item')

        for item in items:
            safe_title = _sanitize_filename(item.title)
            filename = (
                f'{item_prefix}_{item.idx:03d}_{safe_title}.{ext}'
                if safe_title
                else f'{item_prefix}_{item.idx:03d}.{ext}'
            )
            save_path = section_dir / filename
            try:
                item.download(save_path, pbar, lock)
            except Exception as e:
                logger.error(f'Failed: {item.title} - {e}')
                with lock:
                    pbar.update(1)

        pbar.close()
        return section_dir


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
    def setup(self) -> bool: ...

    @abstractmethod
    def get_download_items(self) -> list[tuple[Section | None, Item]]: ...

    def _load_catalog(self) -> Catalog:
        return Catalog.load(self.dir_path / 'catalog.json')

    def _compute_save_path(self, section, item, ext: str, item_prefix: str) -> Path:
        if section is None:
            safe_title = _sanitize_filename(item.title)
            filename = (
                f'{item_prefix}_{item.idx:03d}_{safe_title}.{ext}'
                if safe_title
                else f'{item_prefix}_{item.idx:03d}.{ext}'
            )
            return self.dir_path / filename

        dir_name = (
            getattr(section, 'dir_name', None)
            or getattr(section, 'dir', None)
            or f'sec_{section.idx:03d}_{_sanitize_filename(section.title)}'
        )
        section_dir = self.dir_path / dir_name
        safe_title = _sanitize_filename(item.title)
        filename = (
            f'{item_prefix}_{item.idx:03d}_{safe_title}.{ext}' if safe_title else f'{item_prefix}_{item.idx:03d}.{ext}'
        )
        return section_dir / filename

    def download(self, ext: str = 'md', item_prefix: str = 'item', workers: int = WORKERS_CHAPTER):
        items = self.get_download_items()

        if not items:
            logger.error('没有可下载的内容')
            return

        skip_count = 0
        to_download: list[tuple[Path, Item]] = []
        for section, item in items:
            save_path = self._compute_save_path(section, item, ext, item_prefix)
            if save_path.exists():
                skip_count += 1
                continue
            to_download.append((save_path, item))

        if skip_count:
            logger.bind(force=True).info(f'跳过已下载: {skip_count} 项')

        if not to_download:
            logger.bind(force=True).info('所有内容已下载完成')
            return self.dir_path

        lock = threading.Lock()
        pbar = tqdm(total=len(to_download), desc=self.title, unit='item')

        anti_scraping = None

        logger.bind(force=True).info(f'共 {len(to_download)} 项待下载')

        with ThreadPoolExecutor(max_workers=workers) as executor:

            def _download_one(save_path: Path, item: Item):
                try:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    item.download(save_path, pbar, lock)
                    return True
                except AntiScrapingError:
                    raise
                except Exception as e:
                    logger.error(f'Failed: {item.title} - {e}')
                    with lock:
                        pbar.update(1)
                    return False

            futures = {executor.submit(_download_one, sp, it): it for sp, it in to_download}

            for future in as_completed(futures):
                try:
                    future.result()
                except AntiScrapingError as e:
                    logger.error(f'反爬检测，停止所有下载: {e}')
                    anti_scraping = e
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                except Exception as e:
                    logger.error(f'Failed: {e}')

        pbar.close()

        if anti_scraping:
            raise anti_scraping

        logger.bind(force=True).info(f'保存到 {self.dir_path}')
        return self.dir_path

    def assemble(self) -> str:
        catalog = self._load_catalog()
        parts = []

        info_path = self.dir_path / catalog.info_file
        if info_path.exists():
            parts.append(info_path.read_text(encoding='utf-8'))

        for section in catalog.sections:
            if section.title:
                parts.append(f'## {section.title}')
            for item in section.items:
                if not item.file:
                    continue
                item_path = self.dir_path / item.file
                if item_path.exists():
                    parts.append(item_path.read_text(encoding='utf-8'))

        return '\n\n'.join(parts)
