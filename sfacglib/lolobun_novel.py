import re
from pathlib import Path

from bs4 import BeautifulSoup
from loguru import logger
from tqdm import tqdm

from .base import Container, InvalidNovelError, Item, Section
from .config import API_LOLOBUN, LOLOBUN_BASE
from .fetcher import Fetcher
from .models.catalog import LoLoBunNovelCatalog, LoLoBunNovelCatalogItem, LoLoBunNovelCatalogSection
from .utils import sanitize_filename as _sanitize_filename


class LoLoBunNovelChapter(Item):
    def __init__(
        self,
        idx: int,
        title: str,
        chapter_id: str,
        fetcher: Fetcher,
        novel_id: str,
    ):
        url = f'{LOLOBUN_BASE}/n/{novel_id}/{chapter_id}'
        super().__init__(idx, title, url)
        self.chapter_id = chapter_id
        self.fetcher = fetcher
        self.novel_id = novel_id

    def download(self, save_path: Path, pbar=None, lock=None):
        if save_path.exists():
            logger.debug(f'Skip existing: {save_path.name}')
        else:
            self._download_normal(save_path)
        if pbar and lock:
            with lock:
                pbar.update(1)

    def _download_normal(self, save_path: Path):
        md = self.get_chapter_content()
        save_path.write_text(md, encoding='utf-8')

    def get_chapter_content(self) -> str:
        html = self.fetcher.get_html(self.url)
        soup = BeautifulSoup(html, 'html.parser')

        title_tag = soup.select_one('h1, .chapter-title, [class*="title"]')
        title = title_tag.get_text().strip() if title_tag else self.title

        paragraphs = soup.select('p, .paragraph, [class*="paragraph"]')
        content_parts = []
        for p in paragraphs:
            text = p.get_text().strip()
            if text and len(text) > 1:
                content_parts.append(text)

        content = '\n\n'.join(content_parts)
        return f'### {title}\n\n{content}\n'


class LoLoBunNovelVolume(Section):
    def __init__(self, idx: int, title: str, chapters: list[LoLoBunNovelChapter]):
        super().__init__(idx, title)
        self.chapters = chapters
        self.dir_name = ''

    def get_items(self) -> list[LoLoBunNovelChapter]:
        return self.chapters

    def download(
        self,
        dir_path: Path,
        ext: str = 'md',
        item_prefix: str = 'ch',
    ):
        items = self.get_items()
        lock = __import__('threading').Lock()
        pbar = tqdm(total=len(items), desc=self.title, unit='item')

        for item in items:
            safe_title = _sanitize_filename(item.title)
            filename = f'{item_prefix}_{item.idx:03d}_{safe_title}.{ext}'
            save_path = dir_path / filename
            try:
                item.download(save_path, pbar, lock)
            except Exception as e:
                logger.error(f'Failed: {item.title} - {e}')
                with lock:
                    pbar.update(1)

        pbar.close()
        return dir_path


class LoLoBunNovel(Container):
    def __init__(
        self,
        nid: int | str,
        output_dir: str | Path | None = None,
        fetcher: Fetcher | None = None,
    ):
        super().__init__(output_dir, fetcher)
        self.nid = str(nid)
        self.id = str(nid)
        self.url = f'{LOLOBUN_BASE}/n/{self.nid}'

        if not self.setup():
            raise InvalidNovelError(f'HTTP错误或URL无效 (nid={nid})')

    def __repr__(self):
        return f'<LoLoBunNovel: {self.nid}>'

    def _load_catalog(self) -> LoLoBunNovelCatalog:
        return LoLoBunNovelCatalog.load(self.dir_path / 'catalog.json')

    def _get_novel_info_from_api(self) -> dict:
        try:
            resp = self.fetcher.get(
                API_LOLOBUN,
                params={'op': 'searchWorks', 'q': self.title, 'type': 'novel', 'pi': '0'},
                headers={'Referer': f'{LOLOBUN_BASE}/'},
            )
            data = resp.json()
            if isinstance(data, dict) and data.get('status', {}).get('errorCode') == 200:
                items = data.get('data', {}).get('Items', [])
                for item in items:
                    if str(item.get('EntityId', '')) == self.nid:
                        cover_path = item.get('Cover', '')
                        if cover_path:
                            cover_url = f'https://osrs.sfacg.com/web/novel/images/NovelCover/Big/{cover_path}'
                        else:
                            cover_url = ''
                        return {
                            'author': item.get('AuthorName', ''),
                            'intro': item.get('Intro', ''),
                            'cover': cover_url,
                        }
            return {}
        except Exception as e:
            logger.warning(f'Failed to get novel info from API: {e}')
            return {}

    def setup(self) -> bool:
        try:
            html = self.fetcher.get_html(self.url)
            soup = BeautifulSoup(html, 'html.parser')

            title_tag = soup.select_one('.share-work-title, h1, .title')
            if title_tag:
                title_text = title_tag.get_text().strip()
                if title_text and title_text != 'Summary':
                    self.title = title_text
                else:
                    meta_tag = soup.find('meta', attrs={'property': 'og:title'})
                    if meta_tag:
                        self.title = meta_tag.get('content', 'Unknown Novel').strip()
                    else:
                        self.title = 'Unknown Novel'
            else:
                meta_tag = soup.find('meta', attrs={'property': 'og:title'})
                if meta_tag:
                    self.title = meta_tag.get('content', 'Unknown Novel').strip()
                else:
                    self.title = 'Unknown Novel'

            cover_tag = soup.select_one('img[src*="sfacg.com"]')
            self.cover = cover_tag.get('src', '') if cover_tag else ''

            api_info = self._get_novel_info_from_api()
            self.author = api_info.get('author', 'Unknown')
            self.intro = api_info.get('intro', '')
            if api_info.get('cover'):
                self.cover = api_info['cover']

            self.dir_path = self.output_dir / _sanitize_filename(self.title)
            self.dir_path.mkdir(parents=True, exist_ok=True)

            cover_file = self._download_cover()

            chapter_links = soup.select('a[href*="/n/' + self.nid + '/"]')
            chapters = []
            seen_ids = set()

            for link in chapter_links:
                href = link.get('href', '')
                match = re.search(r'/n/\d+/(\d+)', href)
                if not match:
                    continue

                chapter_id = match.group(1)
                if chapter_id in seen_ids:
                    continue
                seen_ids.add(chapter_id)

                chapter_title = link.get_text().strip()
                if not chapter_title or chapter_title in ('Read On', 'Previous episode', 'Next episode'):
                    continue

                chapters.append(
                    {
                        'chapter_id': chapter_id,
                        'title': chapter_title,
                    }
                )

            items = []
            for idx, ch in enumerate(chapters):
                items.append(
                    LoLoBunNovelCatalogItem(
                        idx=idx + 1,
                        title=ch['title'],
                        chapter_id=ch['chapter_id'],
                        file=f'ch_{idx + 1:03d}_{_sanitize_filename(ch["title"])}.md',
                    )
                )

            catalog = LoLoBunNovelCatalog(
                id=self.id,
                title=self.title,
                author=self.author,
                cover=self.cover,
                cover_file=cover_file,
                info_file='info.md',
                sections=[
                    LoLoBunNovelCatalogSection(
                        idx=1,
                        title='Chapters',
                        items=items,
                    )
                ],
            )
            catalog.save(self.dir_path / 'catalog.json')

            info_md = f"""# {self.title} - {self.author}

## Novel Info

Source: {self.url}

Author: {self.author}

{self.intro}

{'=' * 20}
"""
            (self.dir_path / 'info.md').write_text(info_md, encoding='utf-8')

            return True
        except Exception as e:
            logger.error(f'Setup failed: {e}')
            return False

    def get_download_items(self) -> list[tuple[LoLoBunNovelVolume, LoLoBunNovelChapter]]:
        catalog = self._load_catalog()
        items = []
        for sec in catalog.sections:
            chapters = []
            for item in sec.items:
                chapters.append(
                    LoLoBunNovelChapter(
                        idx=item.idx,
                        title=item.title,
                        chapter_id=item.chapter_id,
                        fetcher=self.fetcher,
                        novel_id=self.nid,
                    )
                )
            volume = LoLoBunNovelVolume(sec.idx, sec.title, chapters)
            for chapter in chapters:
                items.append((volume, chapter))
        return items

    def _compute_save_path(self, section, item, ext: str, item_prefix: str) -> Path:
        safe_title = _sanitize_filename(item.title)
        filename = f'{item_prefix}_{item.idx:03d}_{safe_title}.{ext}'
        return self.dir_path / filename

    def download(self, ext: str = 'md'):
        super().download(ext=ext, item_prefix='ch')
