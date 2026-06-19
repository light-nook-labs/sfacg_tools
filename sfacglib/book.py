import re
from pathlib import Path
from bs4 import BeautifulSoup, Tag
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from .fetcher import Fetcher
from .selectors import Selectors
from .ch import Chapter
from .epub import download_epub
from .config import URL_NOVEL_INDEX, URL_NOVEL_MENU, MOBILE_BASE, WORKERS_CHAPTER
from .progress import ProgressTracker, _extract_id
from .utils import parse_volume_ul, mobile_url


class Volume:

    def __init__(self, vol_tag: Tag, fetcher: Fetcher | None = None, selectors: Selectors | None = None):
        self.title: str = vol_tag.string or '未命名卷'
        self.vol_tag: Tag | None = parse_volume_ul(vol_tag)
        self.fetcher = fetcher or Fetcher()
        self.sel = selectors or Selectors()

    def __repr__(self):
        return f'<Volume({self.title})>'

    def _get_chapters(self, chapter_dict: dict[str, str]) -> tuple[str, str]:
        parts_md: list[str] = []
        parts_html: list[str] = []
        futures = []
        with ThreadPoolExecutor(max_workers=WORKERS_CHAPTER) as executor:
            for _, chapter_url in chapter_dict.items():
                chapter = Chapter(chapter_url, self.fetcher, self.sel)
                futures.append(executor.submit(chapter.get_chapter_content))

            for future in tqdm(as_completed(futures), total=len(futures), desc=self.title, leave=False):
                try:
                    md, html = future.result()
                    parts_md.append(md)
                    parts_html.append(html)
                except Exception as e:
                    logger.error(f'Chapter failed: {e}')
        return '\n\n'.join(parts_md) + '\n\n', ''.join(parts_html)

    def get_volume_content(self) -> tuple[str, str]:
        logger.info(self.title)
        volume_md = f'## {self.title}\n\n'
        volume_html = f'<div class="vol"><h2>{self.title}</h2>'

        chapters: dict[str, str] = {}
        if self.vol_tag:
            chapter_links = self.sel.find_all(self.vol_tag, 'novel_menu', 'chapter_links', required=False)
            if chapter_links:
                for a_tag in chapter_links:
                    href = a_tag.get('href', '')
                    if href:
                        chapters[a_tag.get_text()] = mobile_url(href)
            else:
                for a_tag in self.vol_tag.find_all('a'):
                    href = a_tag.get('href', '')
                    if href:
                        chapters[a_tag.get_text()] = mobile_url(href)

        md, html = self._get_chapters(chapters)
        return volume_md + md, volume_html + html + '</div>'


class Novel:

    def __init__(self, nid: int, fetcher: Fetcher | None = None, selectors: Selectors | None = None):
        self.nid = str(nid)
        self.title: str = ''
        self.author: str = ''
        self.intro: str = ''
        self.cover: str = ''
        self.fetcher = fetcher or Fetcher()
        self.sel = selectors or Selectors()

    def get_novel_info(self) -> tuple[str, str]:
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
        info_html = f"""
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
        """
        return info_md, info_html

    def _get_volume_tags(self) -> list[Tag]:
        menu_url = f'{URL_NOVEL_MENU}{self.nid}'
        html = self.fetcher.get_html(menu_url)
        soup = BeautifulSoup(html, 'html.parser')
        volume_tags = self.sel.find_all(soup, 'novel_menu', 'volume_tags', url=menu_url, required=False)
        if not volume_tags:
            volume_tags = soup.find_all(class_='mulu')
        return volume_tags

    def _collect_chapters(self) -> list[tuple[str, str, str]]:
        volume_tags = self._get_volume_tags()
        chapters: list[tuple[str, str, str]] = []
        for vol_tag in volume_tags:
            vol_title = vol_tag.string or '未命名卷'
            ul_tag = parse_volume_ul(vol_tag)
            if ul_tag:
                for a in ul_tag.find_all('a'):
                    href = a.get('href', '')
                    if href:
                        chapters.append((vol_title, a.get_text(), mobile_url(href)))
        return chapters

    def get_novel_content(self, tracker: ProgressTracker | None = None) -> tuple[str, str]:
        info_md, info_html = self.get_novel_info()
        all_chapters = self._collect_chapters()

        chapter_list = [{'url': ch_url, 'title': ch_title} for _, ch_title, ch_url in all_chapters]
        task_id = tracker.create_task('novel', self.title, self.nid, '', chapters=chapter_list) if tracker else None

        pending_cids = set(ch['cid'] for ch in (tracker.get_pending(task_id) if tracker and task_id else []))
        done_count = tracker.get_done_count(task_id) if tracker and task_id else 0
        total = len(all_chapters)

        if pending_cids:
            logger.bind(force=True).info(f'恢复下载: 已完成 {done_count}/{total}，剩余 {len(pending_cids)}')

        results: dict[str, list[tuple[str, str]]] = {}
        with ThreadPoolExecutor(max_workers=WORKERS_CHAPTER) as executor:
            futures = {}
            for vol_title, ch_title, ch_url in all_chapters:
                ch_cid = _extract_id(ch_url)
                if ch_cid in pending_cids or not pending_cids:
                    ch = Chapter(ch_url, self.fetcher, self.sel)
                    futures[executor.submit(ch.get_chapter_content)] = (vol_title, ch_title, ch_url)

            for future in tqdm(as_completed(futures), total=len(futures), desc='Chapters', initial=done_count):
                vol_title, ch_title, ch_url = futures[future]
                try:
                    md, html = future.result()
                    results.setdefault(vol_title, []).append((md, html))
                    if tracker and task_id:
                        tracker.mark_done(task_id, ch_url)
                except Exception as e:
                    logger.error(f'Failed: {ch_title} - {e}')
                    if tracker and task_id:
                        tracker.mark_failed(task_id, ch_url, str(e))

        if tracker and task_id:
            tracker.mark_task_done(task_id)
            pending = tracker.get_pending(task_id)
            if not pending:
                tracker.delete_task(task_id)
                logger.bind(force=True).info(f'任务完成，已清理记录: {task_id}')
            else:
                logger.warning(f'任务有 {len(pending)} 个失败章节，保留记录')

        content_md = info_md
        content_html = info_html

        vol_order = []
        for vol_title, _, _ in all_chapters:
            if vol_title not in vol_order:
                vol_order.append(vol_title)

        for vol_title in vol_order:
            content_md += f'## {vol_title}\n\n'
            content_html += f'<div class="vol"><h2>{vol_title}</h2>'
            for md, html in results.get(vol_title, []):
                content_md += md
                content_html += html
            content_md += '\n\n'
            content_html += '</div>'

        soup = BeautifulSoup(content_html, 'html.parser')
        return content_md, soup.prettify()

    def download_novel(self, path: str | Path = './', file_type: str = 'md', tracker: ProgressTracker | None = None):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        novel_content = self.get_novel_content(tracker=tracker)
        if file_type in ('txt', 'md'):
            content = novel_content[0]
        elif file_type in ('html', 'epub'):
            content = novel_content[1]
            if file_type == 'epub':
                download_epub(content, self.title, self.author, self.intro, self.cover, path, fetcher=self.fetcher)
                return
        else:
            logger.error(f'不支持的格式: {file_type}')
            return

        file_path = path / f'{self.title}-{self.author}.{file_type}'
        file_path.write_text(content, encoding='utf-8')
        logger.bind(force=True).info(f'保存到 {file_path}')


if __name__ == '__main__':
    novel = Novel(43708)
    novel.download_novel(file_type='epub')
