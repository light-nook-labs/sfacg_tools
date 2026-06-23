import customtkinter as ctk
from .novel_tab import NovelTab
from .comic_tab import ComicTab
from .audio_tab import AudioTab
from .settings_tab import SettingsTab


class App(ctk.CTk):

    def __init__(self):
        super().__init__()

        self.title('SFACG Downloader')
        self.geometry('900x600')

        ctk.set_appearance_mode('dark')
        ctk.set_default_color_theme('blue')

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._create_sidebar()
        self._create_content()

    def _create_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=150, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky='nsew')
        sidebar.grid_rowconfigure(4, weight=1)

        title = ctk.CTkLabel(sidebar, text='SFACG', font=ctk.CTkFont(size=20, weight='bold'))
        title.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.novel_btn = ctk.CTkButton(sidebar, text='小说', command=lambda: self._show_tab('novel'))
        self.novel_btn.grid(row=1, column=0, padx=20, pady=5)

        self.comic_btn = ctk.CTkButton(sidebar, text='漫画', command=lambda: self._show_tab('comic'))
        self.comic_btn.grid(row=2, column=0, padx=20, pady=5)

        self.audio_btn = ctk.CTkButton(sidebar, text='有声', command=lambda: self._show_tab('audio'))
        self.audio_btn.grid(row=3, column=0, padx=20, pady=5)

        self.settings_btn = ctk.CTkButton(sidebar, text='设置', command=lambda: self._show_tab('settings'))
        self.settings_btn.grid(row=5, column=0, padx=20, pady=(5, 20))

    def _create_content(self):
        self.tabs = {
            'novel': NovelTab(self),
            'comic': ComicTab(self),
            'audio': AudioTab(self),
            'settings': SettingsTab(self),
        }

        for tab in self.tabs.values():
            tab.grid(row=0, column=1, sticky='nsew', padx=10, pady=10)

        self._show_tab('novel')

    def _show_tab(self, name: str):
        for tab_name, tab in self.tabs.items():
            if tab_name == name:
                tab.tkraise()
            else:
                tab.lower()
