import requests
from bs4 import BeautifulSoup, Tag, NavigableString
from loguru import logger
from ch import Chapter
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from time import sleep

HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

class Volume:
    """卷"""
    headers = HEADERS
    base_url = 'https://m.sfacg.com'
    def __init__(self, vol_tag: Tag):
        self.title = vol_tag.string
        self.vol_tag = vol_tag.next_sibling.next_sibling.ul

    def __repr__(self):
        return f'Volume({self.title})'

    def _get_chapters(self, chapter_dict: dict) -> str:
        text = ''
        futures = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            for i, (chapter_title, chapter_url) in enumerate(chapter_dict.items()):
                chapter = Chapter(chapter_title, chapter_url)
                future = executor.submit(chapter.get_chapter_content)
                futures.append((i, future))
        for _, future in futures:
            text += future.result()
        return text + '\n\n'

    def get_volume_content(self):
        """获取本卷内容"""
        logger.info(f'{self.title}')
        volume_content = f'## {self.title}\n\n'
        chapters = {}
        for a_tag in self.vol_tag.find_all('a'):
            chapters[a_tag.get_text()] = self.base_url + a_tag['href']
        return volume_content + self._get_chapters(chapters)


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
        intro = soup.find(class_='book_bk_qs1').string
        self.intro = '\n\n'.join(line.strip() for line in intro.split('\n\n'))
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
    # https://m.sfacg.com/b/752997/
    nid = 751089
    # nid = 752997
    nid = 5976
    novel = Novel(nid)
    novel.download_novel()
    # info = novel.get_novel_info()
    # print(info)


