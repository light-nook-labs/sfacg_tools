import requests
from bs4 import BeautifulSoup, Tag, NavigableString
from loguru import logger

HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

class MobileChapter:
    """处理移动端章节
    Args:
        title: str 小说标题
        url: str 小说url
    """

    def __init__(self, title: str, url: str):
        self.url = url
        self.title = title
        self.headers = HEADERS

    def __repr__(self):
        return f'{self.__class__.__name__}(title="{self.title}", url="{self.url}")'

    def get_chapter_content(self):
        """获取章节内容"""
        logger.info(f'{self.title} {self.url}')
        response = requests.get(self.url, headers=self.headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        content = f'### {self.title}\n\n'
        children = [child.name for child in soup.div.div.children]
        for child in soup.div.div.children:
            if type(child) == NavigableString and str(child).strip() != '':
                content += f"{str(child).strip()}\n\n"
            elif child.name == "img":
                content += f"![]({child['src']})\n\n"
            elif child.name == "p":
                content += f"{child.get_text()}\n\n"
            elif child.name == "br":
                continue
        self.content = content.strip()
        return content.strip()

class Volume:
    """卷"""
    headers = HEADERS
    base_url = 'https://m.sfacg.com'
    def __init__(self, vol_tag: Tag):
        self.title = vol_tag.string
        self.vol_tag = vol_tag.next_sibling.next_sibling.ul

    def get_volume_content(self):
        """获取本卷内容"""
        logger.info(f'{self.title}')
        volume_content = f'## {self.title}\n\n'
        chapters = {}
        for a_tag in self.vol_tag.find_all('a'):
            chapters[a_tag.get_text()] = self.base_url + a_tag['href']
        for chapter_title, chapter_url in chapters.items():
            chapter = MobileChapter(chapter_title, chapter_url)
            chapter_content = chapter.get_chapter_content()
            volume_content += chapter_content + '\n\n'
        return volume_content

class Novel:
    """小说内容"""
    headers = HEADERS
    base_url_index = 'https://m.sfacg.com/b/'
    base_url_menu = 'https://m.sfacg.com/i/'

    def __init__(self, nid: int):
        self.nid = str(nid)
        self.index_url = ''
        self.title = ''
        self.label = ''
        self.author = ''
        self.word_num = ''
        self.click_num = ''
        self.date = ''
        self.clock = ''
        self.heart_num = ''
        self.praise_num = ''
        self.intro = '暂无简介'
        self.cover_url = ''

    def get_novel_info(self) -> str:
        """获取小说信息"""
        self.index_url = self.base_url_index + self.nid
        logger.info(self.index_url)
        res = requests.get(url=self.index_url, headers=self.headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        info_tag = soup.find(class_='book_info')
        self.title = info_tag.span.string
        self.cover_url = 'https:' + info_tag.img['src']
        print(self.cover_url)
        for part in info_tag.div.stripped_strings:
            self.label += part + ' '
        self.author, self.word_num, click_and_new = soup.find(class_='book_info3').get_text().split(' / ')
        self.click_num, self.date, self.clock = click_and_new.split()
        smalls = soup.find_all('small')
        self.heart_num, self.praise_num, _ = [small.string.strip() for small in smalls]
        self.intro = soup.find(class_='book_bk_qs1').string
        return f"""
# {self.title}-{self.author}

## 小说信息

![封面]({self.cover_url})

原文地址：{self.base_url_index}{self.nid}

作者：{self.author}\t字数：{self.word_num} 点击量：{self.click_num}

标签：{self.label}

最近更新时间：{self.date} {self.clock}

收藏量：{self.heart_num}\t点赞数：{self.praise_num}

{self.intro}

{'='*20}

"""

    def _get_volume_tags(self) -> list[Tag]:
        """获取卷列表"""
        menu_url = self.base_url_menu + self.nid
        res = requests.get(url=menu_url, headers=self.headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        menu_tags = soup.find_all(class_='mulu')
        return menu_tags

    def get_novel_content(self) -> str:
        novel_content = self.get_novel_info()
        volume_tags = self._get_volume_tags()
        for volume_tag in volume_tags:
            volume = Volume(volume_tag)
            novel_content += volume.get_volume_content()
        return novel_content

    def download_novel(self):
        novel_content = self.get_novel_content()
        with open(f'{self.title}-{self.author}.md', 'w', encoding='utf-8') as f:
            f.write(novel_content)


if __name__ == '__main__':
    # url = 'https://m.sfacg.com/c/8393500/'
    url = 'https://m.sfacg.com/c/9090775/'
    # url = 'https://book.sfacg.com/Novel/744362/985558/9090775/'
    # novel_url = 'https://m.sfacg.com/b/751089/'
    # nid = 751089
    # novel = Novel(nid)
    # novel.download_novel()
    # info = novel.get_novel_info()
    # print(novel.author)
    # print(novel.label)
    # print(info)


