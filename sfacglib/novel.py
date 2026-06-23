import re
import time
import threading
from pathlib import Path
from bs4 import BeautifulSoup, Tag
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from .fetcher import Fetcher
from .selectors import Selectors
from .ch import Chapter, PCChapter, _validate_gif
from .base import Container, Section, Item, _sanitize_filename, AntiScrapingError
from .config import (
    URL_NOVEL_INDEX, URL_NOVEL_MENU, MOBILE_BASE, PC_BASE, WORKERS_CHAPTER,
    URL_REVIEW_LIST, URL_REVIEW_DETAIL, API_HTML5, API_VIP_IMAGE, VIP_IMAGE_WIDTH,
)
from .progress import ProgressTracker, _extract_id
from .utils import parse_volume_ul, mobile_url, fix_url_protocol
from .models import Catalog, CatalogSection, CatalogItem

ICN_IMG = '\ue905'


class NovelChapter(Item):

    def __init__(self, idx: int, title: str, url: str, fetcher: Fetcher, sel: Selectors,
                 nid: str = '', vip: bool = False):
        super().__init__(idx, title, url)
        self.fetcher = fetcher
        self.sel = sel
        self.nid = nid
        self.vip = vip

    def download(self, save_path: Path, pbar=None, lock=None):
        if save_path.exists() or save_path.with_suffix('.gif').exists():
            logger.debug(f'Skip existing: {save_path.name}')
        elif self.vip:
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
        gif_path = save_path.with_suffix('.gif')
        cid = _extract_id(self.url)
        src = f'{API_VIP_IMAGE}?op=getChapPic&tp=true&quick=true&cid={cid}&nid={self.nid}&font=16&lang=&w={VIP_IMAGE_WIDTH}'

        gif_bytes = self.fetcher.get(src, headers={'Referer': self.url}, timeout=(10, 30)).content

        valid, info = _validate_gif(gif_bytes, VIP_IMAGE_WIDTH)
        if not valid:
            raise ValueError(f'VIP GIF invalid (not subscribed?): {info} ({self.url})')

        gif_path.write_bytes(gif_bytes)
        logger.info(f'VIP GIF: {gif_path.name} ({len(gif_bytes)} bytes)')


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
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(msg)

        if pbar and lock:
            with lock:
                pbar.update(1)

    def _get_replies(self, max_pages: int = 100) -> str:
        page = 0
        replies: list[str] = []
        while page < max_pages:
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


def _parse_pc_catalog(soup: BeautifulSoup, fetcher: Fetcher, sel: Selectors, nid: str) -> list[NovelVolume]:
    volumes: list[NovelVolume] = []
    vol_idx = 0

    for hd in soup.select('.catalog-hd'):
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
            if 'catalog-list' not in str(sib.get('class', '')):
                continue

            for a in sib.select('a[href]'):
                href = a.get('href', '')
                if not href:
                    continue
                ch_idx += 1
                is_vip = a.select_one('.icn_vip') is not None
                has_img = a.select_one('.icn') and a.select_one('.icn').get_text() == ICN_IMG
                title = a.get('title', '') or a.get_text().replace('VIP', '').strip()

                if href.startswith('/'):
                    url = f'{PC_BASE}{href}'
                else:
                    url = mobile_url(href)

                chapters.append(NovelChapter(
                    ch_idx, title, url, fetcher, sel,
                    nid=nid, vip=is_vip and not has_img,
                ))

        volumes.append(NovelVolume(vol_idx, vol_title, chapters))

    return volumes


def _parse_mobile_catalog(soup: BeautifulSoup, fetcher: Fetcher, sel: Selectors, nid: str) -> list[NovelVolume]:
    volumes: list[NovelVolume] = []
    vol_idx = 0

    for vol_tag in soup.find_all(class_='mulu'):
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
                        ch_idx, a.get_text(), mobile_url(href), fetcher, sel,
                        nid=nid,
                    ))
        volumes.append(NovelVolume(vol_idx, vol_title, chapters))

    return volumes


class Novel(Container):

    def __init__(
        self,
        nid: int,
        fetcher: Fetcher | None = None,
        selectors: Selectors | None = None,
    ):
        super().__init__(fetcher)
        self.nid = str(nid)
        self.id = str(nid)
        self.title: str = ''
        self.author: str = ''
        self.intro: str = ''
        self.cover: str = ''
        self.sel = selectors or Selectors()
        self.fetcher.auto_auth()

    def get_info(self) -> tuple[str, str]:
        index_url = f'{URL_NOVEL_INDEX}{self.nid}'
        logger.info(index_url)
        html = self.fetcher.get_html(index_url)
        soup = BeautifulSoup(html, 'html.parser')

        self.sel.find(soup, 'novel_info', 'container', url=index_url)
        title = self.sel.find_text(soup, 'novel_info', 'title', url=index_url) or '未知小说'
        self.title = title

        cover_url = self.sel.find_attr(soup, 'novel_info', 'cover', url=index_url) or ''
        cover_url = fix_url_protocol(cover_url)
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

Generated by [SFACG Spider](https://github.com/light-nook-labs/sfacg)

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
<p>Generated by <a href="https://github.com/light-nook-labs/sfacg">SFACG Spider</a></p>
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

        if soup.select('.catalog-hd'):
            return _parse_pc_catalog(soup, self.fetcher, self.sel, self.nid)

        menu_url = f'{URL_NOVEL_MENU}{self.nid}'
        html = self.fetcher.get_html(menu_url)
        soup = BeautifulSoup(html, 'html.parser')
        return _parse_mobile_catalog(soup, self.fetcher, self.sel, self.nid)

    def _get_reviews(self) -> ReviewSection:
        review_ids = self._get_review_ids()
        comments = []
        for idx, cid in enumerate(reversed(review_ids), start=1):
            comments.append(ReviewComment(idx, cid, self.title, self.fetcher))
        return ReviewSection(1, '长评', comments)

    def _get_review_ids(self, max_pages: int = 100) -> list[str]:
        page = 0
        review_ids: list[str] = []
        while page < max_pages:
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


def ocr_novel_gifs(nid: int, path: str | Path = './'):
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
    novel.download(file_type='epub')
