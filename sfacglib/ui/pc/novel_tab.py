import customtkinter as ctk
from threading import Thread
from sfacglib.novel import Novel
from sfacglib.fetcher import Fetcher
from sfacglib.progress import ProgressTracker


class NovelTab(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._create_input()
        self._create_options()
        self._create_output()

    def _create_input(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text='小说ID:').grid(row=0, column=0, padx=5)
        self.nid_entry = ctk.CTkEntry(frame, placeholder_text='输入小说ID或URL')
        self.nid_entry.grid(row=0, column=1, sticky='ew', padx=5)

        self.download_btn = ctk.CTkButton(frame, text='下载', width=80, command=self._start_download)
        self.download_btn.grid(row=0, column=2, padx=5)

    def _create_options(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text='格式:').grid(row=0, column=0, padx=5)
        self.format_var = ctk.StringVar(value='epub')
        self.format_menu = ctk.CTkOptionMenu(frame, variable=self.format_var, values=['epub', 'md', 'txt', 'html'])
        self.format_menu.grid(row=0, column=1, sticky='w', padx=5)

        self.review_var = ctk.BooleanVar(value=False)
        self.review_check = ctk.CTkCheckBox(frame, text='下载评论', variable=self.review_var)
        self.review_check.grid(row=0, column=2, padx=20)

        ctk.CTkLabel(frame, text='输出目录:').grid(row=1, column=0, padx=5, pady=(5, 0))
        self.output_entry = ctk.CTkEntry(frame, placeholder_text='./output/')
        self.output_entry.grid(row=1, column=1, columnspan=2, sticky='ew', padx=5, pady=(5, 0))

    def _create_output(self):
        self.output_text = ctk.CTkTextbox(self, state='disabled')
        self.output_text.grid(row=2, column=0, sticky='nsew')

    def _log(self, msg: str):
        self.output_text.configure(state='normal')
        self.output_text.insert('end', msg + '\n')
        self.output_text.see('end')
        self.output_text.configure(state='disabled')

    def _start_download(self):
        self.download_btn.configure(state='disabled')
        Thread(target=self._download, daemon=True).start()

    def _download(self):
        try:
            nid_text = self.nid_entry.get().strip()
            import re
            match = re.search(r'(\d+)', nid_text)
            if not match:
                self._log('错误: 无法提取小说ID')
                return

            nid = int(match.group(1))
            file_type = self.format_var.get()
            output = self.output_entry.get().strip() or './output/'
            download_reviews = self.review_var.get()

            self._log(f'开始下载: {nid}')

            fetcher = Fetcher()
            tracker = ProgressTracker()
            novel = Novel(nid, fetcher=fetcher)
            novel.download_novel(
                path=output,
                file_type=file_type,
                tracker=tracker,
                download_reviews=download_reviews,
            )
            tracker.close()

            self._log(f'下载完成: {novel.title}')
        except Exception as e:
            self._log(f'错误: {e}')
        finally:
            self.download_btn.configure(state='normal')
