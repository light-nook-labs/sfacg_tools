import re
import json
import time
import threading
from pathlib import Path
from urllib.parse import urlparse
from bs4 import BeautifulSoup, Tag
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from .fetcher import Fetcher
from .selectors import Selectors
from .ch import Chapter, PCChapter
from .base import Container, Section, Item, _sanitize_filename, AntiScrapingError
from .config import (
    URL_NOVEL_INDEX, URL_NOVEL_MENU, MOBILE_BASE, PC_BASE, WORKERS_CHAPTER,
    URL_REVIEW_LIST, URL_REVIEW_DETAIL, API_HTML5, API_VIP_IMAGE, VIP_IMAGE_WIDTH,
)
from .progress import ProgressTracker, _extract_id
from .utils import parse_volume_ul, mobile_url
from .vip import VipMode


class NovelChapter(Item):

    def __init__(self, idx: int, title: str, url: str, fetcher: Fetcher, sel: Selectors,
                 vip: bool = False, vip_mode=VipMode.OCR, llm_api_key='', llm_base_url='', llm_model='',
                 pw_page=None):
        super().__init__(idx, title, url)
        self.fetcher = fetcher
        self.sel = sel
        self.vip = vip
        self.vip_mode = vip_mode
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model
        self._pw_page = pw_page

    def download(self, save_path: Path, pbar=None, lock=None):
        if self.vip:
            self._download_vip_gif(save_path)
        else:
            self._download_normal(save_path)
        if pbar and lock:
            with lock:
                pbar.update(1)

    def _download_normal(self, save_path: Path):
        ch = PCChapter(self.url, self.fetcher, self.sel)
        md, html = ch.get_chapter_content()
        save_path.write_text(md, encoding='utf-8')

    def _download_vip_gif(self, save_path: Path):
        from .vip import _validate_gif
        from urllib.parse import urlparse, parse_qs

        html = self.fetcher.get(self.url, timeout=(10, 20)).text
        soup = BeautifulSoup(html, 'html.parser')

        vip_img = soup.select_one('#vipImage')
        if not vip_img:
            raise ValueError(f'No #vipImage (no subscription): {self.url}')

        src = vip_img.get('src', '')
        if src.startswith('/'):
            src = PC_BASE + src

        gif_bytes = self.fetcher.get(src, timeout=(10, 30)).content

        expected_w = int(parse_qs(urlparse(src).query).get('w', [0])[0])
        valid, info = _validate_gif(gif_bytes, expected_w)
        if not valid:
            raise AntiScrapingError(f'VIP GIF invalid: {info} ({src})')

        gif_path = save_path.with_suffix('.gif')
        gif_path.write_bytes(gif_bytes)
        logger.info(f'VIP GIF: {gif_path.name} ({len(gif_bytes)} bytes)')

    def _download_vip_playwright(self, save_path: Path, page):
        from .vip import _validate_gif
        from urllib.parse import urlparse, parse_qs
        from playwright.sync_api import TimeoutError as PwTimeout

        try:
            page.goto(self.url, wait_until='domcontentloaded')
        except PwTimeout:
            raise AntiScrapingError(f'Page timeout (anti-scraping?): {self.url}')

        img = page.locator('#vipImage')
        try:
            img.wait_for(state='attached', timeout=10000)
        except PwTimeout:
            raise ValueError(f'No #vipImage (no subscription): {self.url}')

        src = img.get_attribute('src')
        if not src:
            raise ValueError(f'No #vipImage src (no subscription): {self.url}')
        if src.startswith('/'):
            src = PC_BASE + src

        try:
            resp = page.request.get(src, timeout=20000)
        except PwTimeout:
            raise AntiScrapingError(f'Image download timeout (anti-scraping?): {src}')

        gif_bytes = resp.body()

        expected_w = int(parse_qs(urlparse(src).query).get('w', [0])[0])
        valid, info = _validate_gif(gif_bytes, expected_w)
        if not valid:
            raise AntiScrapingError(f'VIP GIF invalid (anti-scraping?): {info} ({src})')

        gif_path = save_path.with_suffix('.gif')
        gif_path.write_bytes(gif_bytes)
        logger.info(f'VIP GIF (pw): {gif_path.name} ({len(gif_bytes)} bytes)')


class NovelVolume(Section):

    def __init__(self, idx: int, title: str, chapters: list[NovelChapter]):
        super().__init__(idx, title)
        self.chapters = chapters

    def get_items(self) -> list[NovelChapter]:
        return self.chapters


class ReviewComment(Item):

    def __init__(self, idx: int, cid: str, title: str, fetcher: Fetcher):
        super().__init__(idx, title, f'{URL_REVIEW_DETAIL}{cid}/')
        self.cid = cid
        self.fetcher = fetcher

    def download(self, save_path: Path, pbar=None, lock=None):
        html = self.fetcher.get_html(self.url)
        soup = BeautifulSoup(html, 'html.parser')

        title = ''
        if soup.title:
            title = soup.title.string.removesuffix('-书评详情-SF轻小说手机版') if soup.title.string else ''

        content = soup.p.get_text().strip() if soup.p else ''

        date = ''
        date_div = soup.find('div')
        if date_div and date_div.span:
            match = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', date_div.span.get_text())
            if match:
                date = match.group()

        replies_num, praise_num = '0', '0'
        hudong = soup.find(class_='shuping_hudong book_bk_qs1')
        if hudong:
            parts = hudong.get_text().split()
            if len(parts) >= 2:
                replies_num, praise_num = parts[0], parts[1]

        replies = self._get_replies()

        msg = f'## {title} - 评论时间{date} 评论数{replies_num}, 点赞数{praise_num}\n\n'
        msg += f'{content}\n\n{replies}\n\n'

        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'a', encoding='utf-8') as f:
            f.write(msg)

        if pbar and lock:
            with lock:
                pbar.update(1)

    def _get_replies(self) -> str:
        page = 0
        replies: list[str] = []
        while True:
            params = {
                'op': 'getcmtreply',
                'cid': self.cid,
                'pi': page,
                'withcmt': 'false',
                '_': int(time.time() * 1000),
            }
            data = self.fetcher.get_json(API_HTML5, params=params)
            reply_list = data.get('Replys', []) if isinstance(data, dict) else []
            if not reply_list:
                break
            for item in reply_list:
                name = item.get('DisplayName', '匿名')
                content = item.get('Content', '').strip()
                date = item.get('CreateTime', '')
                replies.append(f'- {name} ({date}): {content}')
            page += 1
        return '\n'.join(replies)


class ReviewSection(Section):

    def __init__(self, idx: int, title: str, comments: list[ReviewComment]):
        super().__init__(idx, title)
        self.comments = comments

    def get_items(self) -> list[ReviewComment]:
        return self.comments


class Novel(Container):

    def __init__(
        self,
        nid: int,
        fetcher: Fetcher | None = None,
        selectors: Selectors | None = None,
        vip_mode: VipMode = VipMode.OCR,
        llm_api_key: str = '',
        llm_base_url: str = '',
        llm_model: str = '',
    ):
        super().__init__(fetcher)
        self.nid = str(nid)
        self.id = str(nid)
        self.title: str = ''
        self.author: str = ''
        self.intro: str = ''
        self.cover: str = ''
        self.sel = selectors or Selectors()
        self.vip_mode = vip_mode
        self._pc_soup = None
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model

    def get_info(self) -> tuple[str, str]:
        index_url = f'{URL_NOVEL_INDEX}{self.nid}'
        logger.info(index_url)
        html = self.fetcher.get_html(index_url)
        soup = BeautifulSoup(html, 'html.parser')

        self.sel.find(soup, 'novel_info', 'container', url=index_url)
        title = self.sel.find_text(soup, 'novel_info', 'title', url=index_url) or '未知小说'
        self.title = title

        cover_url = self.sel.find_attr(soup, 'novel_info', 'cover', url=index_url) or ''
        if cover_url.startswith('//'):
            cover_url = 'https:' + cover_url
        self.cover = cover_url

        label = ''
        label_tag = self.sel.find(soup, 'novel_info', 'labels', url=index_url, required=False)
        if label_tag:
            label = ' '.join(label_tag.stripped_strings)

        stats_text = self.sel.find_text(soup, 'novel_info', 'stats', url=index_url) or ''
        stats_parts = stats_text.split(' / ')
        author = stats_parts[0].strip() if stats_parts else '未知'
        self.author = author

        word_num, date, clock = '', '', ''
        if len(stats_parts) >= 2:
            remainder = stats_parts[1].strip()
            word_match = re.search(r'(\d+)字', remainder)
            if word_match:
                word_num = word_match.group(1)
                date_match = re.search(r'(\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2})', remainder[word_match.end():])
                if date_match:
                    parts = date_match.group(1).split()
                    if len(parts) >= 2:
                        date, clock = parts[0], parts[1]

        counts_tags = self.sel.find_all(soup, 'novel_info', 'counts', url=index_url, required=False)
        heart_num = counts_tags[0].string.strip() if counts_tags and len(counts_tags) >= 1 and counts_tags[0].string else '0'
        praise_num = counts_tags[1].string.strip() if counts_tags and len(counts_tags) >= 2 and counts_tags[1].string else '0'

        intro = self.sel.find_text(soup, 'novel_info', 'introduction', url=index_url) or ''
        intro = '\n\n'.join(line.strip() for line in intro.split('\n\n'))
        self.intro = intro

        info_md = f"""
# {title}-{author}

## 小说信息

![封面]({cover_url})

原文地址：{URL_NOVEL_INDEX}{self.nid}

作者：{author}\t字数：{word_num}

标签：{label}

最近更新时间：{date} {clock}

收藏量：{heart_num}\t点赞数：{praise_num}

{intro}

{'='*20}
"""
        info_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title></head>
<body>
<h1>{title}-{author}</h1>
<div class="vol">
<h2>小说信息</h2>
<img src="{cover_url}" alt="">
<p>原文地址：{URL_NOVEL_INDEX}{self.nid}</p>
<p>作者：{author}\t字数：{word_num}</p>
<p>标签：{label}</p>
<p>最近更新时间：{date} {clock}</p>
<p>收藏量：{heart_num}\t点赞数：{praise_num}</p>
<div>{intro}</div>
<hr>
</div>
</body>
</html>"""
        return info_md, info_html

    def get_sections(self) -> list[NovelVolume]:
        pc_url = f'{PC_BASE}/Novel/{self.nid}/MainIndex/'
        html = self.fetcher.get_html(pc_url)
        soup = BeautifulSoup(html, 'html.parser')

        catalog_hds = soup.select('.catalog-hd')
        if catalog_hds:
            self._pc_soup = soup
        else:
            menu_url = f'{URL_NOVEL_MENU}{self.nid}'
            html = self.fetcher.get_html(menu_url)
            soup = BeautifulSoup(html, 'html.parser')
            catalog_hds = self.sel.find_all(soup, 'novel_menu', 'volume_tags', url=menu_url, required=False)
            if not catalog_hds:
                catalog_hds = soup.find_all(class_='mulu')
            self._pc_soup = None

        volumes: list[NovelVolume] = []
        vol_idx = 0

        if self._pc_soup:
            for hd in catalog_hds:
                vol_idx += 1
                vol_title_tag = hd.select_one('.catalog-title')
                vol_title = vol_title_tag.get_text().strip() if vol_title_tag else '未命名卷'
                chapters: list[NovelChapter] = []
                ch_idx = 0
                for sib in hd.next_siblings:
                    if not hasattr(sib, 'name') or not sib.name:
                        continue
                    if 'catalog-hd' in str(sib.get('class', '')):
                        break
                    if 'catalog-list' in str(sib.get('class', '')):
                        for a in sib.select('a[href]'):
                            href = a.get('href', '')
                            if not href:
                                continue
                            ch_idx += 1
                            is_vip = a.select_one('.icn_vip') is not None
                            title = a.get('title', '') or a.get_text().replace('VIP', '').strip()
                            if is_vip and '/vip/' in href:
                                url = f'{PC_BASE}{href}'
                            elif href.startswith('/'):
                                url = f'{PC_BASE}{href}'
                            else:
                                url = mobile_url(href)
                            chapters.append(NovelChapter(
                                ch_idx, title, url, self.fetcher, self.sel,
                                vip=is_vip,
                            ))
                volumes.append(NovelVolume(vol_idx, vol_title, chapters))
        else:
            for vol_tag in catalog_hds:
                vol_idx += 1
                vol_title = vol_tag.string or '未命名卷'
                chapters: list[NovelChapter] = []
                ul_tag = parse_volume_ul(vol_tag)
                if ul_tag:
                    ch_idx = 0
                    for a in ul_tag.find_all('a'):
                        href = a.get('href', '')
                        if href:
                            ch_idx += 1
                            chapters.append(NovelChapter(
                                ch_idx, a.get_text(), mobile_url(href), self.fetcher, self.sel,
                                self.vip_mode, self.llm_api_key, self.llm_base_url, self.llm_model,
                            ))
                volumes.append(NovelVolume(vol_idx, vol_title, chapters))

        return volumes

    def _get_reviews(self) -> ReviewSection:
        review_ids = self._get_review_ids()
        comments = []
        for idx, cid in enumerate(reversed(review_ids), start=1):
            comments.append(ReviewComment(idx, cid, self.title, self.fetcher))
        return ReviewSection(1, '长评', comments)

    def _get_review_ids(self) -> list[str]:
        page = 0
        review_ids: list[str] = []
        while True:
            params = {
                'op': 'getcmtlist',
                'nid': self.nid,
                'so': 'addtime',
                'pi': page,
                'ctype': 'long',
                'len': 60,
                '_': int(time.time() * 1000),
            }
            data = self.fetcher.get_json(API_HTML5, params=params)
            cmts = data.get('Cmts', []) if isinstance(data, dict) else []
            if not cmts:
                break
            review_ids.extend(str(item.get('CommentID', '')) for item in cmts if item.get('CommentID'))
            page += 1
        return review_ids

    def _download_vip_items(
        self,
        items: list[tuple[Section, Item]],
        dir_path: Path,
        ext: str = 'md',
        pbar=None,
        lock=None,
        tracker: ProgressTracker | None = None,
        task_id: str | None = None,
    ) -> list[dict]:
        from .vip import _vip_rate_limit, _validate_gif
        from urllib.parse import urlparse, parse_qs

        existing_stems = {gif.stem for gif in dir_path.rglob('*.gif')}

        pending_items = []
        for section, item in items:
            safe_section = _sanitize_filename(section.title)
            section_dir = dir_path / f'vol_{section.idx:03d}_{safe_section}'
            safe_title = _sanitize_filename(item.title)
            filename = f'ch_{item.idx:03d}_{safe_title}.{ext}' if safe_title else f'ch_{item.idx:03d}.{ext}'
            save_path = section_dir / filename
            gif_path = save_path.with_suffix('.gif')

            if gif_path.stem in existing_stems:
                if tracker and task_id:
                    tracker.mark_done(task_id, item.url)
                if pbar and lock:
                    with lock:
                        pbar.update(1)
                continue

            pending_items.append((section, item, save_path))

        if not pending_items:
            logger.info('所有VIP章节已下载')
            return []

        logger.info(f'VIP待下载: {len(pending_items)} 章')

        catalog_items = []

        for section, item, save_path in pending_items:
            gif_path = save_path.with_suffix('.gif')
            save_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                _vip_rate_limit()
                html = self.fetcher.get(item.url, timeout=(10, 20)).text
                soup = BeautifulSoup(html, 'html.parser')

                vip_img = soup.select_one('#vipImage')
                if not vip_img:
                    logger.warning(f'跳过(无订阅): {item.title}')
                    if tracker and task_id:
                        tracker.mark_failed(task_id, item.url, 'no subscription')
                    if pbar and lock:
                        with lock:
                            pbar.update(1)
                    continue

                src = vip_img.get('src', '')
                if src.startswith('/'):
                    src = PC_BASE + src

                gif_bytes = self.fetcher.get(src, timeout=(10, 30)).content

                expected_w = int(parse_qs(urlparse(src).query).get('w', [0])[0])
                valid, info = _validate_gif(gif_bytes, expected_w)
                if not valid:
                    raise AntiScrapingError(f'VIP GIF invalid: {info} ({src})')

                gif_path.write_bytes(gif_bytes)

                catalog_items.append({
                    'section_idx': section.idx,
                    'section_title': section.title,
                    'item_idx': item.idx,
                    'item_title': item.title,
                    'item_url': item.url,
                    'file': str(gif_path.relative_to(dir_path)),
                })
                if tracker and task_id:
                    tracker.mark_done(task_id, item.url)
                logger.info(f'VIP GIF: {gif_path.name} ({len(gif_bytes)} bytes)')

            except AntiScrapingError as e:
                logger.error(f'反爬检测，停止: {e}')
                if tracker and task_id:
                    tracker.mark_failed(task_id, item.url, str(e))
                raise
            except Exception as e:
                err_str = str(e)
                if 'timeout' in err_str.lower() or 'timed out' in err_str.lower():
                    logger.error(f'请求超时，停止: {e}')
                    if tracker and task_id:
                        tracker.mark_failed(task_id, item.url, f'timeout: {e}')
                    raise AntiScrapingError(f'Request timeout: {e}')
                logger.error(f'VIP Failed: {item.title} - {e}')
                if tracker and task_id:
                    tracker.mark_failed(task_id, item.url, str(e))

            if pbar and lock:
                with lock:
                    pbar.update(1)

        return sorted(catalog_items, key=lambda x: (x['section_idx'], x['item_idx']))

    def download_novel(
        self,
        path: str | Path = './',
        file_type: str = 'md',
        tracker: ProgressTracker | None = None,
        start_chapter: str | None = None,
        end_chapter: str | None = None,
        chapter_range: str | None = None,
        volume_filter: str | None = None,
        download_reviews: bool = False,
    ):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        if file_type not in ('txt', 'md', 'html', 'epub'):
            logger.error(f'不支持的格式: {file_type}')
            return

        primary_type = 'md' if file_type == 'epub' else file_type
        ext = primary_type

        sections = self.get_sections()
        sections = self._filter_sections(sections, start_chapter, end_chapter, chapter_range, volume_filter)

        all_items = []
        for section in sections:
            for item in section.get_items():
                all_items.append((section, item))

        if download_reviews:
            review_section = self._get_reviews()
            for item in review_section.get_items():
                all_items.append((review_section, item))

        if not all_items:
            logger.error('没有可下载的内容')
            return

        if tracker is None:
            tracker = ProgressTracker()

        normal_items = [(s, i) for s, i in all_items if not getattr(i, 'vip', False)]
        vip_items = [(s, i) for s, i in all_items if getattr(i, 'vip', False)]

        logger.bind(force=True).info(f'共 {len(all_items)} 项 (普通 {len(normal_items)}, VIP {len(vip_items)})')

        info_md, info_html = self.get_info()
        item_list = [{'url': i.url, 'title': i.title} for _, i in all_items]
        task_id = tracker.create_task('novel', self.title, self.nid, '', chapters=item_list)

        dir_path = path / _sanitize_filename(self.title)
        dir_path.mkdir(parents=True, exist_ok=True)

        existing_stems = set()
        for f in dir_path.rglob('*.md'):
            existing_stems.add(f.stem)
        for f in dir_path.rglob('*.gif'):
            existing_stems.add(f.stem)

        for section in sections:
            for item in section.get_items():
                safe_section = _sanitize_filename(section.title)
                section_dir = dir_path / f'vol_{section.idx:03d}_{safe_section}'
                safe_title = _sanitize_filename(item.title)
                ext_check = 'gif' if getattr(item, 'vip', False) else 'md'
                filename = f'ch_{item.idx:03d}_{safe_title}.{ext_check}' if safe_title else f'ch_{item.idx:03d}.{ext_check}'
                stem = Path(filename).stem
                if stem in existing_stems:
                    tracker.mark_done(task_id, item.url) if tracker else None

        dir_path = path / _sanitize_filename(self.title)
        dir_path.mkdir(parents=True, exist_ok=True)

        lock = threading.Lock()
        pbar = tqdm(total=len(all_items), desc=self.title, unit='task')

        catalog = {
            'nid': self.nid,
            'title': self.title,
            'author': self.author,
            'cover': self.cover,
            'intro': self.intro,
            'volumes': {},
            'chapters': [],
        }

        catalog['chapters'] = self._download_items(all_items, dir_path, ext, 'vol', 'ch', pbar, lock, tracker, task_id)

        for section in sections:
            if section.title not in catalog['volumes']:
                catalog['volumes'][section.title] = section.idx

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

        if file_type in ('txt', 'md'):
            single_content = self.assemble(dir_path, primary_type)
            single_path = path / f'{_sanitize_filename(self.title)}.{file_type}'
            single_path.write_text(single_content, encoding='utf-8')
            logger.bind(force=True).info(f'保存到 {single_path}')
        elif file_type == 'html':
            logger.bind(force=True).info(f'保存到 {dir_path}')
        elif file_type == 'epub':
            from .epub import convert_md_to_epub
            md_content = self.assemble(dir_path, 'md')
            convert_md_to_epub(md_content, self.title, self.author, self.intro, self.cover, path, fetcher=self.fetcher)
            logger.bind(force=True).info(f'保存到 {path / _sanitize_filename(self.title)}.epub')


def ocr_novel_gifs(nid: int, path: str | Path = './'):
    """OCR all VIP GIF files for a novel. Run after download_novel."""
    from .ocr_fast import ocr_gif as ocr_gif_fast

    path = Path(path)
    title_dirs = list(path.glob(f'*{nid}*'))
    if not title_dirs:
        logger.error(f'No novel directory found for nid={nid} in {path}')
        return
    novel_dir = title_dirs[0]

    gif_files = sorted(novel_dir.rglob('*.gif'))
    if not gif_files:
        logger.info('No GIF files found')
        return

    logger.info(f'Found {len(gif_files)} GIF files to OCR')

    for gif_path in gif_files:
        md_path = gif_path.with_suffix('.md')
        if md_path.exists():
            logger.info(f'Skip (already OCR): {gif_path.name}')
            continue

        logger.info(f'OCR: {gif_path.name}')
        try:
            gif_bytes = gif_path.read_bytes()
            text = ocr_gif_fast(gif_bytes)
            title = gif_path.stem
            md_path.write_text(f'### {title}\n\n{text}\n', encoding='utf-8')
            logger.info(f'  -> {len(text)} chars')
        except Exception as e:
            logger.error(f'  Failed: {e}')


if __name__ == '__main__':
    novel = Novel(43708)
    novel.download_novel(file_type='epub', download_reviews=True)
