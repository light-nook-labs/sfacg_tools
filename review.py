"""SFACG review downloader."""
import re
import time
from pathlib import Path
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from loguru import logger
from tqdm import tqdm

try:
    from .fetcher import Fetcher
    from .selectors import Selectors
    from .config import URL_REVIEW_LIST, URL_REVIEW_DETAIL, API_HTML5, MOBILE_BASE
except ImportError:
    from sfacglib.fetcher import Fetcher
    from sfacglib.selectors import Selectors
    from sfacglib.config import URL_REVIEW_LIST, URL_REVIEW_DETAIL, API_HTML5, MOBILE_BASE


def _extract_id(url: str) -> str:
    """Extract numeric ID from URL path."""
    path = urlparse(url).path.rstrip('/')
    return path.split('/')[-1]


class Review:
    """单篇评论"""

    def __init__(self, cid: str, title: str, save_dir: str | Path = './', fetcher: Fetcher | None = None):
        self.cid = str(cid).strip('/')
        self.url = f'{URL_REVIEW_DETAIL}{self.cid}/'
        self.title = title
        self.save_dir = Path(save_dir)
        self.fetcher = fetcher or Fetcher()

    def __repr__(self):
        return f'<Review {self.url}>'

    def get_info(self) -> str:
        """获取评论信息"""
        html = self.fetcher.get_html(self.url)
        soup = BeautifulSoup(html, 'html.parser')

        title = ''
        if soup.title:
            title = soup.title.string.removesuffix('-书评详情-SF轻小说手机版') if soup.title.string else ''

        content = soup.p.get_text().strip() if soup.p else ''

        date = ''
        date_div = soup.find('div')
        if date_div and date_div.span:
            match = re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}', date_div.span.get_text())
            if match:
                date = match.group()

        replies_num, praise_num = '0', '0'
        hudong = soup.find(class_='shuping_hudong book_bk_qs1')
        if hudong:
            parts = hudong.get_text().split()
            if len(parts) >= 2:
                replies_num, praise_num = parts[0], parts[1]

        replies = self._get_replies()

        msg = f'## {title} - 评论时间{date} 评论数{replies_num}, 点赞数{praise_num}\n\n'
        msg += f'{content}\n\n{replies}\n\n'
        return msg

    def _get_replies(self) -> str:
        """获取评论回复（分页）"""
        page = 0
        replies: list[str] = []
        while True:
            params = {
                'op': 'getcmtreply',
                'cid': self.cid,
                'pi': page,
                'withcmt': 'false',
                '_': int(time.time() * 1000),
            }
            data = self.fetcher.get_json(API_HTML5, params=params)
            reply_list = data.get('Replys', []) if isinstance(data, dict) else []
            if not reply_list:
                break
            for item in reply_list:
                name = item.get('DisplayName', '匿名')
                content = item.get('Content', '').strip()
                date = item.get('CreateTime', '')
                replies.append(f'- {name} ({date}): {content}')
            page += 1
        return '\n'.join(replies)

    def download(self):
        """下载一篇评论到文件"""
        info = self.get_info()
        self.save_dir.mkdir(parents=True, exist_ok=True)
        path = self.save_dir / f'{self.title}.md'
        with open(path, 'a', encoding='utf-8') as f:
            f.write(info)
        logger.bind(force=True).info(f'评论 {self.cid} 已保存')


class BookReviews:
    """小说全部长评"""

    def __init__(self, url: str, save_dir: str | Path = './', fetcher: Fetcher | None = None):
        self.nid = _extract_id(url)
        self.url = f'{URL_REVIEW_LIST}{self.nid}/'
        self.save_dir = Path(save_dir)
        self.fetcher = fetcher or Fetcher()
        self.title = self._get_title()

    def __repr__(self):
        return f'<BookReviews {self.url}>'

    def _get_title(self) -> str:
        html = self.fetcher.get_html(self.url)
        soup = BeautifulSoup(html, 'html.parser')
        if soup.title and soup.title.string:
            return soup.title.string.removesuffix('小说书评列表-SF轻小说手机版')
        return f'小说_{self.nid}'

    def _get_review_ids(self) -> list[str]:
        """获取所有长评ID"""
        page = 0
        review_ids: list[str] = []
        while True:
            params = {
                'op': 'getcmtlist',
                'nid': self.nid,
                'so': 'addtime',
                'pi': page,
                'ctype': 'long',
                'len': 60,
                '_': int(time.time() * 1000),
            }
            data = self.fetcher.get_json(API_HTML5, params=params)
            cmts = data.get('Cmts', []) if isinstance(data, dict) else []
            if not cmts:
                break
            review_ids.extend(str(item.get('CommentID', '')) for item in cmts if item.get('CommentID'))
            page += 1
        return review_ids

    def download_reviews(self):
        """下载全部长评"""
        review_ids = self._get_review_ids()
        total = len(review_ids)
        logger.bind(force=True).info(f'{self.title} 共{total}条评论')

        self.save_dir.mkdir(parents=True, exist_ok=True)
        path = self.save_dir / f'{self.title}.md'
        path.write_text(f'# {self.title} 长评 共{total}条评论\n\n', encoding='utf-8')

        for cid in tqdm(reversed(review_ids), total=total, desc='Reviews'):
            review = Review(cid, self.title, save_dir=self.save_dir, fetcher=self.fetcher)
            review.download()

        logger.bind(force=True).info(f'下载完毕: {path}')


if __name__ == '__main__':
    url = f'{MOBILE_BASE}/b/43708/'
    b = BookReviews(url)
    b.download_reviews()
