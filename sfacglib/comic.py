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
        args = []
        for script in soup.find_all('script'):
            txt = script.string or ''
            if all(v in txt for v in var_names):
                for var in var_names:
                    match = re.search(rf'{var}\s*=\s*([^\s;]+);', txt)
                    if match:
                        args.append(match.group(1).strip('"'))
        return args

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
        self.title: str = ''
        self.info: str = ''
        self.sel = selectors or Selectors()

    def __repr__(self):
        return f'<Comic: {self.url}>'

    def get_info(self) -> tuple[str, str]:
        html = self.fetcher.get_html(self.url)
        soup = BeautifulSoup(html, 'html.parser')

        self.sel.find(soup, 'comic_info', 'container', url=self.url)

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
        info_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title></head>
<body>
<h1>{title}</h1>
<img src="{cover}" alt="">
<p>漫画地址： {self.url}</p>
<p>标签： {label}</p>
<p>{more_info}</p>
<p>{interactions}</p>
<div>{description}</div>
</body>
</html>"""
        return self.info, info_html

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

        catalog = {
            'url': self.url,
            'title': self.title,
            'info': info_md,
            'sections': [],
            'items': [],
        }

        for section in sections:
            catalog['sections'].append({
                'idx': section.idx,
                'title': section.title,
            })

        if file_type == 'html' and not local_images:
            logger.warning('⚠️ 使用URL模式: 图片链接随时可能失效，建议使用 local_images=True 下载到本地')

            all_items = []
            for section in sections:
                for item in section.get_items():
                    all_items.append((section, item))

            for section, item in all_items:
                catalog['items'].append({
                    'section_idx': section.idx,
                    'section_title': section.title,
                    'item_idx': item.idx,
                    'item_title': item.title,
                    'item_url': item.url,
                    'file': '',
                })

            (dir_path / 'catalog.json').write_text(
                json.dumps(catalog, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )

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
        task_id = tracker.create_task('comic', self.title, self.url, '', chapters=item_list) if tracker else None

        lock = threading.Lock()
        pbar = tqdm(total=len(all_items), desc=self.title, unit='page')

        catalog['items'] = self._download_items(all_items, dir_path, 'jpg', 'ch', 'page', pbar, lock, tracker, task_id)

        pbar.close()

        (dir_path / 'catalog.json').write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )
        (dir_path / 'info.md').write_text(info_md, encoding='utf-8')

        if tracker and task_id:
            tracker.mark_task_done(task_id)
            pending = tracker.get_pending(task_id)
            if not pending:
                tracker.delete_task(task_id)
                logger.bind(force=True).info(f'任务完成，已清理记录: {task_id}')
            else:
                logger.warning(f'任务有 {len(pending)} 个失败项，保留记录')

        logger.bind(force=True).info(f'目录保存到 {dir_path}')

        if file_type == 'html':
            self._export_html(dir_path, sections, local_images=True)
        elif file_type == 'epub':
            self._export_epub(dir_path, sections)
        elif file_type == 'pdf':
            self._export_pdf(dir_path, sections)

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
            logger.warning('⚠️ 使用URL模式: 图片链接随时可能失效，建议使用 local_images=True 下载到本地')

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
            catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
        else:
            catalog = {'items': []}

        if not local_images:
            logger.warning('⚠️ HTML使用远程URL，图片链接将在服务器清理后失效')

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
            html_parts.append('<div class="warning">⚠️ 本文件使用远程图片URL，链接随时可能失效。建议下载本地版本。</div>')

        html_parts.append("""<div class="toc">
<h2>目录</h2>
""")

        for section in sections:
            html_parts.append(f'<a href="#ch_{section.idx:03d}">{section.title}</a>')

        html_parts.append('</div>')

        items_by_section: dict[int, list] = {}
        for item in catalog.get('items', []):
            sec_idx = item.get('section_idx', 0)
            if sec_idx not in items_by_section:
                items_by_section[sec_idx] = []
            items_by_section[sec_idx].append(item)

        for section in sections:
            html_parts.append(f'<div class="chapter" id="ch_{section.idx:03d}">')
            html_parts.append(f'<h2>{section.title}</h2>')

            for item in items_by_section.get(section.idx, []):
                if local_images:
                    img_src = item.get('file', '')
                else:
                    img_src = item.get('item_url', '')

                html_parts.append(f'<img src="{img_src}" alt="{item.get("item_title", "")}" loading="lazy">')

            html_parts.append('</div>')

        html_parts.append('</body></html>')

        html_file = dir_path / f'{_sanitize_filename(self.title)}.html'
        html_file.write_text('\n'.join(html_parts), encoding='utf-8')
        logger.bind(force=True).info(f'HTML文件: {html_file}')

    def _export_epub(self, dir_path: Path, sections: list[ComicChapter]):
        try:
            from ebooklib import epub
        except ImportError:
            logger.error('需要安装 ebooklib: uv add ebooklib')
            return

        catalog_path = dir_path / 'catalog.json'
        if not catalog_path.exists():
            logger.error('未找到目录，请先下载')
            return

        catalog = json.loads(catalog_path.read_text(encoding='utf-8'))

        book = epub.EpubBook()
        book.set_identifier(self.url)
        book.set_title(self.title)
        book.set_language('zh')

        cover_url = ''
        info_html = catalog.get('info', '')
        soup = BeautifulSoup(info_html, 'html.parser')
        cover_img = soup.find('img')
        if cover_img:
            cover_url = cover_img.get('src', '')

        if cover_url:
            try:
                cover_data = self.fetcher.get_binary(cover_url)
                book.set_cover('cover.jpg', cover_data)
            except Exception as e:
                logger.warning(f'封面下载失败: {e}')

        spine = ['nav']
        toc = []

        items_by_section: dict[int, list] = {}
        for item in catalog.get('items', []):
            sec_idx = item.get('section_idx', 0)
            if sec_idx not in items_by_section:
                items_by_section[sec_idx] = []
            items_by_section[sec_idx].append(item)

        for section in sections:
            ch_items = items_by_section.get(section.idx, [])
            if not ch_items:
                continue

            ch_html = f'<h2>{section.title}</h2>'
            for item in ch_items:
                img_path = dir_path / item.get('file', '')
                if img_path.exists():
                    img_data = img_path.read_bytes()
                    fname = f'img_{section.idx:03d}_{item.get("item_idx", 0):03d}.jpg'
                    book.add_item(epub.EpubImage(
                        file_name=f'images/{fname}',
                        media_type='image/jpeg',
                        content=img_data,
                    ))
                    ch_html += f'<img src="images/{fname}" alt="">'

            page = epub.EpubHtml(
                title=section.title,
                file_name=f'ch_{section.idx:03d}.xhtml',
                lang='zh',
                content=ch_html,
            )
            book.add_item(page)
            spine.append(page)
            toc.append(page)

        book.toc = toc
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = spine

        epub_path = dir_path / f'{_sanitize_filename(self.title)}.epub'
        epub.write_epub(str(epub_path), book)
        logger.bind(force=True).info(f'EPUB保存到 {epub_path}')

    def _export_pdf(self, dir_path: Path, sections: list[ComicChapter], padding: int = 0):
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            from reportlab.lib.utils import ImageReader
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        except ImportError:
            logger.error('需要安装 reportlab: uv add reportlab')
            return

        catalog_path = dir_path / 'catalog.json'
        if not catalog_path.exists():
            logger.error('未找到目录，请先下载')
            return

        catalog = json.loads(catalog_path.read_text(encoding='utf-8'))

        pdf_path = dir_path / f'{_sanitize_filename(self.title)}.pdf'
        c = canvas.Canvas(str(pdf_path), pagesize=A4)
        width, height = A4

        items_by_section: dict[int, list] = {}
        for item in catalog.get('items', []):
            sec_idx = item.get('section_idx', 0)
            if sec_idx not in items_by_section:
                items_by_section[sec_idx] = []
            items_by_section[sec_idx].append(item)

        for section in sections:
            ch_items = items_by_section.get(section.idx, [])
            if not ch_items:
                continue

            c.setFont('STSong-Light', 16)
            c.drawCentredString(width / 2, height - 50, section.title)
            c.showPage()

            for item in ch_items:
                img_path = dir_path / item.get('file', '')
                if img_path.exists():
                    try:
                        img = ImageReader(str(img_path))
                        img_width, img_height = img.getSize()

                        usable_width = width - 2 * padding
                        usable_height = height - 2 * padding

                        scale = min(usable_width / img_width, usable_height / img_height)
                        draw_width = img_width * scale
                        draw_height = img_height * scale

                        x = (width - draw_width) / 2
                        y = (height - draw_height) / 2

                        c.drawImage(img, x, y, draw_width, draw_height)
                        c.showPage()
                    except Exception as e:
                        logger.warning(f'图片处理失败: {e}')

        c.save()
        logger.bind(force=True).info(f'PDF保存到 {pdf_path}')


if __name__ == '__main__':
    comic_url = f'{COMIC_BASE}/b/ZXNWM/'
    comic = Comic(comic_url)
    comic.download(file_type='dir')
