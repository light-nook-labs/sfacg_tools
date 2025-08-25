from time import sleep
import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from loguru import logger
from abc import ABC, abstractmethod
import os.path

HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

class Ch(ABC):
    """小说章节抽象类

    Args:
        url(str): 小说url
    """

    headers = HEADERS

    def __init__(self, url: str=''):
        self.url = url
        self.title = ''

    def __repr__(self):
        return f'<{self.__class__.__name__}>'

    def _download(self, parent_dir: str='./', file_type: str='md'):
        content = self.get_chapter_content()
        path = f'{parent_dir}{self.title}.{file_type}'
        if file_type in ['md', 'txt']:
            chapter_txt = content[0]
        elif file_type == 'html':
            chapter_txt = content[1]
        with open(path, 'w', encoding='utf-8') as f:
            f.write(chapter_txt)
            logger.info(f'下载完成 {self.title} {self.url}')

    def _soup(self) -> BeautifulSoup:
        """发送请求"""
        response = requests.get(self.url, headers=self.headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        return soup

    def download(self, parent_dir: str='./', file_type: str='md', force: bool=True) -> None:
        if force:
            self._download(parent_dir, file_type)


    @abstractmethod
    def get_chapter_content(self) -> tuple[str]:
        pass


class MobileChapter(Ch):
    """处理移动端章节"""

    def get_chapter_content(self) -> tuple[str, str]:
        """获取章节内容"""
        sleep(0.2)
        soup = self._soup()
        title = soup.title.get_text().split(' - ')[1]
        self.title = title
        content_html = soup.div.div
        del content_html['style']
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
        content_html = f'<div class="ch"><h3>{self.title}</h3>' + str(content_html) + '</div>'
        return content_md, content_html


class PCChapter(Ch):
    """处理PC端章节"""

    def get_chapter_content(self) -> tuple[str, str]:
        """获取章节内容"""
        sleep(0.2)
        soup = self._soup()
        info_tag = soup.find(class_='article-hd')
        title = info_tag.find('h1').get_text().strip()
        self.title = title
        other_info_tags = info_tag.find_all(class_='text')
        other_info = '\t'.join(other_info_tag.get_text() for other_info_tag in other_info_tags)
        content_tag = soup.find(id='ChapterBody')
        del content_tag['class'], content_tag['data-class'], content_tag['id']
        content_html = f'<h3>{title}</h3><p>{other_info}</p>{str(content_tag)}'
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
        return content_md, f'<div class="ch">{content_html}</div>'


class Chapter(PCChapter):

    def get_chapter_content(self) -> tuple[str]:
        if 'book' in self.url:
            chapter = PCChapter(self.url)
        else:
            chapter = MobileChapter(self.url)
        content = chapter.get_chapter_content()
        self.title = chapter.title
        return content




if __name__ == '__main__':
    url = 'https://m.sfacg.com/c/9200838/'
    # url = 'http://m.sfacg.com/c/1888100'
    # url = 'https://book.sfacg.com/Novel/538652/727403/6832391/'
    # url = 'https://book.sfacg.com/Novel/538652/716897/6348396/'

    chapter = Chapter(url=url)
    text = chapter.get_chapter_content()
    # print(text)
    chapter.download(file_type='html')