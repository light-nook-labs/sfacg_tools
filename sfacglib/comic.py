import re
from pathlib import Path
from time import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from bs4 import BeautifulSoup
from loguru import logger
from .fetcher import Fetcher
from .selectors import Selectors
from .config import COMIC_BASE, API_COMIC_PICS, API_COMIC_VIP, COMIC_READER_BASE, WORKERS_IMAGE
from .utils import sanitize_filename


class ComicChapter:
    common_url = API_COMIC_PICS

    def __init__(self, title: str, url: str, fetcher: Fetcher | None = None, selectors: Selectors | None = None):
        self.title = title
        self.url = url
        self.fetcher = fetcher or Fetcher()
        self.sel = selectors or Selectors()

    def __repr__(self):
        return f'<ComicChapter: {self.title}, {self.url}>'

    def _get_args(self) -> list[str]:
        html = self.fetcher.get_html(self.url)
        soup = BeautifulSoup(html, 'html.parser')
        var_names = ['comicId', 'nv', 'chapterId']
        args = []
        for script in soup.find_all('script'):
            txt = script.string or ''
            if all(v in txt for v in var_names):
                for var in var_names:
                    match = re.search(rf'{var}\s*=\s*([^\s;]+);', txt)
                    if match:
                        args.append(match.group(1).strip('"'))
        return args

    def _is_vip(self) -> bool:
        """Detect if this comic chapter requires VIP access."""
        html = self.fetcher.get_html(self.url)
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
            logger.error(f'Failed to extract comic args from {self.url}')
            return []
        comic_id, nv, chapter_id = args[0], args[1], args[2]

        api_url = API_COMIC_VIP if use_vip_api else self.common_url
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
            resp = self.fetcher.get(api_url, params=params, headers=headers)
            data = resp.json()
        except Exception as e:
            logger.error(f'Failed to get comic images: {e}')
            if not use_vip_api:
                logger.info('Retrying with VIP API endpoint...')
                return self.get_image_urls(use_vip_api=True)
            return []

        if isinstance(data, dict):
            urls = data.get('data', [])
            if not urls and not use_vip_api:
                logger.info('Empty result, retrying with VIP API endpoint...')
                return self.get_image_urls(use_vip_api=True)
            return urls
        return []

    def _download_image(self, idx: int, url: str, path: Path):
        headers = {'Referer': f'{COMIC_READER_BASE}/'}
        resp = self.fetcher.get(url, headers=headers)
        (path / f'{idx:03}.jpg').write_bytes(resp.content)
        logger.debug(f'page {idx} downloaded')

    def download(self, path: str | Path = './images/') -> None:
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        use_vip = self._is_vip()
        if use_vip:
            logger.info(f'VIP comic chapter detected: {self.title}')

        urls = self.get_image_urls(use_vip_api=use_vip)
        if not urls:
            logger.warning(f'No images found for {self.title}')
            return

        with ThreadPoolExecutor(max_workers=WORKERS_IMAGE) as executor:
            futures = {executor.submit(self._download_image, idx, url, path): idx
                       for idx, url in enumerate(urls, start=1)}
            for future in tqdm(as_completed(futures), total=len(futures), desc='Pages', leave=False):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f'Image download failed: {e}')


class Comic:
    def __init__(self, url: str, fetcher: Fetcher | None = None, selectors: Selectors | None = None):
        self.url = url
        self.title: str = ''
        self.info: str = ''
        self.fetcher = fetcher or Fetcher()
        self.sel = selectors or Selectors()

    def __repr__(self):
        return f'<Comic: {self.url}>'

    def get_comic_info(self) -> dict[str, str]:
        html = self.fetcher.get_html(self.url)
        soup = BeautifulSoup(html, 'html.parser')

        self.sel.find(soup, 'comic_info', 'container', url=self.url)
        title = self.sel.find_text(soup, 'comic_info', 'title', url=self.url) or '未知漫画'
        self.title = title
        cover = self.sel.find_attr(soup, 'comic_info', 'cover', url=self.url) or ''

        label = ''
        label_tag = self.sel.find(soup, 'comic_info', 'labels', url=self.url, required=False)
        if label_tag:
            label = ' '.join(label_tag.stripped_strings)

        more_info = ''
        stats_tag = self.sel.find(soup, 'comic_info', 'stats', url=self.url, required=False)
        if stats_tag:
            more_info = ' '.join(stats_tag.stripped_strings)

        interactions = ''
        interact_tag = self.sel.find(soup, 'comic_info', 'interactions', url=self.url, required=False)
        if interact_tag:
            items = list(interact_tag.stripped_strings)
            if items:
                items.pop()
            interactions = ' '.join(items)

        description = ''
        desc_tag = self.sel.find(soup, 'comic_info', 'description', url=self.url, required=False)
        if desc_tag:
            description = desc_tag.get_text()

        self.info = f"""
# {title}

![封面]({cover})

漫画地址： {self.url}

标签： {label}

{more_info}

{interactions}

{description}
"""
        a_tags = self.sel.find_all(soup, 'comic_info', 'chapter_list', url=self.url)
        chapter_dict: dict[str, str] = {}
        for a_tag in reversed(a_tags):
            href = a_tag.get('href', '')
            if href:
                chapter_dict[href] = a_tag.get_text().strip()
        return chapter_dict

    def download(self, path: str | Path = './'):
        chapter_dict = self.get_comic_info()
        comic_path = Path(path) / sanitize_filename(self.title)
        comic_path.mkdir(parents=True, exist_ok=True)
        total = len(chapter_dict)

        for i, (href, chapter_title) in enumerate(tqdm(chapter_dict.items(), desc='Chapters'), start=1):
            safe_title = sanitize_filename(chapter_title)
            chapter_path = comic_path / f'{i:03}-{safe_title}'
            chapter_path.mkdir(parents=True, exist_ok=True)
            chapter = ComicChapter(
                title=chapter_title,
                url=f'{COMIC_BASE}{href}',
                fetcher=self.fetcher,
                selectors=self.sel,
            )
            chapter.download(chapter_path)
            logger.bind(force=True).info(f'[{i}/{total}] {chapter_title}')


if __name__ == '__main__':
    comic_url = f'{COMIC_BASE}/b/ZXNWM/'
    comic = Comic(comic_url)
    comic.download()
