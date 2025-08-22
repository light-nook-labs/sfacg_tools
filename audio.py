import requests
from bs4 import BeautifulSoup, Tag
from loguru import logger
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from time import sleep
import json
import re
import os
import os.path


HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
BASE_URL = 'https://m.sfacg.com'
MAX_INVALID = 10
JSON_PATH = './audiobooks.json'

def get_audiobook_list(i: int=0) -> list[int]:
    """获取有声小说列表，返回有效ID列表，并保存为JSON文件"""

    valid_ids: list[int] = []
    valid_titles: list[str] = []
    while True:
        i += 1
        if len(valid_ids) < 1:
            pass
        elif i - valid_ids[-1] >= MAX_INVALID:
            break
        audio_url = f'{BASE_URL}/ai/{i}/'
        try:
            res = requests.get(audio_url, headers=HEADERS)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, 'html.parser')
            title = soup.title.string
            if title == '出错啦':
                continue
            else:
                valid_ids.append(i)
                title = title.split('音频列表')[0]
                valid_titles.append(title)
                logger.info(f'{i} {title}')
        except Exception as e:
            logger.error(i, audio_url, e)
            continue

    # 保存为JSON文件
    if valid_ids:
        filename = JSON_PATH
        json_content = [{"id": i, "title": title} for i, title in zip(valid_ids, valid_titles)]
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(json_content, f, ensure_ascii=False, indent=2)
        logger.info(f"已更新json文件{filename}")
    else:
        logger.warning("json文件更新失败，请重试")
    return valid_ids


class AudioChapter:
    """有声小说章节"""

    def __init__(self, title: str='第一章 邪道主人公变成美少女（1）', url: str='/a/91682/'):
        self.title = title
        self.url = BASE_URL + url

    def get_mp3_url(self) -> str | None:
        """获取mp3的链接"""
        try:
            res = requests.get(self.url, headers=HEADERS)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, 'html.parser')
            script_tags = soup.find_all('script')
            # 用于匹配MP3链接的正则表达式
            mp3_pattern = re.compile(r'https?://.+\.mp3')

            # 遍历所有script标签内容，查找MP3链接
            for script in script_tags:
                if script.string:  # 确保script标签有内容
                    # 搜索MP3链接
                    match = mp3_pattern.search(script.string)
                    if match:
                        return match.group()  # 返回找到的第一个MP3链接
            return None
        except Exception as e:
            logger.error(f"获取音频链接失败: {self.url} - {e}")
        return None

    def download_mp3(self, path: str='./', force: bool=True) -> None:
        """下载音频

        Args:

            path 下载目录
            force 如果文件存在是否覆盖
        """
        path = f'{path}{self.title}.mp3'
        mp3_url = self.get_mp3_url()
        if not mp3_url:
            return
        if force:
            content = requests.get(mp3_url, headers=HEADERS).content
            with open(path, 'wb+') as f:
                f.write(content)
            logger.info(f'下载完成{self.title}{self.url}')

class AudioVolume:
    """有声小说卷"""

    def __init__(self, tag: Tag, prefix: bool=True):
        self.tag = tag.next_sibling.next_sibling.ul
        self.prefix = prefix

    def get_volume_dict(self):
        volumn_dict = {}
        for tag in self.tag.find_all('a'):
            volumn_dict[tag['href']] = tag.li.string
        if self.prefix:
            volumn_dict = {href: f'{i:03}-{text}' for i, (href, text) in enumerate(volumn_dict.items(), start=1)}
        return volumn_dict

    def download_volume(self, path: str='./', force: bool=True) -> None:
        with ThreadPoolExecutor(max_workers=5) as executor:
            for href, text in self.get_volume_dict().items():
                chapter = AudioChapter(text, href)
                executor.submit(chapter.download_mp3, path=path, force=force)

class Audio:
    """有声小说"""
    def __init__(self, id: int):
        self.id = id
        self.url = BASE_URL + f'/ai/{id}/'
        self.title = ''  # 初始化标题属性

        if os.path.exists(JSON_PATH):
            with open(JSON_PATH, 'r', encoding='utf-8') as f:
                data_list = json.load(f)  # 加载整个JSON数组

            # 遍历数组查找匹配id的条目
            for item in data_list:
                if item.get("id") == id:
                    self.title = item.get("title")
                    break  # 找到后退出循环
            else:
                # 如果循环结束未找到匹配id
                logger.warning('请尝试调用get_audiobook_list()函数更新json文件')
                raise ValueError(f"未找到id为{id}的有声小说")
        else:
            logger.warning('请尝试调用get_audiobook_list()函数更新json文件')
            raise FileNotFoundError(f"JSON文件不存在: {JSON_PATH}")

    def _get_volume_list(self) -> list[Tag]:
        res = requests.get(self.url, headers=HEADERS)
        try:
            res.raise_for_status()
            soup = BeautifulSoup(res.text, 'html.parser')
            volume_tags = soup.find_all(class_='mulu')
            return volume_tags
        except Exception as e:
            logger.error('卷目录获取失败')
            return []

    def download(self):
        volume_tags = self._get_volume_list()
        for volume_tag in volume_tags:
            volume = AudioVolume(volume_tag)
            volume.download_volume(path='./audio/', force=True)


if __name__ == '__main__':
    id = 555
    audio = Audio(id)
    audio.download()
    # volumes_tags = audio._get_volume_list()
    # volume_tag = volumes_tags[0]
    # volume = AudioVolume(volume_tag)
    # volume_dict = volume.get_volume_dict()
    # print(volume_dict)