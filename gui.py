import requests
from bs4 import BeautifulSoup
import re
import time
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import sys
from io import StringIO
import os


class RedirectText:
    """用于将控制台输出重定向到Tkinter文本框"""

    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.buffer = StringIO()

    def write(self, string):
        self.buffer.write(string)
        self.text_widget.configure(state="normal")
        self.text_widget.insert(tk.END, string)
        self.text_widget.see(tk.END)  # 滚动到最后
        self.text_widget.configure(state="disabled")

    def flush(self):
        self.buffer.flush()


class Review:
    """小说一篇评论的类"""

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    base_url = 'https://m.sfacg.com/cmt/l/'

    def __init__(self, url, title, save_dir):
        self.cid = str(url).strip('/').split('/')[-1]
        self.url = self.base_url + self.cid + '/'
        self.title = title
        self.save_dir = save_dir  # 保存目录

    def __repr__(self):
        return f'<Review {self.url}>'

    def get_info(self):
        """获取评论的信息"""
        msg = ''
        try:
            res = requests.get(url=self.url, headers=self.headers, timeout=10)
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            title = soup.title.string.rstrip('-书评详情-SF轻小说手机版')
            content = soup.p.get_text().strip()
            pattern = r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}$'
            date = soup.div.span.get_text()
            date = re.search(pattern, date).group()
            hudong = soup.find(class_='shuping_hudong book_bk_qs1')
            if hudong:
                replies_num, praise_num = hudong.get_text().split()
            else:
                replies_num, praise_num = "0", "0"

            review_info = {
                'title': title,
                'content': content,
                'date': date,
                'replies_num': replies_num,
                'praise_num': praise_num,
                'replys': self.get_replies(),
            }
            msg += f"## {review_info['title']} - 评论时间{review_info['date']} 评论数{review_info['replies_num']}, 点赞数{review_info['praise_num']}\n\n"
            msg += f'{review_info["content"]}\n\n'
            msg += f'{review_info["replys"]}\n\n'
            return msg
        except Exception as e:
            print(f"获取评论信息出错: {str(e)}")
            return f"获取评论信息出错: {str(e)}\n\n"

    def get_replies(self) -> str:
        """获取评论的回复"""
        i = 0
        reply_base_url = 'https://m.sfacg.com/API/HTML5.ashx'
        replies = []
        try:
            while True:
                params = {
                    'op': 'getcmtreply',
                    'cid': self.cid,
                    'pi': i,
                    'withcmt': 'false',
                    '_': int(time.time() * 1000),
                }
                json_data = requests.get(
                    url=reply_base_url,
                    headers=self.headers,
                    params=params,
                    timeout=10
                ).json()

                if not json_data.get('Replys', []):
                    break

                reply_info = self.__json_info(json_data)
                replies.append(reply_info)
                i += 1
                time.sleep(0.5)  # 降低请求频率
        except Exception as e:
            print(f"获取评论回复出错: {str(e)}")
            replies.append(f"获取评论回复出错: {str(e)}")

        reply_msg = '\n'.join(replies)
        return reply_msg

    def __json_info(self, data) -> str:
        """解析回复的JSON数据"""
        replys = []
        for item in data['Replys']:
            user_name = item.get('DisplayName', '匿名用户')
            content = item.get('Content', '').strip()
            date = item.get('CreateTime', '未知时间')
            replys.append(f"- {user_name} ({date}): {content}")

        return '\n'.join(replys)

    def down_one_review(self):
        """下载一篇评论"""
        try:
            review_info = self.get_info()
            print(review_info)

            # 确保保存目录存在
            if not os.path.exists(self.save_dir):
                os.makedirs(self.save_dir)

            # 构建完整文件路径
            file_path = os.path.join(self.save_dir, f'{self.title}.md')
            with open(file_path, 'a+', encoding='utf-8') as f:
                f.write(review_info)
            time.sleep(1)  # 降低请求频率，避免被反爬
        except Exception as e:
            print(f"下载评论出错: {str(e)}")


class BookReviews:
    """小说的评论类"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    review_base_url = 'https://m.sfacg.com/cmt/l/list/'
    base_url = 'https://m.sfacg.com/API/HTML5.ashx'

    def __init__(self, url, save_dir, progress_callback=None):
        self.nid = url.strip('/').split('/')[-1]
        self.url = self.review_base_url + self.nid + '/'
        self.title = self.__get_title()
        self.save_dir = save_dir  # 保存目录
        self.progress_callback = progress_callback  # 用于更新进度条的回调函数

    def __repr__(self):
        return f'<BookReviews {self.url}>'

    def __get_title(self):
        """获取小说的标题"""
        try:
            res = requests.get(url=self.url, headers=self.headers, timeout=10)
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            title = soup.title.string.rstrip('小说书评列表-SF轻小说手机版')
            return title
        except Exception as e:
            print(f"获取小说标题出错: {str(e)}")
            return f"未知小说_{int(time.time())}"

    def download_reviews(self):
        """获取并下载小说的所有评论"""
        try:
            i = 0
            review_ids = []
            msg = f'# {self.title} 长评'

            print("正在获取评论列表...")
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
                json_data = requests.get(
                    url=self.base_url,
                    headers=self.headers,
                    params=params,
                    timeout=10
                ).json()

                if not json_data.get('Cmts', []):
                    break

                cids = [item['CommentID'] for item in json_data['Cmts']]
                review_ids.extend(cids)
                print(f"已获取第{i + 1}页评论，共{len(review_ids)}条")
                i += 1
                time.sleep(1)  # 降低请求频率

            total = len(review_ids)
            msg += f' 共{total}条评论\n\n'
            print(msg)

            # 确保保存目录存在
            if not os.path.exists(self.save_dir):
                os.makedirs(self.save_dir)

            # 构建完整文件路径
            file_path = os.path.join(self.save_dir, f'{self.title}.md')

            # 写入标题信息
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(msg)

            # 下载每条评论
            print(f"开始下载{total}条评论...")
            for idx, cid in enumerate(review_ids[::-1]):
                # 检查是否已被用户终止
                if hasattr(self, 'is_running') and not self.is_running:
                    break

                print(f"正在下载第{idx + 1}/{total}条评论")
                review = Review(cid, self.title, self.save_dir)
                review.down_one_review()

                # 更新进度条
                if self.progress_callback:
                    self.progress_callback(int((idx + 1) / total * 100))

            if hasattr(self, 'is_running') and self.is_running:
                print('所有评论下载完毕！')
                print(f'文件已保存为: {file_path}')
                return True
            else:
                print('下载已终止')
                return False
        except Exception as e:
            print(f"下载评论时出错: {str(e)}")
            return False


class NovelReviewCrawlerGUI:
    """GUI界面"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SF轻小说长评下载器")
        self.root.geometry("800x600")
        self.root.resizable(True, True)

        # 设置中文字体
        self.setup_fonts()

        # 默认保存目录为用户文档
        self.save_dir = os.path.join(os.path.expanduser('~'), 'Documents', '小说评论')

        # 创建界面组件
        self.create_widgets()

        # 标志位，用于控制线程
        self.is_running = False
        self.book_reviews = None

        # 添加状态栏
        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        self.status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def setup_fonts(self):
        """设置支持中文的字体"""
        default_font = ('SimHei', 10)
        self.root.option_add("*Font", default_font)

    def create_widgets(self):
        """创建GUI组件"""
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # URL输入区域
        url_frame = ttk.LabelFrame(main_frame, text="小说URL", padding="5")
        url_frame.pack(fill=tk.X, pady=5)

        ttk.Label(url_frame, text="请输入小说详情页URL:").pack(side=tk.LEFT, padx=5)

        self.url_entry = ttk.Entry(url_frame)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.url_entry.insert(0, "https://m.sfacg.com/b/43708/")  # 默认URL

        # 保存目录选择区域
        dir_frame = ttk.LabelFrame(main_frame, text="保存文件夹", padding="5")
        dir_frame.pack(fill=tk.X, pady=5)

        self.dir_entry = ttk.Entry(dir_frame)
        self.dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.dir_entry.insert(0, self.save_dir)

        self.browse_btn = ttk.Button(dir_frame, text="浏览...", command=self.browse_directory)
        self.browse_btn.pack(side=tk.LEFT, padx=5)

        # 按钮区域
        button_frame = ttk.Frame(main_frame, padding="5")
        button_frame.pack(fill=tk.X, pady=5)

        self.start_btn = ttk.Button(button_frame, text="开始下载", command=self.start_download)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(button_frame, text="停止", command=self.stop_download, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # 进度条
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=5)

        # 输出区域
        output_frame = ttk.LabelFrame(main_frame, text="输出信息", padding="5")
        output_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.output_text.pack(fill=tk.BOTH, expand=True)

        # 重定向标准输出
        self.redirect = RedirectText(self.output_text)

    def browse_directory(self):
        """浏览并选择保存目录"""
        directory = filedialog.askdirectory(
            initialdir=self.save_dir,
            title="选择保存评论的目录"
        )
        if directory:
            self.save_dir = directory
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, directory)
            self.status_var.set(f"保存目录: {directory}")

    def update_progress(self, value):
        """更新进度条和状态栏"""
        self.progress_var.set(value)
        self.status_var.set(f"正在下载... 进度: {value}%")
        self.root.update_idletasks()

    def start_download(self):
        """开始下载评论"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("错误", "请输入小说URL")
            return

        # 支持的网址前缀列表，可以根据实际情况添加或修改
        valid_prefixes = [
            "https://m.sfacg.com/b/",
            "https://www.sfacg.com/b/",
            "https://sfacg.com/b/",
            "https://book.sfacg.com/Novel/",
            # 可以继续添加其他有效的网址前缀
        ]

        # 检查URL是否以任何有效前缀开头
        if not any(url.startswith(prefix) for prefix in valid_prefixes):
            messagebox.showerror(
                "错误", 
                f"请输入正确的小说详情页URL，支持的格式包括:\n{', '.join(valid_prefixes)}"
            )
            return

        # 获取保存目录
        self.save_dir = self.dir_entry.get().strip()
        if not self.save_dir:
            messagebox.showerror("错误", "请选择保存目录")
            return

        # 禁用开始按钮和浏览按钮，启用停止按钮
        self.start_btn.config(state=tk.DISABLED)
        self.browse_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.is_running = True
        self.status_var.set("开始获取评论列表...")

        # 清空输出区域
        self.output_text.configure(state="normal")
        self.output_text.delete(1.0, tk.END)
        self.output_text.configure(state="disabled")

        # 重置进度条
        self.progress_var.set(0)

        # 保存原始的stdout
        self.original_stdout = sys.stdout
        # 重定向stdout到文本框
        sys.stdout = self.redirect

        # 在新线程中执行下载任务，避免UI卡顿
        def download_task():
            try:
                self.book_reviews = BookReviews(url, self.save_dir, self.update_progress)
                self.book_reviews.is_running = True  # 添加运行状态标志
                success = self.book_reviews.download_reviews()
                if success:
                    self.status_var.set("下载完成")
                else:
                    self.status_var.set("下载已终止")
            except Exception as e:
                error_msg = f"发生错误: {str(e)}"
                print(error_msg)
                self.status_var.set(error_msg)
            finally:
                # 恢复stdout
                sys.stdout = self.original_stdout
                # 恢复按钮状态
                self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.browse_btn.config(state=tk.NORMAL))
                self.root.after(0, lambda: self.stop_btn.config(state=tk.DISABLED))
                self.is_running = False
                self.book_reviews = None

        self.download_thread = threading.Thread(target=download_task)
        self.download_thread.start()

    def stop_download(self):
        """停止下载"""
        if messagebox.askyesno("确认", "确定要停止下载吗？"):
            self.is_running = False
            if self.book_reviews:
                self.book_reviews.is_running = False
            self.stop_btn.config(state=tk.DISABLED)
            self.status_var.set("正在停止下载...")
            print("正在停止下载...")


if __name__ == '__main__':
    root = tk.Tk()
    app = NovelReviewCrawlerGUI(root)
    root.mainloop()
