from ebooklib import epub
from bs4 import BeautifulSoup, Tag
import requests
from uuid import uuid4
import os
from urllib.parse import urlparse

from ebooklib.epub import EpubHtml

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


def download_epub(html: str, title: str, author: str, desc: str, cover: str, path: str='./') -> None:

    # 创建电子书对象
    book = epub.EpubBook()

    # 设置书籍元数据
    book.set_identifier(str(uuid4()))  # 唯一标识符
    book.set_title(title)
    book.set_language('zh')
    book.add_author(author)
    book.add_metadata('DC', 'description', desc)

    # 处理封面
    try:
        cover_content = requests.get(url=cover, headers=HEADERS, timeout=10).content
        book.set_cover("cover.jpg", cover_content)
    except Exception as e:
        print(f"封面下载失败: {e}")

    spine: list[str | EpubHtml] = ['nav']
    toc = []

    # 解析HTML内容
    soup = BeautifulSoup(html, 'html.parser')
    for vol_tag in soup.find_all(class_='vol'):
        vol_title = vol_tag.h2.get_text() if vol_tag.h2 else "未命名卷"

        # 创建卷节点
        vol = epub.EpubHtml(
            title=vol_title,
            file_name=f'vol_{str(uuid4())[:8]}.xhtml',  # 使用短UUID避免路径过长
            lang='zh',
            content=str(vol_tag.h2) if vol_tag.h2 else ""
        )
        if not vol_tag.h3:
            vol.content = str(vol_tag)
        book.add_item(vol)
        spine.append(vol)

        chapters = []
        for ch_tag in vol_tag.find_all(class_='ch'):
            # 获取章节标题
            if ch_tag.h3:
                chapter_title = ch_tag.h3.get_text()
            else:
                # chapter_title = '未命名章节'
                continue
            # 处理章节中的图片
            imgs: list[Tag] = ch_tag.find_all('img')
            for img in imgs:
                if 'src' not in img.attrs:
                    continue  # 跳过没有src属性的图片

                img_url = img['src']
                try:
                    img_filename = f"image_{str(uuid4())[:8]}.jpg"

                    # 下载图片内容
                    img_content = requests.get(url=img_url, headers=HEADERS, timeout=10).content

                    # 创建图片项
                    img_item = epub.EpubImage(
                        uid=str(uuid4()),
                        file_name=f"images/{img_filename}",  # 统一放到images目录
                        media_type='image/jpeg',  # 可以根据实际情况调整
                        content=img_content
                    )
                    book.add_item(img_item)

                    # 更新HTML中的图片路径
                    img['src'] = f"images/{img_filename}"

                except Exception as e:
                    print(f"处理图片 {img_url} 失败: {e}")
                    # 出错时移除图片标签或保留原始URL
                    # img.decompose()  # 移除无法处理的图片

            # 创建章节
            chapter = epub.EpubHtml(
                title=chapter_title,
                file_name=f'ch_{str(uuid4())[:8]}.xhtml',  # 使用短UUID
                lang='zh',
                content=str(ch_tag)
            )

            chapters.append(chapter)
            book.add_item(chapter)
            spine.append(chapter)

        # 添加到目录
        vol_tuple = (epub.Section(vol_title), tuple(chapters))
        toc.append(vol_tuple)

    book.toc = tuple(toc)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine

    # 写入电子书
    try:
        epub.write_epub(name=f'{path}{title}.epub', book=book)
        print("电子书生成成功")
    except Exception as e:
        print(f"生成电子书失败: {e}")
