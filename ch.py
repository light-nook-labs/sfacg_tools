from time import sleep
import requests
from requests.exceptions import HTTPError
from bs4 import BeautifulSoup, NavigableString, Tag
from loguru import logger
from abc import ABC, abstractmethod
import os.path

HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

class Ch(ABC):
    """处理章节
    Args:
        title: str 小说标题
        url: str 小说url
    """

    def __init__(self, title: str='未命名章节', url: str=''):
        self.url = url
        self.title = title
        self.headers = HEADERS
        self.failed = False

    def __repr__(self):
        return f'{self.__class__.__name__}(title="{self.title}", url="{self.url}")'

    def _check_url(self):
        """检查URL是否为有效的移动端章节URL"""
        # 如果URL为空，或者不以下列任一前缀开头，则视为无效
        if not self.url:
            return True  # URL为空，视为无效

        # 检查是否以指定的HTTPS或HTTP前缀开头
        return not self.url.startswith(self.url_prefixes)

    def _download(self, path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.get_chapter_content())
            logger.info(f'下载完成 {self.title} {self.url}')

    def _soup(self, format: str) -> BeautifulSoup:
        """发送i请求"""
        if self._check_url():
            logger.error('URL无效')
            return
        if format not in ('md', 'html', 'both'):
            logger.error('format无效')
            return
        try:
            response = requests.get(self.url, headers=self.headers)
            response.raise_for_status()
            logger.info(f'{self.title} {self.url}')
        except HTTPError as e:
            self.failed = True
            logger.error(f'{self.title} {self.url}')
            return str(e)
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup

    def download_md(self, path: str='./', force: bool=True) -> None:
        md_path = f'{path}/{self.title}.md'
        # ex = os.path.exists(md_path)
        # print(ex)
        if force:
            if ex:
                logger.warning(f'{md_path}已存在，将被覆写')
            self._download(md_path)
        else:
            if ex:
                logger.warning(f'{md_path}已存在，下载失败')
            else:
                self._download(md_path)

    @abstractmethod
    def get_chapter_content(self, format: str='md') -> str | tuple[str] | None:
        pass


class MobileChapter(Ch):
    """处理移动端章节
    Args:
        title: str 小说标题
        url: str 小说url
    """

    def __init__(self, title: str='未命名章节', url: str=''):
        super().__init__(title, url)
        self.url_prefixes = (
            'https://m.sfacg.com/c/',
            'http://m.sfacg.com/c/'
        )

    def get_chapter_content(self, format: str='md') -> str | tuple[str] | None:
        """获取章节内容

        Args:
            format: str 解析格式，可选值如下：

                - 'md' 返回markdown格式的字符串
                - 'html' 返回html格式的字符串，便于ebooklib解析
                - 'both' 返回元组
        """
        sleep(0.2)
        soup = self._soup(format)
        content_html = soup.div.div
        if format == 'html':
            del content_html['style']
            return f'<h3>{self.title}</h3>' + str(content_html)
        content_md = f'### {self.title}\n\n'
        for child in content_html.children:
            if type(child) == NavigableString and str(child).strip() != '':
                content_md += f"{str(child).strip()}\n\n"
            elif type(child) == Tag and child.name == "img":
                content_md += f"![]({child['src']})\n\n"
            elif type(child) == Tag and child.name == "p":
                content_md += f"{child.get_text().strip()}\n\n"
            elif type(child) == Tag and child.name == "br":
                continue
        content_md = content_md.lstrip()
        if format == 'md':
            return content_md
        if format == 'both':
            return content_md, content_html
        return


class PCChapter(Ch):
    """处理PC端章节
    Args:
        title: str 小说标题
        url: str 小说url
    """

    def __init__(self, title: str='未命名章节', url: str=''):
        super().__init__(title, url)
        self.url_prefixes = (
            'https://book.sfacg.com/Novel/',
            'http://book.sfacg.com/Novel/'
        )

    def get_chapter_content(self, format: str='md') -> str | tuple[str] | None:
        """获取章节内容"""
        sleep(0.2)
        soup = self._soup(format)
        info_tag = soup.find(class_='article-hd')
        title = info_tag.find('h1').get_text().strip()
        other_info_tags = info_tag.find_all(class_='text')
        other_info = '\t'.join(other_info_tag.get_text() for other_info_tag in other_info_tags)
        content_tag = soup.find(id='ChapterBody')
        del content_tag['class'], content_tag['data-class'], content_tag['id']
        content_html = f'<h3>{title}</h3><p>{other_info}</p>{str(content_tag)}'
        if format == 'html':
            return content_html
        content_md = f'### {title}\n\n{other_info}\n\n'
        for child_tag in content_tag.children:
            if type(child_tag) == NavigableString and str(child_tag).strip() != '':
                content_md += f"{str(child_tag).strip()}\n\n"
            elif type(child_tag) == Tag and child_tag.name == "img":
                content_md += f"![]({child_tag['src']})\n\n"
            elif type(child_tag) == Tag and child_tag.name == "p":
                content_md += f"{child_tag.get_text().strip()}\n\n"
            elif type(child_tag) == Tag and child_tag.name == "br":
                continue
        if format == 'md':
            return content_md
        if format == 'both':
            return content_md, content_html


class Chapter(Ch):
    """处理PC端章节
    Args:
        title: str 小说标题
        url: str 小说url
    """

    def __init__(self, title: str = '未命名章节', url: str = ''):
        super().__init__(title, url)
        self.url_prefixes = (
            'https://m.sfacg.com/c/',
            'http://m.sfacg.com/c/',
            'https://book.sfacg.com/Novel/',
            'http://book.sfacg.com/Novel/'
        )
        self.pc_url_prefixes = (
            'https://book.sfacg.com/Novel/',
            'http://book.sfacg.com/Novel/',
        )
        self.m_url_prefixes = (
            'https://m.sfacg.com/c/',
            'http://m.sfacg.com/c/',
        )

    def _check_device(self) -> PCChapter | MobileChapter:
        ch = None
        if self.url.startswith(self.pc_url_prefixes):
            ch = PCChapter(title=self.title, url=self.url)
        elif self.url.startswith(self.m_url_prefixes):
            ch = MobileChapter(title=self.title, url=self.url)
        return ch

    def get_chapter_content(self, format: str = 'md') -> str | tuple[str] | None:
        if self._check_url():
            logger.error('URL无效')
            return None
        chapter = self._check_device()
        content = chapter.get_chapter_content(format)
        return content



if __name__ == '__main__':
    # url = 'https://m.sfacg.com/c/9200838/'
    # url = 'http://m.sfacg.com/c/1888100'
    url = 'https://book.sfacg.com/Novel/538652/727403/6832391/'
    # url = 'https://book.sfacg.com/Novel/538652/716897/6348396/'

    chapter = Chapter(url=url)
    text = chapter.get_chapter_content()
    print(text)


    # chapter = MobileChapter(url=url)
    # print(chapter)
    # chapter.download_md()
    # html = chapter.get_chapter_content('md')
    # print(html)