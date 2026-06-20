import re
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Tag
from loguru import logger
from abc import ABC, abstractmethod
from .fetcher import Fetcher
from .selectors import Selectors, SelectorError
from .config import API_VIP_IMAGE, PC_BASE, MOBILE_BASE, VIP_IMAGE_WIDTH
from .vip import VipMode, process_vip_chapter


class Ch(ABC):

    def __init__(self, url: str = '', fetcher: Fetcher | None = None, selectors: Selectors | None = None):
        self.url = url
        self.title: str = ''
        self.fetcher = fetcher or Fetcher()
        self.sel = selectors or Selectors()

    def __repr__(self):
        return f'<{self.__class__.__name__}>'

    def _download(self, parent_dir: str | Path = './', file_type: str = 'md'):
        content = self.get_chapter_content()
        path = Path(parent_dir) / f'{self.title}.{file_type}'
        text = content[0] if file_type in ('md', 'txt') else content[1]
        path.write_text(text, encoding='utf-8')
        logger.bind(force=True).info(f'下载完成 {self.title}')

    def _soup(self) -> BeautifulSoup:
        html = self.fetcher.get_html(self.url)
        return BeautifulSoup(html, 'html.parser')

    def download(self, parent_dir: str | Path = './', file_type: str = 'md', force: bool = True) -> None:
        if force:
            self._download(parent_dir, file_type)

    def _parse_children(self, container: Tag) -> str:
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

    @abstractmethod
    def get_chapter_content(self) -> tuple[str, str]:
        pass


class MobileChapter(Ch):

    def get_chapter_content(self) -> tuple[str, str]:
        soup = self._soup()

        title_tag = soup.title
        if title_tag and ' - ' in title_tag.get_text():
            title = title_tag.get_text().split(' - ')[1]
        else:
            title = self.sel.find_text(soup, 'chapter_mobile', 'title', url=self.url) or '未知章节'
        self.title = title

        content_html = self.sel.find(soup, 'chapter_mobile', 'content_container', url=self.url)
        if content_html and content_html.has_attr('style'):
            del content_html['style']

        content_md = f'### {self.title}\n\n'
        if content_html:
            content_md += self._parse_children(content_html)

        content_md = content_md.lstrip()
        html_str = f'<div class="ch"><h3>{self.title}</h3>{str(content_html) if content_html else ""}</div>'
        return content_md, html_str


class PCChapter(Ch):

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


class VIPChapter(Ch):

    IMAGE_API_BASE = API_VIP_IMAGE

    def __init__(
        self,
        url: str = '',
        fetcher: Fetcher | None = None,
        selectors: Selectors | None = None,
        vip_mode: VipMode = VipMode.OCR,
        save_frames_dir: Path | None = None,
        llm_api_key: str = '',
        llm_base_url: str = '',
        llm_model: str = '',
    ):
        super().__init__(url, fetcher, selectors)
        self.vip_mode = vip_mode
        self.save_frames_dir = save_frames_dir
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model

    def _is_vip(self, soup: BeautifulSoup) -> bool:
        if soup.select_one('#vipImage'):
            return True
        for script in soup.find_all('script'):
            txt = script.string or ''
            if 'isVip' in txt and 'true' in txt:
                return True
        return False

    def _get_image_url(self, soup: BeautifulSoup) -> str | None:
        vip_img = self.sel.find(soup, 'chapter_vip', 'vip_image', url=self.url, required=False)
        if vip_img:
            src = vip_img.get('src', '')
            if src.startswith('/'):
                src = PC_BASE + src
            return src

        for script in soup.find_all('script'):
            txt = script.string or ''
            if 'getChapPic' in txt:
                match = re.search(r"['\"]([^'\"]*getChapPic[^'\"]*)['\"]", txt)
                if match:
                    src = match.group(1)
                    if src.startswith('/'):
                        src = PC_BASE + src
                    return src
        return None

    def _extract_chapter_ids(self, soup: BeautifulSoup) -> tuple[str, str]:
        novel_id, chapter_id = '', ''
        for script in soup.find_all('script'):
            txt = script.string or ''
            if 'novelID' in txt:
                m = re.search(r'var\s+novelID\s*=\s*(\d+)', txt)
                if m:
                    novel_id = m.group(1)
            if 'chapterID' in txt:
                m = re.search(r'var\s+chapterID\s*=\s*(\d+)', txt)
                if m:
                    chapter_id = m.group(1)
        return novel_id, chapter_id

    def _build_image_url(self, soup: BeautifulSoup) -> str:
        img_url = self._get_image_url(soup)
        if img_url:
            return img_url

        novel_id, chapter_id = self._extract_chapter_ids(soup)
        if novel_id and chapter_id:
            return f'{self.IMAGE_API_BASE}?op=getChapPic&tp=true&quick=true&cid={chapter_id}&nid={novel_id}&font=16&lang=&w={VIP_IMAGE_WIDTH}'

        raise SelectorError(
            page='chapter_vip', field='vip_image', selector='#vipImage',
            url=self.url, description='Cannot find VIP image URL or chapter IDs',
        )

    def get_chapter_content(self) -> tuple[str, str]:
        soup = self._soup()

        title_tag = self.sel.find(soup, 'chapter_vip', 'title', url=self.url, required=False)
        title = title_tag.get_text().strip() if title_tag else '未知章节'
        self.title = title

        other_info_tags = self.sel.find_all(soup, 'chapter_vip', 'meta_info', url=self.url, required=False)
        other_info = '\t'.join(tag.get_text() for tag in other_info_tags) if other_info_tags else ''

        img_url = self._build_image_url(soup)
        logger.info(f'VIP chapter [{self.vip_mode.value}]: {img_url}')

        text, frame_paths = process_vip_chapter(
            image_url=img_url,
            mode=self.vip_mode,
            save_dir=self.save_frames_dir,
            llm_api_key=self.llm_api_key,
            llm_base_url=self.llm_base_url,
            llm_model=self.llm_model,
            fetcher=self.fetcher,
        )

        if self.vip_mode == VipMode.RAW:
            img_tags = ''.join(f'<img src="{p}">' for p in frame_paths)
            md_imgs = '\n\n'.join(f'![frame_{i}]({p})' for i, p in enumerate(frame_paths))
            content_md = f'### {title}\n\n{other_info}\n\n{md_imgs}\n\n'
            content_html = f'<div class="ch"><h3>{title}</h3><p>{other_info}</p>{img_tags}</div>'
        elif text:
            content_md = f'### {title}\n\n{other_info}\n\n{text}\n\n'
            content_html = (
                f'<div class="ch"><h3>{title}</h3><p>{other_info}</p>'
                f'<p>{text.replace(chr(10), "<br>")}</p></div>'
            )
        else:
            content_md = f'### {title}\n\n{other_info}\n\n[VIP内容 - 提取失败]({img_url})\n\n'
            content_html = f'<div class="ch"><h3>{title}</h3><p>{other_info}</p><img src="{img_url}"></div>'

        return content_md, content_html


class Chapter(PCChapter):

    def __init__(
        self,
        url: str = '',
        fetcher: Fetcher | None = None,
        selectors: Selectors | None = None,
        vip_mode: VipMode = VipMode.OCR,
        save_frames_dir: Path | None = None,
        llm_api_key: str = '',
        llm_base_url: str = '',
        llm_model: str = '',
    ):
        super().__init__(url, fetcher, selectors)
        self.vip_mode = vip_mode
        self.save_frames_dir = save_frames_dir
        self.llm_api_key = llm_api_key
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model

    def get_chapter_content(self) -> tuple[str, str]:
        if 'book' not in self.url:
            chapter = MobileChapter(self.url, self.fetcher, self.sel)
            content = chapter.get_chapter_content()
            self.title = chapter.title
            return content

        soup = self._soup()
        vip_ch = VIPChapter(
            url=self.url,
            fetcher=self.fetcher,
            selectors=self.sel,
            vip_mode=self.vip_mode,
            save_frames_dir=self.save_frames_dir,
            llm_api_key=self.llm_api_key,
            llm_base_url=self.llm_base_url,
            llm_model=self.llm_model,
        )
        if vip_ch._is_vip(soup):
            logger.info(f'VIP chapter detected: {self.url}')
            content = vip_ch.get_chapter_content()
            self.title = vip_ch.title
            return content

        chapter = PCChapter(self.url, self.fetcher, self.sel)
        content = chapter.get_chapter_content()
        self.title = chapter.title
        return content


if __name__ == '__main__':
    url = f'{MOBILE_BASE}/c/9200838/'
    chapter = Chapter(url=url)
    text = chapter.get_chapter_content()
    chapter.download(file_type='html')
