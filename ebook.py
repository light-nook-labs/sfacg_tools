from ebooklib import epub
from bs4 import BeautifulSoup, Tag
import requests
from uuid import uuid4

from ebooklib.epub import EpubHtml

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


with open('./demo.html', encoding='utf-8') as f:
    html = f.read()

title = 'sample'
author = 'a'
description = 'd'
cover = 'https://rs.sfacg.com/web/novel/images/NovelCover/Big/2025/07/4cc0bed8-327c-46b8-b909-d8dbc066aa5b.jpg"'

# 创建电子书对象
book = epub.EpubBook()

# 设置书籍元数据
book.set_identifier(str(uuid4()))  # 唯一标识符
book.set_title(title)
book.set_language('zh')
book.add_author(author)
book.add_metadata('DC', 'description', description)
cover_content = requests.get(url=cover, headers=HEADERS).content
book.set_cover("cover.jpg", cover_content)


spine: list[str | EpubHtml] = ['nav']
toc = []

# 解析HTML内容
soup = BeautifulSoup(html, 'html.parser')
for vol_tag in soup.find_all(class_='vol'):
    vol_title = vol_tag.h2.get_text()
    spine.append(vol_title)
    chapters = []
    vol = epub.EpubHtml(
        title=vol_title,
        file_name=f'{str(uuid4())}.xhtml',
        lang='zh',
        content=str(vol_tag.h2),
    )
    book.add_item(vol)
    spine.append(vol)
    for ch_tag in vol_tag.find_all(class_='ch'):
        if ch_tag.h3:
            title = ch_tag.h3.get_text()
        else:
            title = '未命名章节'
        imgs: list[Tag | None] = ch_tag.find_all('img')
        if imgs:
            for img in imgs:
                url = img['src']
                img['src'] = f"img/{url}"
                img_item = epub.EpubImage(
                    uid=str(uuid4()), file_name=f"img/{url}",
                    media_type='image/jpg',
                    content=requests.get(url=url, headers=HEADERS).content
                )
                book.add_item(img_item)
        chapter = epub.EpubHtml(
            title=title,
            file_name=f'{str(uuid4())}.xhtml',
            lang='zh',
            content=str(ch_tag),
        )

        chapters.append(chapter)
        book.add_item(chapter)
        spine.append(chapter)
    vol_tuple = (epub.Section(vol_title), tuple(chapters))
    toc.append(vol_tuple)


book.toc = tuple(toc)
book.add_item(epub.EpubNcx())
book.add_item(epub.EpubNav())
book.spine = spine
epub.write_epub(name='样书.epub', book=book)


