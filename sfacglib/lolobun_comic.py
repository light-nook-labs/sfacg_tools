import re
from pathlib import Path

from bs4 import BeautifulSoup
from loguru import logger

from .base import Container, InvalidNovelError, Item, Section
from .config import API_LOLOBUN_COMIC, LOLOBUN_BASE
from .fetcher import Fetcher
from .models.catalog import LoLoBunComicCatalog, LoLoBunComicCatalogSection
from .utils import sanitize_filename as _sanitize_filename


class LoLoBunComicPage(Item):
    def __init__(self, idx: int, url: str, fetcher: Fetcher):
        super().__init__(idx, '', url)
        self.fetcher = fetcher
        self._data: bytes | None = None

    def download(self, save_path: Path, pbar=None, lock=None):
        headers = {'Referer': f'{LOLOBUN_BASE}/'}
        resp = self.fetcher.get(self.url, headers=headers)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(resp.content)
        self._data = resp.content
        if pbar and lock:
            with lock:
                pbar.update(1)

    def get_data(self) -> bytes:
        if self._data is None:
            headers = {'Referer': f'{LOLOBUN_BASE}/'}
            resp = self.fetcher.get(self.url, headers=headers)
            self._data = resp.content
        return self._data


class LoLoBunComicChapter(Section):
    def __init__(self, idx: int, title: str, chapter_id: str, fetcher: Fetcher, dir_name: str = ''):
        super().__init__(idx, title)
        self.chapter_id = chapter_id
        self.fetcher = fetcher
        if dir_name:
            self.dir_name = dir_name

    def get_image_urls(self) -> list[str]:
        try:
            resp = self.fetcher.post(
                API_LOLOBUN_COMIC,
                params={'op': 'getChapterPic'},
                data={'chapId': self.chapter_id},
                headers={'Referer': f'{LOLOBUN_BASE}/'},
            )
            data = resp.json()
            if isinstance(data, dict) and data.get('status', {}).get('errorCode') == 200:
                return data.get('data', [])
            return []
        except Exception as e:
            logger.error(f'Failed to get comic images: {e}')
            return []

    def get_items(self) -> list[LoLoBunComicPage]:
        urls = self.get_image_urls()
        pages = []
        for idx, url in enumerate(urls, start=1):
            pages.append(LoLoBunComicPage(idx, url, self.fetcher))
        return pages


class LoLoBunComic(Container):
    def __init__(
        self,
        cid: int | str,
        output_dir: str | Path | None = None,
        fetcher: Fetcher | None = None,
    ):
        super().__init__(output_dir, fetcher)
        self.cid = str(cid)
        self.id = str(cid)
        self.url = f'{LOLOBUN_BASE}/c/{self.cid}'

        if not self.setup():
            raise InvalidNovelError(f'HTTP错误或URL无效 (cid={cid})')

    def __repr__(self):
        return f'<LoLoBunComic: {self.cid}>'

    def _load_catalog(self) -> LoLoBunComicCatalog:
        return LoLoBunComicCatalog.load(self.dir_path / 'catalog.json')

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
                        self.title = meta_tag.get('content', 'Unknown Comic').strip()
                    else:
                        self.title = 'Unknown Comic'
            else:
                meta_tag = soup.find('meta', attrs={'property': 'og:title'})
                if meta_tag:
                    self.title = meta_tag.get('content', 'Unknown Comic').strip()
                else:
                    self.title = 'Unknown Comic'

            cover_tag = soup.select_one('img[src*="sfacg.com"]')
            self.cover = cover_tag.get('src', '') if cover_tag else ''

            author_tag = soup.select_one('.author, [class*="author"]')
            if author_tag:
                author_text = author_tag.get_text().strip()
                if author_text and author_text != 'Unknown':
                    self.author = author_text
                else:
                    self.author = 'Unknown'
            else:
                self.author = 'Unknown'

            intro_tag = soup.select_one('.summary, .description, [class*="summary"], [class*="description"]')
            self.intro = intro_tag.get_text().strip() if intro_tag else ''

            self.dir_path = self.output_dir / _sanitize_filename(self.title)
            self.dir_path.mkdir(parents=True, exist_ok=True)

            cover_file = self._download_cover()

            chapter_links = []
            if soup:
                chapter_links = soup.select('a[href*="/c/' + self.cid + '/"]')

            chapters = []
            seen_ids = set()

            for link in chapter_links:
                href = link.get('href', '')
                match = re.search(r'/c/\d+/(\d+)', href)
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

            sections = []
            for idx, ch in enumerate(chapters):
                safe_title = _sanitize_filename(ch['title'])
                dir_name = f'ch_{idx + 1:03d}_{safe_title}'

                chapter = LoLoBunComicChapter(
                    idx=idx + 1,
                    title=ch['title'],
                    chapter_id=ch['chapter_id'],
                    fetcher=self.fetcher,
                    dir_name=dir_name,
                )
                image_urls = chapter.get_image_urls()

                sections.append(
                    LoLoBunComicCatalogSection(
                        idx=idx + 1,
                        title=ch['title'],
                        chapter_id=ch['chapter_id'],
                        dir=dir_name,
                        image_urls=image_urls,
                    )
                )

            catalog = LoLoBunComicCatalog(
                id=self.id,
                title=self.title,
                author=self.author,
                cover=self.cover,
                cover_file=cover_file,
                description=self.intro,
                sections=sections,
            )
            catalog.save(self.dir_path / 'catalog.json')

            return True
        except Exception as e:
            logger.error(f'Setup failed: {e}')
            return False

    def get_download_items(self) -> list[tuple[LoLoBunComicChapter, LoLoBunComicPage]]:
        catalog = self._load_catalog()
        chapters = []
        for sec in catalog.sections:
            chapter = LoLoBunComicChapter(
                idx=sec.idx,
                title=sec.title,
                chapter_id=sec.chapter_id,
                fetcher=self.fetcher,
                dir_name=sec.dir,
            )
            for page in chapter.get_items():
                chapters.append((chapter, page))
        return chapters

    def download(self, ext: str = 'jpg', item_prefix: str = 'page'):
        super().download(ext=ext, item_prefix=item_prefix)
