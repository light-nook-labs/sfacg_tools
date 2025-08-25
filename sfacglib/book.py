import requests
from bs4 import BeautifulSoup, Tag
from loguru import logger
from ch import Chapter
from concurrent.futures import ThreadPoolExecutor
from time import sleep
from epup import download_epub

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
        return f'<Volume({self.title})>'

    def _get_chapters(self, chapter_dict: dict) -> tuple[str, str]:
        text_md = ''
        text_html = ''
        futures = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            for i, (_, chapter_url) in enumerate(chapter_dict.items()):
                chapter = Chapter(chapter_url)
                future = executor.submit(chapter.get_chapter_content)
                futures.append((i, future))
        for _, future in futures:
            res = future.result()
            text_md += res[0]
            text_html += res[1]
        return text_md + '\n\n', text_html

    def get_volume_content(self, file_type: str='md') -> tuple[str, str]:
        """获取本卷内容"""
        logger.info(f'{self.title}')
        volume_md = f'## {self.title}\n\n'
        volume_html = f'<div class="vol"><h2>{self.title}</h2>'
        chapters = {}
        for a_tag in self.vol_tag.find_all('a'):
            chapters[a_tag.get_text()] = self.base_url + a_tag['href']
        md, html = self._get_chapters(chapters)
        return volume_md + md, volume_html + html + '</div>'


class Novel:
    """小说内容"""
    headers = HEADERS
    base_url_index = 'https://m.sfacg.com/b/'
    base_url_menu = 'https://m.sfacg.com/i/'

    def __init__(self, nid: int):
        self.nid = str(nid)
        self.title = ''
        self.author = ''
        self.intro = ''
        self.cover = ''

    def get_novel_info(self) -> tuple[str, str]:
        """获取小说信息"""
        index_url = self.base_url_index + self.nid
        logger.info(index_url)
        res = requests.get(url=index_url, headers=self.headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        info_tag = soup.find(class_='book_info')
        title = info_tag.span.string
        self.title = title
        cover_url = 'https:' + info_tag.img['src']
        self.cover = cover_url
        label = ''
        for part in info_tag.div.stripped_strings:
            label += part + ' '
        author, word_num, click_and_new = soup.find(class_='book_info3').get_text().split(' / ')
        self.author = author
        click_num, date, clock = click_and_new.split()
        smalls = soup.find_all('small')
        heart_num, praise_num, _ = [small.string.strip() for small in smalls]
        intro = soup.find(class_='book_bk_qs1').string
        intro = '\n\n'.join(line.strip() for line in intro.split('\n\n'))
        self.intro = intro
        info_md = f"""
# {title}-{author}

## 小说信息

![封面]({cover_url})

原文地址：{self.base_url_index}{nid}

作者：{author}\t字数：{word_num} 点击量：{click_num}

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
        <p>原文地址：{self.base_url_index}{nid}</p>
        <p>作者：{author}\t字数：{word_num} 点击量：{click_num}</p>
        <p>标签：{label}</p>
        <p>最近更新时间：{date} {clock}</p>
        <p>收藏量：{heart_num}\t点赞数：{praise_num}</p>
        <div>{intro}</div>
        <hr>
        </div>
        """
        return info_md, info_html

    def _get_volume_tags(self) -> list[Tag]:
        """获取卷列表"""
        menu_url = self.base_url_menu + self.nid
        res = requests.get(url=menu_url, headers=self.headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        menu_tags = soup.find_all(class_='mulu')
        return menu_tags

    def get_novel_content(self) -> tuple[str, str]:
        novel_content_md, novel_content_html = self.get_novel_info()
        volume_tags = self._get_volume_tags()
        for volume_tag in volume_tags:
            volume = Volume(volume_tag)
            content_md, content_html = volume.get_volume_content()
            novel_content_md += content_md
            novel_content_html += content_html
            sleep(3)
        soup = BeautifulSoup(novel_content_html, 'html.parser')
        return novel_content_md, soup.prettify()

    def download_novel(self, path: str='./', file_type: str='md'):
        novel_content = self.get_novel_content()
        if file_type in ['txt', 'md']:
            novel_content = novel_content[0]
        elif file_type in ['html', 'epub']:
            novel_content = novel_content[1]
            if file_type == 'epub':
                download_epub(novel_content, self.title, self.author, self.intro, self.cover, path)
                return
        else:
            logger.error('下载失败')
            return
        path += f'{self.title}-{self.author}.{file_type}'
        with open(path, 'w', encoding='utf-8') as f:
            f.write(novel_content)


if __name__ == '__main__':
    # url = 'https://m.sfacg.com/c/8393500/'
    url = 'https://m.sfacg.com/c/9090775/'
    # url = 'https://book.sfacg.com/Novel/744362/985558/9090775/'
    # novel_url = 'https://m.sfacg.com/b/751089/'
    # https://m.sfacg.com/b/752997/
    # nid = 751089
    # nid = 752997
    # nid = 5976
    path = 'e:/小说/'
    nid = 474064
    novel = Novel(nid)
    novel.download_novel(file_type='epub', path=path)
    # info = novel.get_novel_content()[1]
    # print(info)


