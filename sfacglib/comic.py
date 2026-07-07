import re
from pathlib import Path
from time import time

from bs4 import BeautifulSoup
from loguru import logger

from .base import Container, InvalidNovelError, Item, Section
from .config import API_COMIC_PICS, API_COMIC_VIP, COMIC_READER_BASE
from .fetcher import Fetcher
from .selectors import Selectors
from .utils import fix_url_protocol, save_json
from .utils import sanitize_filename as _sanitize_filename


class ComicPage(Item):
    def __init__(self, idx: int, url: str, fetcher: Fetcher):
        super().__init__(idx, '', url)
        self.fetcher = fetcher
        self._data: bytes | None = None

    def download(self, save_path: Path, pbar=None, lock=None):
        headers = {'Referer': f'{COMIC_READER_BASE}/'}
        resp = self.fetcher.get(self.url, headers=headers)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(resp.content)
        self._data = resp.content
        if pbar and lock:
            with lock:
                pbar.update(1)

    def get_data(self) -> bytes:
        if self._data is None:
            headers = {'Referer': f'{COMIC_READER_BASE}/'}
            resp = self.fetcher.get(self.url, headers=headers)
            self._data = resp.content
        return self._data


class ComicChapter(Section):
    def __init__(self, idx: int, title: str, chapter_url: str, fetcher: Fetcher, sel: Selectors, dir_name: str = ''):
        super().__init__(idx, title)
        self.chapter_url = chapter_url
        self.fetcher = fetcher
        self.sel = sel
        self.dir_name = dir_name or f'ch_{idx:03d}_{_sanitize_filename(title)}'
        self._html: str = ''

    def _get_html(self) -> str:
        if not self._html:
            self._html = self.fetcher.get_html(self.chapter_url)
        return self._html

    def _get_args(self) -> list[str]:
        html = self._get_html()

        patterns = [
            (r'var\s+c\s*=\s*(\d+)', 'comicId'),
            (r'var\s+chapId\s*=\s*(\d+)', 'chapterId'),
            (r'var\s+nv\s*=\s*"([^"]+)"', 'nv'),
            (r'comicId\s*=\s*([^\s;]+)', 'comicId'),
            (r'chapterId\s*=\s*([^\s;]+)', 'chapterId'),
        ]

        result = {}
        for pattern, key in patterns:
            if key not in result:
                match = re.search(pattern, html)
                if match:
                    result[key] = match.group(1).strip('"')

        if len(result) == 3:
            return [result['comicId'], result['nv'], result['chapterId']]

        soup = BeautifulSoup(html, 'html.parser')
        var_names = ['comicId', 'nv', 'chapterId']
        result = {}
        for script in soup.find_all('script'):
            txt = script.string or ''
            if all(v in txt for v in var_names):
                for var in var_names:
                    if var not in result:
                        match = re.search(rf'{var}\s*=\s*([^\s;]+);', txt)
                        if match:
                            result[var] = match.group(1).strip('"')
                if len(result) == 3:
                    return [result['comicId'], result['nv'], result['chapterId']]
        return []

    def _is_vip(self) -> bool:
        html = self._get_html()
        soup = BeautifulSoup(html, 'html.parser')

        for script in soup.find_all('script'):
            txt = script.string or ''
            if 'isVip' in txt and 'true' in txt:
                return True

        body_text = soup.get_text()
        vip_keywords = ['VIP章节', '开通VIP', '购买章节', '登录后可查看全文']
        for kw in vip_keywords:
            if kw in body_text:
                return True

        return False

    def get_image_urls(self, use_vip_api: bool = False) -> list[str]:
        args = self._get_args()
        if len(args) < 3:
            logger.error(f'Failed to extract comic args from {self.chapter_url}')
            return []
        comic_id, nv, chapter_id = args[0], args[1], args[2]

        api_url = API_COMIC_VIP if use_vip_api else API_COMIC_PICS
        try:
            params = {
                'op': 'getPics',
                'cid': int(comic_id),
                'chapId': int(chapter_id),
                'serial': 'ZP',
                'path': nv,
                '_': int(time() * 1000),
            }
        except ValueError:
            logger.error(f'Invalid comic/chapter ID: {comic_id}, {chapter_id}')
            return []

        headers = {
            'Referer': f'{COMIC_READER_BASE}/',
        }

        try:
            resp = self.fetcher.get(api_url, params=params, headers=headers, vip=use_vip_api)
            data = resp.json()
        except Exception as e:
            if not use_vip_api:
                logger.info(f'Non-VIP API failed ({e}), retrying with VIP API...')
                return self.get_image_urls(use_vip_api=True)
            logger.error(f'Failed to get comic images: {e}')
            return []

        if isinstance(data, dict):
            urls = data.get('data', [])
            if not urls and not use_vip_api:
                logger.info('Empty result from non-VIP API, retrying with VIP API...')
                return self.get_image_urls(use_vip_api=True)
            return urls
        return []

    def get_items(self) -> list[ComicPage]:
        use_vip = self._is_vip()
        urls = self.get_image_urls(use_vip_api=use_vip)
        pages = []
        for idx, url in enumerate(urls, start=1):
            pages.append(ComicPage(idx, url, self.fetcher))
        return pages


class Comic(Container):
    def __init__(
        self,
        url: str,
        output_dir: str | Path | None = None,
        fetcher: Fetcher | None = None,
        selectors: Selectors | None = None,
    ):
        super().__init__(output_dir, fetcher)
        self.url = url
        self.id = self._extract_id(url)
        self.sel = selectors or Selectors()

        if not self.setup():
            raise InvalidNovelError(f'HTTP错误或URL无效 (url={url})')

    @staticmethod
    def _extract_id(url: str) -> str:
        match = re.search(r'/mh/(\w+)', url)
        return match.group(1) if match else url

    def __repr__(self):
        return f'<Comic: {self.url}>'

    def setup(self) -> bool:
        try:
            html = self.fetcher.get_html(self.url)
            soup = BeautifulSoup(html, 'html.parser')

            container = self.sel.find(soup, 'comic_info', 'container', url=self.url)

            title_tag = soup.title
            if title_tag:
                title_text = title_tag.get_text()
                if ',' in title_text:
                    title = title_text.split(',')[0].strip()
                elif '漫画' in title_text:
                    title = title_text.split('漫画')[0].strip()
                else:
                    title = title_text.split('_')[0].strip()
            else:
                title = self.sel.find_text(soup, 'comic_info', 'title', url=self.url) or '未知漫画'
            self.title = title

            cover = self.sel.find_attr(soup, 'comic_info', 'cover', url=self.url, required=False) or ''
            self.cover = fix_url_protocol(cover)

            author = ''
            if container:
                container_text = container.get_text()
                author_match = re.search(r'作者[：:]\s*(.+?)(?:\s*作品类型|$)', container_text)
                if author_match:
                    author = author_match.group(1).strip()
            self.author = author

            description = ''
            if container:
                li_tags = container.find_all('li')
                for li in li_tags:
                    if not li.get('class') or 'cover' not in li.get('class', []):
                        text = li.get_text(strip=True)
                        if text and len(text) > 20:
                            description = text.split('漫画地区')[0].split('作者')[0].strip()
                            break
            self.intro = description

            self.dir_path = self.output_dir / _sanitize_filename(self.title)
            self.dir_path.mkdir(parents=True, exist_ok=True)

            info_md = f"""# {title}

![封面]({self.cover})

漫画地址： {self.url}

作者：{author}

{description}
"""
            (self.dir_path / 'info.md').write_text(info_md, encoding='utf-8')

            a_tags = self.sel.find_all(soup, 'comic_info', 'chapter_list', url=self.url)

            sections = []
            ch_idx = 0
            for a_tag in reversed(a_tags):
                href = a_tag.get('href', '')
                if not href:
                    continue
                ch_idx += 1
                ch_title = a_tag.get_text().strip()
                ch_url = f'{COMIC_READER_BASE}{href}'

                safe_title = _sanitize_filename(ch_title)
                dir_name = f'ch_{ch_idx:03d}_{safe_title}'

                sections.append(
                    {
                        'idx': ch_idx,
                        'title': ch_title,
                        'chapter_url': ch_url,
                        'dir': dir_name,
                    }
                )

            catalog = {
                'id': self.id,
                'title': self.title,
                'author': self.author,
                'cover': self.cover,
                'info_file': 'info.md',
                'sections': sections,
            }
            save_json(catalog, self.dir_path / 'catalog.json')

            return True
        except Exception as e:
            logger.error(f'Setup failed: {e}')
            return False

    def get_download_items(self) -> list[tuple[ComicChapter, ComicPage]]:
        catalog = self._load_catalog()
        chapters = []
        for sec in catalog.get('sections', []):
            chapter = ComicChapter(
                idx=sec['idx'],
                title=sec['title'],
                chapter_url=sec['chapter_url'],
                fetcher=self.fetcher,
                sel=self.sel,
                dir_name=sec.get('dir'),
            )
            for page in chapter.get_items():
                chapters.append((chapter, page))
        return chapters

    def download(self, ext: str = 'jpg', item_prefix: str = 'page'):
        super().download(ext=ext, item_prefix=item_prefix)
