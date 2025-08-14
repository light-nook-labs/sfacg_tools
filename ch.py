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

    def download_md(self, path: str='./', force: bool=True) -> None:
        md_path = f'{path}/{self.title}.md'
        ex = os.path.exists(md_path)
        print(ex)
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
    def get_chapter_content(self):
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
    pass

class Chapter(Ch):
    pass


if __name__ == '__main__':
    url = 'https://m.sfacg.com/c/9200838/'
    # url = 'http://m.sfacg.com/c/1888100'
    chapter = MobileChapter(url=url)
    print(chapter)
    chapter.download_md()
    # html = chapter.get_chapter_content('md')
    # print(html)