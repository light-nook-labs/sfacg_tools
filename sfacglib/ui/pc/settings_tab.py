import customtkinter as ctk
from sfacglib.fetcher import Fetcher


class SettingsTab(ctk.CTkFrame):

    def __init__(self, master):
        super().__init__(master)

        self.grid_columnconfigure(0, weight=1)

        self._create_cookie_section()
        self._create_appearance()

    def _create_cookie_section(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text='Cookie', font=ctk.CTkFont(size=14, weight='bold')).grid(row=0, column=0, padx=10, pady=5, sticky='w')

        self.cookie_text = ctk.CTkTextbox(frame, height=100)
        self.cookie_text.grid(row=1, column=0, sticky='ew', padx=10, pady=5)

        btn_frame = ctk.CTkFrame(frame)
        btn_frame.grid(row=2, column=0, sticky='ew', padx=10, pady=5)

        self.import_btn = ctk.CTkButton(btn_frame, text='导入Cookie', width=120, command=self._import_cookie)
        self.import_btn.pack(side='left', padx=5)

        self.status_label = ctk.CTkLabel(btn_frame, text='')
        self.status_label.pack(side='left', padx=10)

    def _create_appearance(self):
        frame = ctk.CTkFrame(self)
        frame.grid(row=1, column=0, sticky='ew', pady=(0, 10))

        ctk.CTkLabel(frame, text='外观', font=ctk.CTkFont(size=14, weight='bold')).grid(row=0, column=0, padx=10, pady=5, sticky='w')

        ctk.CTkLabel(frame, text='主题:').grid(row=1, column=0, padx=10, pady=5, sticky='w')
        self.theme_var = ctk.StringVar(value='dark')
        self.theme_menu = ctk.CTkOptionMenu(frame, variable=self.theme_var, values=['dark', 'light', 'system'], command=self._change_theme)
        self.theme_menu.grid(row=1, column=1, padx=10, pady=5, sticky='w')

    def _import_cookie(self):
        cookie = self.cookie_text.get('1.0', 'end').strip()
        if not cookie:
            self.status_label.configure(text='请输入Cookie', text_color='red')
            return

        try:
            fetcher = Fetcher()
            fetcher.import_cookies(cookie)
            self.status_label.configure(text='导入成功', text_color='green')
        except Exception as e:
            self.status_label.configure(text=f'导入失败: {e}', text_color='red')

    def _change_theme(self, theme: str):
        ctk.set_appearance_mode(theme)
