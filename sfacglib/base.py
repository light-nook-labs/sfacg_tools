import threading
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from loguru import logger
from tqdm import tqdm

from .config import DEFAULT_DOWNLOAD_DIR, WORKERS_CHAPTER
from .fetcher import Fetcher
from .models import Catalog, CatalogItem, CatalogSection
from .progress import ProgressTracker, _extract_id
from .utils import sanitize_filename as _sanitize_filename


class AntiScrapingError(Exception):
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

    def download(
        self,
        dir_path: Path,
        ext: str,
        item_prefix: str = 'item',
        pbar=None,
        lock=None,
        executor: ThreadPoolExecutor | None = None,
        tracker: ProgressTracker | None = None,
        task_id: str = '',
    ) -> CatalogSection:
        section_dir = dir_path / f'sec_{self.idx:03d}_{_sanitize_filename(self.title)}'
        section_dir.mkdir(parents=True, exist_ok=True)

        items = self.get_items()

        def _download_one(item):
            safe_title = _sanitize_filename(item.title)
            if safe_title:
                filename = f'{item_prefix}_{item.idx:03d}_{safe_title}.{ext}'
            else:
                filename = f'{item_prefix}_{item.idx:03d}.md'
            save_path = section_dir / filename
            try:
                item.download(save_path, pbar, lock)
                if tracker and task_id:
                    tracker.mark_done(task_id, item.url, str(save_path.relative_to(dir_path)))
                return CatalogItem(
                    idx=item.idx,
                    title=item.title,
                    url=item.url,
                    file=str(save_path.relative_to(dir_path)),
                )
            except Exception as e:
                logger.error(f'Failed: {item.title} - {e}')
                if tracker and task_id:
                    tracker.mark_failed(task_id, item.url, str(e))
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

        return CatalogSection(
            idx=self.idx,
            title=self.title,
            dir=section_dir.name,
            items=catalog_items,
        )


class Container(ABC):
    def __init__(self, output_dir: str | Path | None = None, fetcher: Fetcher | None = None):
        self.fetcher = fetcher or Fetcher()
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_DOWNLOAD_DIR
        self.id: str = ''
        self.title: str = ''
        self.author: str = ''
        self.intro: str = ''
        self.cover: str = ''
        self.dir_path: Path = Path()
        self.tracker: ProgressTracker | None = None

    def _setup(self):
        self.dir_path = self.output_dir / _sanitize_filename(self.title)
        self.dir_path.mkdir(parents=True, exist_ok=True)
        self.tracker = ProgressTracker(self.dir_path / 'progress.db')

        info_md, info_html = self.get_info()
        if info_html:
            (self.dir_path / 'info.html').write_text(info_html, encoding='utf-8')
        if info_md:
            (self.dir_path / 'info.md').write_text(info_md, encoding='utf-8')

        catalog = Catalog(
            id=self.id,
            title=self.title,
            author=self.author,
            cover=self.cover,
            intro=self.intro,
        )
        catalog.save(self.dir_path / 'catalog.json')

    def get_info(self) -> tuple[str, str]:
        return '', ''

    def get_sections(self) -> list[Section]:
        return []

    @abstractmethod
    def _download_item(self, item: Item, save_path: Path, pbar=None, lock=None): ...

    def _filter_items(
        self,
        sections: list[Section],
        start: str | None = None,
        end: str | None = None,
        range_str: str | None = None,
        filter_str: str | None = None,
    ) -> list[tuple[Section, Item]]:
        all_items: list[tuple[Section, Item]] = []
        for section in sections:
            for item in section.get_items():
                all_items.append((section, item))

        if filter_str:
            names = {v.strip() for v in filter_str.split(',')}
            all_items = [(s, i) for s, i in all_items if s.title in names]

        if start:
            found = False
            filtered = []
            for idx, (s, i) in enumerate(all_items):
                if i.title == start or _extract_id(i.url) == start or str(idx + 1) == start:
                    found = True
                if found:
                    filtered.append((s, i))
            if not found:
                logger.warning(f'起始章节未找到: {start}')
            all_items = filtered

        if end:
            filtered = []
            found = False
            for idx, (s, i) in enumerate(all_items):
                filtered.append((s, i))
                if i.title == end or _extract_id(i.url) == end or str(idx + 1) == end:
                    found = True
                    break
            if not found:
                logger.warning(f'结束章节未找到: {end}')
            all_items = filtered

        if range_str:
            ids: set[str] = set()
            is_index = False
            for part in range_str.split(','):
                part = part.strip()
                if '-' in part and not part.startswith('-'):
                    s, e = part.split('-', 1)
                    try:
                        s_int, e_int = int(s), int(e)
                        if all(0 < x <= len(all_items) for x in (s_int, e_int)):
                            is_index = True
                        for i in range(s_int, e_int + 1):
                            ids.add(str(i))
                    except ValueError:
                        ids.add(part)
                else:
                    try:
                        val = int(part)
                        ids.add(str(val))
                        if 0 < val <= len(all_items):
                            is_index = True
                    except ValueError:
                        ids.add(part)

            if is_index:
                total = len(all_items)
                filtered = []
                for idx, (s, i) in enumerate(all_items):
                    pos = idx + 1
                    neg_pos = idx - total
                    if str(pos) in ids or str(neg_pos) in ids:
                        filtered.append((s, i))
                all_items = filtered
            else:
                filtered = []
                for s, i in all_items:
                    cid = _extract_id(i.url)
                    if cid in ids or i.title in ids:
                        filtered.append((s, i))
                all_items = filtered

        return all_items

    def _filter_sections(
        self,
        sections: list[Section],
        start: str | None = None,
        end: str | None = None,
        range_str: str | None = None,
        filter_str: str | None = None,
    ) -> list[Section]:
        filtered_items = self._filter_items(sections, start, end, range_str, filter_str)

        seen_sections: list[Section] = []
        seen_ids: set[int] = set()
        for s, _ in filtered_items:
            if s.idx not in seen_ids:
                seen_sections.append(s)
                seen_ids.add(s.idx)

        return seen_sections

    def download(
        self,
        start: str | None = None,
        end: str | None = None,
        range_str: str | None = None,
        filter_str: str | None = None,
    ):
        sections = self.get_sections()
        filtered_sections = self._filter_sections(sections, start, end, range_str, filter_str)
        all_items = self._filter_items(sections, start, end, range_str, filter_str)

        if not all_items:
            logger.error('没有可下载的内容')
            return

        skip_count = 0
        to_download: list[tuple[Section, Item]] = []
        for section, item in all_items:
            safe_section = _sanitize_filename(section.title)
            section_dir = self.dir_path / f'sec_{section.idx:03d}_{safe_section}'
            safe_title = _sanitize_filename(item.title)
            if safe_title:
                filename = f'item_{item.idx:03d}_{safe_title}.md'
            else:
                filename = f'item_{item.idx:03d}.md'
            save_path = section_dir / filename

            if save_path.exists():
                skip_count += 1
                continue
            to_download.append((section, item))

        if skip_count:
            logger.bind(force=True).info(f'跳过已下载: {skip_count} 项')

        if not to_download:
            logger.bind(force=True).info('所有内容已下载完成')
            self._save_catalog(sections, all_items)
            return self.dir_path

        task_id = f'{self.__class__.__name__.lower()}_{self.id}'
        self.tracker.create_task(
            self.__class__.__name__.lower(),
            self.title,
            self.id,
            '',
            chapters=[{'url': i.url, 'title': i.title} for _, i in to_download],
        )

        lock = threading.Lock()
        pbar = tqdm(total=len(to_download), desc=self.title, unit='item')

        anti_scraping = None

        logger.bind(force=True).info(f'共 {len(to_download)} 项待下载')

        section_items: dict[int, list[Item]] = {}
        for section, item in to_download:
            section_items.setdefault(section.idx, []).append(item)

        section_map = {s.idx: s for s in filtered_sections}

        with ThreadPoolExecutor(max_workers=WORKERS_CHAPTER) as executor:

            def _download_section(sec_idx):
                section = section_map[sec_idx]
                section.download(
                    self.dir_path,
                    ext='md',
                    pbar=pbar,
                    lock=lock,
                    executor=executor,
                    tracker=self.tracker,
                    task_id=task_id,
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

        self._save_catalog(sections, all_items)
        self.tracker.finalize_task(task_id)

        logger.bind(force=True).info(f'保存到 {self.dir_path}')
        return self.dir_path

    def _save_catalog(self, sections, all_items):
        catalog = Catalog.from_sections(
            id=self.id,
            title=self.title,
            sections=[s for s in sections if any(si is s for si, _ in all_items)],
            author=self.author,
            cover=self.cover,
            intro=self.intro,
        )
        catalog.save(self.dir_path / 'catalog.json')

    def assemble(self, dir_path: Path) -> str:
        catalog = Catalog.load(dir_path / 'catalog.json')
        parts = []

        info_path = dir_path / 'info.md'
        if info_path.exists():
            parts.append(info_path.read_text(encoding='utf-8'))

        for section in catalog.sections:
            if section.title:
                parts.append(f'## {section.title}')
            for item in section.items:
                item_path = dir_path / item.file
                if item_path.exists():
                    parts.append(item_path.read_text(encoding='utf-8'))

        return '\n\n'.join(parts)
