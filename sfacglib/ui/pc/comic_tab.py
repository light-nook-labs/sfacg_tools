import customtkinter as ctk
from threading import Thread
from sfacglib.comic import Comic
from sfacglib.fetcher import Fetcher
from sfacglib.progress import ProgressTracker


class ComicTab(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._create_input()
        self._create_options()
        self._create_output()

    def _create_input(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text='漫画URL:').grid(row=0, column=0, padx=5)
        self.url_entry = ctk.CTkEntry(frame, placeholder_text='输入漫画URL')
        self.url_entry.grid(row=0, column=1, sticky='ew', padx=5)

        self.download_btn = ctk.CTkButton(frame, text='下载', width=80, command=self._start_download)
        self.download_btn.grid(row=0, column=2, padx=5)

    def _create_options(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(frame, text='输出目录:').grid(row=0, column=0, padx=5)
        self.output_entry = ctk.CTkEntry(frame, placeholder_text='./output/')
        self.output_entry.grid(row=0, column=1, sticky='ew', padx=5)

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
            url = self.url_entry.get().strip()
            if not url:
                self._log('错误: 请输入漫画URL')
                return

            output = self.output_entry.get().strip() or './output/'

            self._log(f'开始下载: {url}')

            fetcher = Fetcher()
            tracker = ProgressTracker()
            comic = Comic(url, fetcher=fetcher)
            comic.download(path=output, tracker=tracker)
            tracker.close()

            self._log(f'下载完成: {comic.title}')
        except Exception as e:
            self._log(f'错误: {e}')
        finally:
            self.download_btn.configure(state='normal')
