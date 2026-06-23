import customtkinter as ctk
from threading import Thread
from sfacglib.audio import Audio
from sfacglib.fetcher import Fetcher
from sfacglib.progress import ProgressTracker


class AudioTab(ctk.CTkFrame):

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

        ctk.CTkLabel(frame, text='有声ID:').grid(row=0, column=0, padx=5)
        self.id_entry = ctk.CTkEntry(frame, placeholder_text='输入有声小说ID')
        self.id_entry.grid(row=0, column=1, sticky='ew', padx=5)

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
            id_text = self.id_entry.get().strip()
            if not id_text:
                self._log('错误: 请输入有声小说ID')
                return

            audio_id = int(id_text)
            output = self.output_entry.get().strip() or './output/'

            self._log(f'开始下载: {audio_id}')

            fetcher = Fetcher()
            tracker = ProgressTracker()
            audio = Audio(audio_id, fetcher=fetcher)
            audio.download(path=output, tracker=tracker)
            tracker.close()

            self._log(f'下载完成: {audio.title}')
        except Exception as e:
            self._log(f'错误: {e}')
        finally:
            self.download_btn.configure(state='normal')
