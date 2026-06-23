import json
import threading
from pathlib import Path
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from loguru import logger
from .fetcher import Fetcher
from .config import WORKERS_CHAPTER
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
    def download(self, save_path: Path, pbar=None, lock=None):
        ...

    def to_dict(self) -> dict:
        return {'idx': self.idx, 'title': self.title, 'url': self.url}


class Section(ABC):

    def __init__(self, idx: int, title: str):
        self.idx = idx
        self.title = title

    @abstractmethod
    def get_items(self) -> list[Item]:
        ...

    def to_dict(self) -> dict:
        return {'idx': self.idx, 'title': self.title}


class Container(ABC):

    def __init__(self, fetcher: Fetcher | None = None):
        self.fetcher = fetcher or Fetcher()
        self.title: str = ''
        self.id: str = ''

    @abstractmethod
    def get_info(self) -> tuple[str, str]:
        ...

    @abstractmethod
    def get_sections(self) -> list[Section]:
        ...

    def _filter_sections(
        self,
        sections: list[Section],
        start: str | None = None,
        end: str | None = None,
        range_str: str | None = None,
        filter_str: str | None = None,
    ) -> list[Section]:
        all_items = []
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
            all_items = filtered

        if end:
            filtered = []
            for idx, (s, i) in enumerate(all_items):
                filtered.append((s, i))
                if i.title == end or _extract_id(i.url) == end or str(idx + 1) == end:
                    break
            all_items = filtered

        if range_str:
            ids = set()
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

        seen_sections = []
        seen_ids = set()
        for s, _ in all_items:
            if s.idx not in seen_ids:
                seen_sections.append(s)
                seen_ids.add(s.idx)

        return seen_sections

    def _download_items(
        self,
        items: list[tuple[Section, Item]],
        dir_path: Path,
        ext: str,
        section_prefix: str = 'sec',
        item_prefix: str = 'item',
        pbar=None,
        lock=None,
        tracker: ProgressTracker | None = None,
        task_id: str | None = None,
    ) -> list[dict]:
        has_tracker = tracker and task_id
        pending_cids = None
        if has_tracker:
            pending = tracker.get_pending(task_id)
            pending_cids = set(ch['cid'] for ch in pending)

        catalog_items = []

        with ThreadPoolExecutor(max_workers=WORKERS_CHAPTER) as executor:
            futures = {}
            for section, item in items:
                item_cid = _extract_id(item.url)
                if has_tracker and pending_cids is not None and item_cid not in pending_cids:
                    continue
                safe_section = _sanitize_filename(section.title)
                section_dir = dir_path / f'{section_prefix}_{section.idx:03d}_{safe_section}'
                section_dir.mkdir(exist_ok=True)
                safe_title = _sanitize_filename(item.title)
                if safe_title:
                    filename = f'{item_prefix}_{item.idx:03d}_{safe_title}.{ext}'
                else:
                    filename = f'{item_prefix}_{item.idx:03d}.{ext}'
                save_path = section_dir / filename
                futures[executor.submit(item.download, save_path, pbar, lock)] = (section, item, save_path)

            anti_scraping = None
            for future in as_completed(futures):
                section, item, save_path = futures[future]
                try:
                    future.result()
                    if tracker and task_id:
                        tracker.mark_done(task_id, item.url)
                    catalog_items.append({
                        'section_idx': section.idx,
                        'section_title': section.title,
                        'item_idx': item.idx,
                        'item_title': item.title,
                        'item_url': item.url,
                        'file': str(save_path.relative_to(dir_path)),
                    })
                except AntiScrapingError as e:
                    logger.error(f'反爬检测，停止所有下载: {e}')
                    anti_scraping = e
                    if tracker and task_id:
                        tracker.mark_failed(task_id, item.url, str(e))
                    if pbar and lock:
                        with lock:
                            pbar.update(1)
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
                except Exception as e:
                    logger.error(f'Failed: {item.title} - {e}')
                    if tracker and task_id:
                        tracker.mark_failed(task_id, item.url, str(e))
                    if pbar and lock:
                        with lock:
                            pbar.update(1)

            if anti_scraping:
                if catalog_items:
                    logger.warning(f'反爬检测，已下载 {len(catalog_items)} 项，保存部分结果')
                raise anti_scraping

        return sorted(catalog_items, key=lambda x: (x['section_idx'], x['item_idx']))

    def download(
        self,
        path: str | Path = './',
        ext: str = 'md',
        tracker: ProgressTracker | None = None,
        start: str | None = None,
        end: str | None = None,
        range_str: str | None = None,
        filter_str: str | None = None,
    ):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        info_md, info_html = self.get_info()
        sections = self.get_sections()
        sections = self._filter_sections(sections, start, end, range_str, filter_str)

        all_items = []
        for section in sections:
            for item in section.get_items():
                all_items.append((section, item))

        if not all_items:
            logger.error('没有可下载的内容')
            return

        logger.bind(force=True).info(f'共 {len(all_items)} 项待下载')

        item_list = [{'url': i.url, 'title': i.title} for _, i in all_items]
        task_id = tracker.create_task(
            self.__class__.__name__.lower(), self.title, self.id, '', chapters=item_list
        ) if tracker else None

        dir_path = path / _sanitize_filename(self.title)
        dir_path.mkdir(parents=True, exist_ok=True)

        lock = threading.Lock()
        pbar = tqdm(total=len(all_items), desc=self.title, unit='item')

        catalog = {
            'id': self.id,
            'title': self.title,
            'info': info_md,
            'sections': [],
            'items': [],
        }

        catalog['items'] = self._download_items(
            all_items, dir_path, ext,
            pbar=pbar, lock=lock, tracker=tracker, task_id=task_id,
        )

        for section in sections:
            catalog['sections'].append({
                'idx': section.idx,
                'title': section.title,
            })

        pbar.close()

        (dir_path / 'catalog.json').write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

        if ext == 'html':
            (dir_path / 'info.html').write_text(info_html, encoding='utf-8')
        else:
            (dir_path / 'info.md').write_text(info_md, encoding='utf-8')

        if tracker and task_id:
            tracker.mark_task_done(task_id)
            pending = tracker.get_pending(task_id)
            if not pending:
                tracker.delete_task(task_id)
                logger.bind(force=True).info(f'任务完成，已清理记录: {task_id}')
            else:
                logger.warning(f'任务有 {len(pending)} 个失败项，保留记录')

        logger.bind(force=True).info(f'保存到 {dir_path}')
        return dir_path

    def assemble(self, dir_path: Path, ext: str = 'md') -> str:
        catalog = json.loads((dir_path / 'catalog.json').read_text(encoding='utf-8'))
        parts = []

        if ext == 'html':
            parts.append(f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{catalog['title']}</title></head>
<body>""")
            parts.append((dir_path / 'info.html').read_text(encoding='utf-8'))
        else:
            parts.append((dir_path / 'info.md').read_text(encoding='utf-8'))

        items_key = 'items' if 'items' in catalog else 'chapters'
        last_section_idx = None
        for item in catalog[items_key]:
            sec_idx = item.get('section_idx', 0)
            if sec_idx != last_section_idx:
                sec_title = item.get('section_title', '')
                if sec_title:
                    if ext == 'html':
                        parts.append(f'<h2>{sec_title}</h2>')
                    else:
                        parts.append(f'## {sec_title}')
                last_section_idx = sec_idx
            item_path = dir_path / item['file']
            if item_path.exists():
                parts.append(item_path.read_text(encoding='utf-8'))

        if ext == 'html':
            parts.append('</body></html>')

        return '\n\n'.join(parts) if ext != 'html' else '\n'.join(parts)
