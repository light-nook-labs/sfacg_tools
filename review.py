import requests
from bs4 import BeautifulSoup
import re
import time

# 小说详情页 https://m.sfacg.com/b/49038/
# 评论列表 https://m.sfacg.com/cmt/l/list/49038/
# 其中一个书评 https://m.sfacg.com/cmt/l/17040073/

class Review:
    """小说一篇评论的类"""

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    base_url = 'https://m.sfacg.com/cmt/l/'

    def __init__(self, url, title):
        self.cid = str(url).strip('/').split('/')[-1]
        self.url = self.base_url + self.cid + '/'
        self.title = title

    def __repr__(self):
        return f'<Review {self.url}>'

    def get_info(self):
        """获取评论的信息"""
        msg = ''
        res = requests.get(url=self.url, headers=self.headers)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        title = soup.title.string.rstrip('-书评详情-SF轻小说手机版')
        content = soup.p.get_text().strip()
        pattern = r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}$'
        date = soup.div.span.get_text()
        date = re.search(pattern, date).group()
        replies_num, praise_num = soup.find(class_='shuping_hudong book_bk_qs1').get_text().split()
        review_info = {
            'title': title,
            'content': content,
            'date': date,
            'replies_num': replies_num,
            'praise_num': praise_num,
            'replys': self.get_replies(),
        }
        msg += f"## {review_info['title']} - 评论时间{review_info['date']} 评论数{review_info['replies_num']}, 点赞数{review_info['praise_num']}\n\n"
        msg += f'{review_info['content']}\n\n'
        msg += f'{review_info['replys']}\n\n'
        return msg

    def get_replies(self) -> str:
        """获取评论的回复"""
        i = 0
        reply_base_url = 'https://m.sfacg.com/API/HTML5.ashx'
        replies = []
        while True:
            params = {
                'op': 'getcmtreply',
                'cid': self.cid,
                'pi': i,
                'withcmt': 'false',
                '_': int(time.time() * 1000),
            }
            json_data = requests.get(url=reply_base_url, headers=self.headers, params=params).json()
            # print(json_data)
            if json_data['Replys'] == []:
                break
            reply_info = self.__json_info(json_data)
            replies.append(reply_info)
            i += 1
        reply_msg = '\n'.join(replies)
        return reply_msg

    def __json_info(self, data) -> str:
        """获取评论的回复"""
        replys = []
        for item in data['Replys']:
            user_name = item['DisplayName']
            content = item['Content'].strip()
            date = item['CreateTime']
            reply_info =  {
                'user_name': user_name,
                'content': content,
                'date': date
            }
            replys.append(reply_info)
        reply_msg = '\n'.join([f"- {item['user_name']} ({item['date']}): {item['content']})" for item in replys])

        return reply_msg

    def down_one_review(self):
        """下载一篇评论"""
        review_info = self.get_info()
        print(review_info)
        with open(f'{self.title}.md', 'a+', encoding='utf-8') as f:
            f.write(review_info)

class BookReviews:
    """小说的评论类"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    review_base_url = 'https://m.sfacg.com/cmt/l/list/'
    base_url = 'https://m.sfacg.com/API/HTML5.ashx'
    def __init__(self, url):
        self.nid = url.strip('/').split('/')[-1]
        self.url = self.review_base_url + self.nid + '/'
        self.title = self.__get_title()
    def __repr__(self):
        return f'<BookReviews {self.url}>'

    def __get_title(self):
        """获取小说的评论"""
        res = requests.get(url=self.url, headers=self.headers)
        res.encoding = 'utf-8'
        soup = BeautifulSoup(res.text, 'html.parser')
        return soup.title.string.rstrip('小说书评列表-SF轻小说手机版')

    def download_reviews(self):
        """获取小说的评论"""
        i = 0
        review_ids = []
        reviews = []
        msg = f'# {self.title} 长评'
        while True:
            params = {
                'op': 'getcmtlist',
                'nid': self.nid,
                'so': 'addtime',
                'pi': i,
                'ctype': 'long',
                'len': 60,
                '_': int(time.time() * 1000),
            }
            json_data = requests.get(url=self.base_url, headers=self.headers, params=params).json()
            # print(json_data)
            if json_data['Cmts'] == []:
                break
            cids = [item['CommentID'] for item in json_data['Cmts']]
            review_ids.extend(cids)
            i += 1
        print(review_ids)
        msg += f' 共{len(review_ids)}条评论\n\n'
        print(msg)
        with open(f'{self.title}.md', 'a+', encoding='utf-8') as f:
            f.write(msg)
        for cid in review_ids[::-1]:
            review = Review(cid, self.title)
            review.down_one_review()
        print('下载完毕')


if __name__ == '__main__':
    # url = 'https://m.sfacg.com/b/49038/'
    # url = 'https://m.sfacg.com/b/689388/'
    url = 'https://m.sfacg.com/b/43708/'
    b = BookReviews(url)
    b.download_reviews()