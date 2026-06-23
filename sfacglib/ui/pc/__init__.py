def run_pc():
    try:
        from .app import App
        app = App()
        app.mainloop()
    except ImportError as e:
        print(f'PC UI 依赖缺失: {e}')
        print('安装 tkinter: sudo apt install python3-tk (Linux) 或 brew install python-tk (macOS)')
