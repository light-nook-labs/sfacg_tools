from time import sleep, time
import requests
from bs4 import BeautifulSoup
from loguru import logger
import os.path
import re
from concurrent.futures import ThreadPoolExecutor


HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
BASE_URL = 'https://mm.sfacg.com'

class ComicChapter:
    headers = HEADERS
    common_url = 'https://mm.sfacg.com/ajax/Common.ashx'
    def __init__(self, title: str, url: str):
        self.title = title
        # https://mm.sfacg.com/b/ZXNWM/ZP/0002_4857/
        self.url = url

    def __repr__(self):
        return f'<ComicChapter: {self.title}, {self.url}>'

    def _get_args(self):
        res = requests.get(self.url, headers=self.headers)
        soup = BeautifulSoup(res.content, 'html.parser')
        scripts = soup.find_all('script')
        vars = ['comicId', 'nv', 'chapterId']
        args = []
        for script in scripts:
            if all(var in script.text for var in vars):
                for var in vars:
                    pattern = rf'{var}\s*=\s*([^\s;]+);'
                    match = re.search(pattern, script.text)
                    value = match.group(1)
                    args.append(value)
        return [arg.strip('"') for arg in args]

    def get_image_urls(self) -> list[str]:
        comic_id, nv, chapter_id = self._get_args()
        params = {
            'op': 'getPics',
            'cid': int(comic_id),
            'chapId': int(chapter_id),
            'serial': 'ZP',
            'path': nv, # nv
            '_': int(time() * 1000),
        }
        res = requests.get(self.common_url, headers=self.headers, params=params)
        res.raise_for_status()
        return res.json()['data']

    def _download_image(self, id: int, url: str, path: str='./images/'):
        content = requests.get(url, headers=self.headers).content
        with open(f'{path}{id:03}.jpg', 'wb') as f:
            f.write(content)
        logger.info(f'page {id} downloaded')

    def download(self, path: str='./images/') -> None:
        # 在循环外部创建线程池，实现真正的多线程并行下载
        with ThreadPoolExecutor(max_workers=10) as executor:
            # 一次性提交所有下载任务
            for id, image_url in enumerate(self.get_image_urls(), start=1):
                executor.submit(self._download_image, id, image_url, path)


class Comic:
    headers = HEADERS
    def __init__(self, url: str):
        self.url = url
        self.title = ''
        self.info = ''

    def __repr__(self):
        return f'<Comic: {self.url}>'

    def get_comic_info(self) -> dict[str, str]:
        res = requests.get(self.url, headers=self.headers)
        soup = BeautifulSoup(res.content, 'html.parser')
        info_tag = soup.find(class_='book_info')
        title = info_tag.find(class_='book_newtitle').string
        self.title = title
        cover = info_tag.img['src']
        label = ' '.join(list(info_tag.find(class_='book_info2').stripped_strings))
        more_info = ' '.join(list(info_tag.find(class_='book_info3').stripped_strings))
        book_interact = list(soup.find(class_='book_interact').stripped_strings)
        del book_interact[-1]
        book_interact = ' '.join(book_interact)
        book_profile = soup.find(class_='book_profile').get_text()
        self.info = f"""
# {title}

![封面]({cover})

漫画地址： {self.url}

标签： {label}

{more_info}

{book_interact}

{book_profile}
"""
        a_tags = soup.find(class_='comic_main_list').find_all('a')
        chapter_dict = {}
        for a_tag in a_tags[::-1]:
            href = a_tag['href']
            chapter_title = a_tag.get_text().strip()
            chapter_dict[href] = chapter_title
        return chapter_dict

    def download(self, path: str='./'):
        chapter_dict = self.get_comic_info()
        comic_path = f'{path}{self.title}/'
        os.makedirs(comic_path, exist_ok=True)
        with ThreadPoolExecutor(max_workers=3) as executer:
            for i, (href, chapter_title) in enumerate(chapter_dict.items(), start=1):
                chapter_path = f'{comic_path}{i:03}-{chapter_title}/'
                os.makedirs(chapter_path, exist_ok=False)
                chapter = ComicChapter(title=chapter_title, url=BASE_URL+href)
                executer.submit(chapter.download, chapter_path)
                logger.info(f'{chapter_title} downloaded')



if __name__ == '__main__':
    # chapter_url = 'https://mm.sfacg.com/b/ZXNWM/ZP/0002_4857/'
    comic_url = 'https://mm.sfacg.com/b/ZXNWM/'
    comic = Comic(comic_url)
    info = comic.get_comic_info()
    # print(info)
    comic.download()
