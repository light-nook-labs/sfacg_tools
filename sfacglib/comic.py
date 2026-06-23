import re
import json
import threading
from pathlib import Path
from time import time
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from bs4 import BeautifulSoup
from loguru import logger
from .fetcher import Fetcher
from .selectors import Selectors
from .base import Container, Section, Item, _sanitize_filename
from .config import COMIC_BASE, API_COMIC_PICS, API_COMIC_VIP, COMIC_READER_BASE, WORKERS_IMAGE, WORKERS_CHAPTER
from .progress import ProgressTracker, _extract_id
from .models import Catalog, CatalogSection, CatalogItem
from .convert import convert_to_epub, convert_to_pdf


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

    def __init__(self, idx: int, title: str, url: str, fetcher: Fetcher, sel: Selectors):
        super().__init__(idx, title)
        self.url = url
        self.fetcher = fetcher
        self.sel = sel

    def _get_args(self, html: str = '') -> list[str]:
        if not html:
            html = self.fetcher.get_html(self.url)

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

    def _is_vip(self, html: str = '') -> bool:
        if not html:
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
        html = self.fetcher.get_html(self.url)
        args = self._get_args(html)
        if len(args) < 3:
            logger.error(f'Failed to extract comic args from {self.url}')
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
            resp = self.fetcher.get(api_url, params=params, headers=headers)
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

    def __init__(self, url: str, fetcher: Fetcher | None = None, selectors: Selectors | None = None):
        super().__init__(fetcher)
        self.url = url
        self.id = self._extract_id(url)
        self.title: str = ''
        self.author: str = ''
        self.intro: str = ''
        self.cover: str = ''
        self.sel = selectors or Selectors()

    @staticmethod
    def _extract_id(url: str) -> str:
        match = re.search(r'/mh/(\w+)', url)
        return match.group(1) if match else url

    def __repr__(self):
        return f'<Comic: {self.url}>'

    def get_info(self) -> tuple[str, str]:
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
        if cover.startswith('//'):
            cover = 'https:' + cover
        self.cover = cover

        label = ''
        label_tag = self.sel.find(soup, 'comic_info', 'labels', url=self.url, required=False)
        if label_tag:
            label = ' '.join(label_tag.stripped_strings)

        author = ''
        more_info = ''
        if container:
            container_text = container.get_text()
            author_match = re.search(r'作者[：:]\s*(.+?)(?:\s*作品类型|$)', container_text)
            if author_match:
                author = author_match.group(1).strip()
            
            region_match = re.search(r'漫画地区[：:]\s*(.+?)(?:\s|作者|$)', container_text)
            type_match = re.search(r'作品类型[：:]\s*(.+?)(?:\s|$)', container_text)
            update_match = re.search(r'最新连载[：:]\s*(.+?)(?:\s|$)', container_text)
            clicks_match = re.search(r'点击数[：:]\s*(\d+)', container_text)
            
            parts = []
            if region_match:
                parts.append(f'地区：{region_match.group(1).strip()}')
            if type_match:
                parts.append(f'类型：{type_match.group(1).strip()}')
            if update_match:
                parts.append(f'最新：{update_match.group(1).strip()}')
            if clicks_match:
                parts.append(f'点击：{clicks_match.group(1).strip()}')
            more_info = '　'.join(parts)
        self.author = author

        interactions = ''
        interact_tag = self.sel.find(soup, 'comic_info', 'interactions', url=self.url, required=False)
        if interact_tag:
            items = list(interact_tag.stripped_strings)
            if items:
                items.pop()
            interactions = ' '.join(items)

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

        info_md = f"""
# {title}

![封面]({cover})

漫画地址： {self.url}

作者：{author}

标签： {label}

{more_info}

{interactions}

{description}
"""
        info_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title></head>
<body>
<h1>{title}</h1>
<img src="{cover}" alt="">
<p>漫画地址： {self.url}</p>
<p>作者：{author}</p>
<p>标签： {label}</p>
<p>{more_info}</p>
<p>{interactions}</p>
<div>{description}</div>
</body>
</html>"""
        return info_md, info_html

    def get_sections(self) -> list[ComicChapter]:
        html = self.fetcher.get_html(self.url)
        soup = BeautifulSoup(html, 'html.parser')
        a_tags = self.sel.find_all(soup, 'comic_info', 'chapter_list', url=self.url)
        chapters: list[ComicChapter] = []
        for ch_idx, a_tag in enumerate(reversed(a_tags), start=1):
            href = a_tag.get('href', '')
            if href:
                ch_title = a_tag.get_text().strip()
                ch_url = f'{COMIC_READER_BASE}{href}'
                chapters.append(ComicChapter(ch_idx, ch_title, ch_url, self.fetcher, self.sel))
        return chapters

    def download(
        self,
        path: str | Path = './',
        file_type: str = 'dir',
        local_images: bool = True,
        tracker: ProgressTracker | None = None,
        start_chapter: str | None = None,
        end_chapter: str | None = None,
        chapter_range: str | None = None,
    ):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        if file_type not in ('dir', 'html', 'epub', 'pdf'):
            logger.error(f'不支持的格式: {file_type}')
            return

        sections = self.get_sections()
        sections = self._filter_sections(sections, start_chapter, end_chapter, chapter_range)

        info_md, info_html = self.get_info()
        dir_path = path / _sanitize_filename(self.title)
        dir_path.mkdir(parents=True, exist_ok=True)

        catalog = Catalog(
            id=self.id,
            title=self.title,
            author=self.author,
            cover=self.cover,
            intro=info_md,
        )

        if file_type == 'html' and not local_images:
            logger.warning('使用URL模式: 图片链接随时可能失效，建议使用 local_images=True 下载到本地')

            for section in sections:
                catalog_section = CatalogSection(
                    idx=section.idx,
                    title=section.title,
                    items=[],
                )
                for item in section.get_items():
                    catalog_section.items.append(CatalogItem(
                        idx=item.idx,
                        title=item.title,
                        url=item.url,
                        file='',
                    ))
                catalog.sections.append(catalog_section)

            catalog.save(dir_path / 'catalog.json')

            self._export_html(dir_path, sections, local_images=False)
            logger.bind(force=True).info(f'HTML保存到 {dir_path}')
            return

        all_items = []
        for section in sections:
            for item in section.get_items():
                all_items.append((section, item))

        if not all_items:
            logger.error('没有可下载的内容')
            return

        logger.bind(force=True).info(f'共 {len(all_items)} 页待下载')

        item_list = [{'url': i.url, 'title': i.title} for _, i in all_items]
        task_id = tracker.create_task('comic', self.title, self.id, '', chapters=item_list) if tracker else None

        lock = threading.Lock()
        pbar = tqdm(total=len(all_items), desc=self.title, unit='page')

        catalog.sections = self._download_items(all_items, dir_path, 'jpg', 'ch', 'page', pbar, lock, tracker, task_id)

        pbar.close()

        catalog.save(dir_path / 'catalog.json')
        (dir_path / 'info.md').write_text(info_md, encoding='utf-8')

        if tracker and task_id:
            tracker.finalize_task(task_id)

        logger.bind(force=True).info(f'目录保存到 {dir_path}')

        if file_type == 'html':
            self._export_html(dir_path, sections, local_images=True)
        elif file_type == 'epub':
            convert_to_epub(dir_path, self.fetcher)
        elif file_type == 'pdf':
            convert_to_pdf(dir_path, fetcher=self.fetcher)

    def export_html(
        self,
        path: str | Path = './',
        local_images: bool = True,
        start_chapter: str | None = None,
        end_chapter: str | None = None,
        chapter_range: str | None = None,
    ):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        if not local_images:
            logger.warning('使用URL模式: 图片链接随时可能失效，建议使用 local_images=True 下载到本地')

        sections = self.get_sections()
        sections = self._filter_sections(sections, start_chapter, end_chapter, chapter_range)

        info_md, info_html = self.get_info()
        dir_path = path / _sanitize_filename(self.title)
        dir_path.mkdir(parents=True, exist_ok=True)

        if local_images:
            all_items = []
            for section in sections:
                for item in section.get_items():
                    all_items.append((section, item))

            if all_items:
                lock = threading.Lock()
                pbar = tqdm(total=len(all_items), desc=self.title, unit='page')
                self._download_items(all_items, dir_path, 'jpg', 'ch', 'page', pbar, lock)
                pbar.close()

        self._export_html(dir_path, sections, local_images)
        logger.bind(force=True).info(f'HTML保存到 {dir_path}')

    def _export_html(self, dir_path: Path, sections: list[ComicChapter], local_images: bool = True):
        catalog_path = dir_path / 'catalog.json'
        if catalog_path.exists():
            catalog = Catalog.load(catalog_path)
        else:
            catalog = Catalog(id='', title=self.title)

        if not local_images:
            logger.warning('HTML使用远程URL，图片链接将在服务器清理后失效')

        html_parts = [f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{self.title}</title>
<style>
body {{ font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
h1 {{ text-align: center; color: #333; }}
h2 {{ color: #666; border-bottom: 2px solid #ddd; padding-bottom: 10px; }}
.chapter {{ margin-bottom: 40px; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
img {{ max-width: 100%; height: auto; display: block; margin: 10px auto; }}
.toc {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
.toc a {{ display: block; padding: 8px; color: #0066cc; text-decoration: none; }}
.toc a:hover {{ background: #f0f0f0; }}
.warning {{ background: #fff3cd; border: 1px solid #ffc107; padding: 12px; border-radius: 8px; margin-bottom: 20px; }}
</style>
</head>
<body>
<h1>{self.title}</h1>
"""]

        if not local_images:
            html_parts.append('<div class="warning">本文件使用远程图片URL，链接随时可能失效。建议下载本地版本。</div>')

        html_parts.append("""<div class="toc">
<h2>目录</h2>
""")

        for section in sections:
            html_parts.append(f'<a href="#ch_{section.idx:03d}">{section.title}</a>')

        html_parts.append('</div>')

        for section in catalog.sections:
            html_parts.append(f'<div class="chapter" id="ch_{section.idx:03d}">')
            html_parts.append(f'<h2>{section.title}</h2>')

            for item in section.items:
                if local_images:
                    img_src = item.file
                else:
                    img_src = item.url

                html_parts.append(f'<img src="{img_src}" alt="{item.title}" loading="lazy">')

            html_parts.append('</div>')

        html_parts.append('</body></html>')

        html_file = dir_path / f'{_sanitize_filename(self.title)}.html'
        html_file.write_text('\n'.join(html_parts), encoding='utf-8')
        logger.bind(force=True).info(f'HTML文件: {html_file}')


if __name__ == '__main__':
    comic_url = f'{COMIC_BASE}/b/ZXNWM/'
    comic = Comic(comic_url)
    comic.download(file_type='dir')
