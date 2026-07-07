import re
import time
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag
from loguru import logger

from .base import Container, InvalidNovelError, Item, Section
from .config import (
    API_HTML5,
    API_VIP_IMAGE,
    PC_BASE,
    URL_NOVEL_INDEX,
    URL_REVIEW_DETAIL,
    VIP_IMAGE_WIDTH,
    VIP_RETRY_DELAYS,
)
from .fetcher import Fetcher
from .selectors import Selectors
from .utils import fix_url_protocol, save_json, validate_gif
from .utils import sanitize_filename as _sanitize_filename

ICN_IMG = '\ue905'


def _chapter_url(novel_id: str, vol_id: str, chapter_id: str, is_gif: bool) -> str:
    if is_gif:
        return f'{PC_BASE}/vip/c/{chapter_id}/'
    return f'{PC_BASE}/Novel/{novel_id}/{vol_id}/{chapter_id}/'


class NovelChapter(Item):
    def __init__(
        self,
        idx: int,
        title: str,
        chapter_id: str,
        fetcher: Fetcher,
        sel: Selectors,
        novel_id: str,
        vol_id: str,
        is_gif: bool = False,
    ):
        url = _chapter_url(novel_id, vol_id, chapter_id, is_gif)
        super().__init__(idx, title, url)
        self.chapter_id = chapter_id
        self.fetcher = fetcher
        self.sel = sel
        self.novel_id = novel_id
        self.vol_id = vol_id
        self.is_gif = is_gif

    def download(self, save_path: Path, pbar=None, lock=None):
        if save_path.exists() or save_path.with_suffix('.gif').exists():
            logger.debug(f'Skip existing: {save_path.name}')
        elif self.is_gif:
            self._download_vip_gif(save_path)
        else:
            self._download_normal(save_path)
        if pbar and lock:
            with lock:
                pbar.update(1)

    def _download_normal(self, save_path: Path):
        md, _html = self.get_chapter_content()
        save_path.write_text(md, encoding='utf-8')

    def _download_vip_gif(self, save_path: Path):
        gif_path = save_path.with_suffix('.gif')
        src = f'{API_VIP_IMAGE}?op=getChapPic&tp=true&quick=true&cid={self.chapter_id}&nid={self.novel_id}&font=16&lang=&w={VIP_IMAGE_WIDTH}'

        gif_bytes = b''
        for attempt in range(1 + len(VIP_RETRY_DELAYS)):
            if attempt > 0:
                delay = VIP_RETRY_DELAYS[attempt - 1]
                logger.warning(f'VIP retry {attempt}/{len(VIP_RETRY_DELAYS)} after {delay}s...')
                time.sleep(delay)

            self.fetcher.auth_rate_limiter.wait('vip.sfacg.com')
            resp = self.fetcher.get(src, headers={'Referer': self.url}, timeout=(10, 30), vip=True)
            gif_bytes = resp.content

            valid, info = validate_gif(gif_bytes, VIP_IMAGE_WIDTH)
            if valid:
                logger.info(f'VIP GIF OK: {info}')
                break
            logger.warning(f'VIP GIF invalid ({info}), retrying...')

        valid, info = validate_gif(gif_bytes, VIP_IMAGE_WIDTH)
        if not valid:
            raise ValueError(f'VIP GIF invalid (not subscribed?): {info} ({self.url})')

        gif_path.write_bytes(gif_bytes)
        logger.info(f'VIP GIF: {gif_path.name} ({len(gif_bytes)} bytes)')

    def get_chapter_content(self) -> tuple[str, str]:
        soup = self._soup()

        self.sel.find(soup, 'chapter_pc', 'header', url=self.url)
        title_tag = self.sel.find(soup, 'chapter_pc', 'title', url=self.url)
        title = title_tag.get_text().strip() if title_tag else '未知章节'
        self.title = title

        other_info_tags = self.sel.find_all(soup, 'chapter_pc', 'meta_info', url=self.url, required=False)
        other_info = '\t'.join(tag.get_text() for tag in other_info_tags) if other_info_tags else ''

        content_tag = self.sel.find(soup, 'chapter_pc', 'content', url=self.url)
        if content_tag:
            for attr in ('class', 'data-class', 'id'):
                content_tag.attrs.pop(attr, None)

        content_html = f'<h3>{title}</h3><p>{other_info}</p>{str(content_tag) if content_tag else ""}'
        content_md = f'### {title}\n\n{other_info}\n\n'

        if content_tag:
            content_md += self._parse_children(content_tag)

        return content_md, f'<div class="ch">{content_html}</div>'

    def _soup(self) -> BeautifulSoup:
        html = self.fetcher.get_html(self.url)
        return BeautifulSoup(html, 'html.parser')

    @staticmethod
    def _parse_children(container: Tag) -> str:
        md = ''
        for child in container.children:
            if isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    md += f'{text}\n\n'
            elif isinstance(child, Tag):
                if child.name == 'img':
                    src = child.get('src', '')
                    md += f'![]({src})\n\n'
                elif child.name == 'p':
                    md += f'{child.get_text().strip()}\n\n'
                elif child.name == 'br':
                    continue
        return md


class NovelVolume(Section):
    def __init__(self, idx: int, title: str, vol_id: str, chapters: list[NovelChapter]):
        super().__init__(idx, title)
        self.vol_id = vol_id
        self.chapters = chapters

    def get_items(self) -> list[NovelChapter]:
        return self.chapters

    def download(
        self,
        dir_path: Path,
        ext: str = 'md',
        item_prefix: str = 'ch',
        pbar=None,
        lock=None,
        executor=None,
    ):
        super().download(dir_path, ext=ext, item_prefix=item_prefix, pbar=pbar, lock=lock, executor=executor)


class ReviewComment(Item):
    def __init__(self, idx: int, cid: str, title: str, fetcher: Fetcher, sel: Selectors | None = None):
        super().__init__(idx, title, f'{URL_REVIEW_DETAIL}{cid}/')
        self.cid = cid
        self.fetcher = fetcher
        self.sel = sel or Selectors()

    def download(self, save_path: Path, pbar=None, lock=None):
        html = self.fetcher.get_html(self.url)
        soup = BeautifulSoup(html, 'html.parser')

        title_tag = self.sel.find(soup, 'review_detail', 'title', url=self.url, required=False)
        title = ''
        if title_tag:
            title = title_tag.string.removesuffix('-书评详情-SF轻小说手机版') if title_tag.string else ''

        content_tag = self.sel.find(soup, 'review_detail', 'content', url=self.url, required=False)
        content = content_tag.get_text().strip() if content_tag else ''

        date = ''
        date_container = self.sel.find(soup, 'review_detail', 'date_container', url=self.url, required=False)
        if date_container and date_container.span:
            match = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', date_container.span.get_text())
            if match:
                date = match.group()

        replies_num, praise_num = '0', '0'
        interactions = self.sel.find(soup, 'review_detail', 'interactions', url=self.url, required=False)
        if interactions:
            parts = interactions.get_text().split()
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


class Review(Container):
    def __init__(
        self,
        nid: int,
        title: str,
        output_dir: str | Path,
        fetcher: Fetcher,
    ):
        self.nid = str(nid)
        super().__init__(output_dir=output_dir, fetcher=fetcher)
        self.title = title
        self.id = self.nid
        self.author = ''
        self.intro = f'《{self.title}》的书评'
        self.cover = ''

        if not self.setup():
            raise InvalidNovelError(f'获取书评列表失败 (nid={nid})')

    def setup(self) -> bool:
        try:
            self.dir_path = self.output_dir / _sanitize_filename(f'{self.title}_reviews')
            self.dir_path.mkdir(parents=True, exist_ok=True)

            info_md = f"""# 《{self.title}》书评

有声小说地址：{URL_NOVEL_INDEX}{self.nid}
"""
            (self.dir_path / 'info.md').write_text(info_md, encoding='utf-8')

            review_ids = self._get_review_ids()
            if not review_ids:
                logger.warning(f'未找到书评: {self.title}')
                return True

            sections = []
            for idx, cid in enumerate(reversed(review_ids), start=1):
                safe_title = _sanitize_filename(self.title)
                sections.append(
                    {
                        'idx': idx,
                        'title': f'书评_{idx}',
                        'cid': cid,
                        'file': f'review_{idx:03d}_{safe_title}.md',
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

    def get_download_items(self) -> list[tuple[None, ReviewComment]]:
        catalog = self._load_catalog()
        items = []
        for sec in catalog.get('sections', []):
            items.append(
                (
                    None,
                    ReviewComment(
                        idx=sec['idx'],
                        cid=sec['cid'],
                        title=self.title,
                        fetcher=self.fetcher,
                    ),
                )
            )
        return items

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


class Novel(Container):
    def __init__(
        self,
        nid: int,
        output_dir: str | Path | None = None,
        fetcher: Fetcher | None = None,
        selectors: Selectors | None = None,
    ):
        super().__init__(output_dir, fetcher)
        self.nid = str(nid)
        self.id = str(nid)
        self.sel = selectors or Selectors()

        if not self.setup():
            raise InvalidNovelError(f'HTTP错误或URL无效 (nid={nid})')

    def download(self, ext: str = 'md'):
        super().download(ext=ext, item_prefix='ch')

    def setup(self) -> bool:
        try:
            html = self.fetcher.get_html(f'{URL_NOVEL_INDEX}{self.nid}')
            soup = BeautifulSoup(html, 'html.parser')

            self.sel.find(soup, 'novel_info', 'container', url=f'{URL_NOVEL_INDEX}{self.nid}')
            title = self.sel.find_text(soup, 'novel_info', 'title', url=f'{URL_NOVEL_INDEX}{self.nid}') or '未知小说'
            self.title = title

            cover_url = self.sel.find_attr(soup, 'novel_info', 'cover', url=f'{URL_NOVEL_INDEX}{self.nid}') or ''
            self.cover = fix_url_protocol(cover_url)

            stats_text = self.sel.find_text(soup, 'novel_info', 'stats', url=f'{URL_NOVEL_INDEX}{self.nid}') or ''
            stats_parts = stats_text.split(' / ')
            self.author = stats_parts[0].strip() if stats_parts else '未知'

            intro = self.sel.find_text(soup, 'novel_info', 'introduction', url=f'{URL_NOVEL_INDEX}{self.nid}') or ''
            intro = '\n\n'.join(line.strip() for line in intro.split('\n\n'))

            self.dir_path = self.output_dir / _sanitize_filename(self.title)
            self.dir_path.mkdir(parents=True, exist_ok=True)

            cover_file = self._download_cover()

            info_md = f"""# {title}-{self.author}

## 小说信息

Generated by [SFACG Spider](https://github.com/light-nook-labs/sfacg)

![封面]({self.cover})

原文地址：{URL_NOVEL_INDEX}{self.nid}

作者：{self.author}

{intro}

{'=' * 20}
"""
            (self.dir_path / 'info.md').write_text(info_md, encoding='utf-8')

            html = self.fetcher.get_html(f'{PC_BASE}/Novel/{self.nid}/MainIndex/')
            soup = BeautifulSoup(html, 'html.parser')

            self.sel.find(soup, 'novel_pc_index', 'volume_headers', url=f'{PC_BASE}/Novel/{self.nid}/MainIndex/')

            sections = []
            vol_idx = 0
            for hd in self.sel.find_all(soup, 'novel_pc_index', 'volume_headers'):
                vol_idx += 1
                vol_title_tag = self.sel.find(hd, 'novel_pc_index', 'volume_title', required=False)
                vol_title = vol_title_tag.get_text().strip() if vol_title_tag else '未命名卷'

                vol_id = ''
                for sib in hd.next_siblings:
                    if not hasattr(sib, 'name') or not sib.name:
                        continue
                    sib_class = sib.get('class', [])
                    if 'catalog-hd' in sib_class:
                        break
                    if 'catalog-list' not in sib_class:
                        continue

                    for a in self.sel.find_all(sib, 'novel_pc_index', 'chapter_links'):
                        href = a.get('href', '')
                        if not href:
                            continue

                        if not vol_id:
                            m = re.search(r'/Novel/\d+/(\d+)/', href)
                            if m:
                                vol_id = m.group(1)

                        break
                    break

                items = []
                ch_idx = 0
                for sib in hd.next_siblings:
                    if not hasattr(sib, 'name') or not sib.name:
                        continue
                    sib_class = sib.get('class', [])
                    if 'catalog-hd' in sib_class:
                        break
                    if 'catalog-list' not in sib_class:
                        continue

                    for a in self.sel.find_all(sib, 'novel_pc_index', 'chapter_links'):
                        href = a.get('href', '')
                        if not href:
                            continue
                        ch_idx += 1

                        chapter_id = ''
                        m = re.search(r'/(\d+)/?$', href)
                        if m:
                            chapter_id = m.group(1)

                        is_vip = self.sel.find(a, 'novel_pc_index', 'vip_badge', required=False) is not None
                        icn_tag = self.sel.find(a, 'novel_pc_index', 'image_badge', required=False)
                        has_img = icn_tag is not None and icn_tag.get_text() == ICN_IMG
                        title = a.get('title', '') or a.get_text().replace('VIP', '').strip()

                        is_gif = is_vip and not has_img

                        safe_title = _sanitize_filename(title)
                        file = f'sec_{vol_idx:03d}_{_sanitize_filename(vol_title)}/ch_{ch_idx:03d}_{safe_title}.md'

                        items.append(
                            {
                                'idx': ch_idx,
                                'title': title,
                                'chapter_id': chapter_id,
                                'is_gif': is_gif,
                                'file': file,
                            }
                        )

                sections.append(
                    {
                        'idx': vol_idx,
                        'title': vol_title,
                        'vol_id': vol_id,
                        'dir': f'sec_{vol_idx:03d}_{_sanitize_filename(vol_title)}',
                        'items': items,
                    }
                )

            catalog = {
                'id': self.id,
                'title': self.title,
                'author': self.author,
                'cover': self.cover,
                'cover_file': cover_file,
                'info_file': 'info.md',
                'sections': sections,
            }
            save_json(catalog, self.dir_path / 'catalog.json')

            return True
        except Exception as e:
            logger.error(f'Setup failed: {e}')
            return False

    def get_download_items(self) -> list[tuple[NovelVolume, NovelChapter]]:
        catalog = self._load_catalog()
        items = []
        for sec in catalog.get('sections', []):
            chapters = []
            for item in sec.get('items', []):
                chapters.append(
                    NovelChapter(
                        idx=item['idx'],
                        title=item['title'],
                        chapter_id=item['chapter_id'],
                        fetcher=self.fetcher,
                        sel=self.sel,
                        novel_id=self.nid,
                        vol_id=sec['vol_id'],
                        is_gif=item.get('is_gif', False),
                    )
                )
            volume = NovelVolume(sec['idx'], sec['title'], sec['vol_id'], chapters)
            for chapter in chapters:
                items.append((volume, chapter))
        return items

    def create_vol(self, idx: int) -> NovelVolume | None:
        for volume in self.get_download_items():
            if volume.idx == idx:
                return volume
        return None

    def create_review(self) -> Review:
        return Review(
            nid=int(self.nid),
            title=self.title,
            output_dir=self.dir_path,
            fetcher=self.fetcher,
        )

    @classmethod
    def ocr_novel_gifs(cls, nid: int, path: str | Path = './'):
        from .ocr import ocr_gif

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
                text = ocr_gif(gif_bytes)
                title = gif_path.stem
                md_path.write_text(f'### {title}\n\n{text}\n', encoding='utf-8')
                logger.info(f'  -> {len(text)} chars')
            except Exception as e:
                logger.error(f'  Failed: {e}')
