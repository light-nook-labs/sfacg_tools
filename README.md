# SFACG Spider

[SF轻小说](https://book.sfacg.com) 多内容下载器 — 小说 / 漫画 / 有声 / 评论

> 学习项目，仅供学习使用

## 功能

- [x] 小说下载（EPUB / MD / HTML / TXT）
- [x] 漫画下载（按章节）
- [x] 有声小说下载（MP3）
- [x] 评论下载（长评 + 回复）
- [x] 现代 Material Design UI（Flet）
- [x] 多线程并发下载
- [x] 进度条显示
- [x] Cookie 持久化登录
- [x] CSS 选择器集中管理

## 安装

```bash
# 安装 uv（如果没有）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装依赖
uv sync

# 安装 tesseract（OCR，可选）
sudo apt-get install -y tesseract-ocr tesseract-ocr-chi-sim
```

## 运行

```bash
# 桌面 GUI
uv run python app.py

# Web 浏览器
uv run flet run app.py --web

# CLI
uv run python main.py novel 43708 -f epub
uv run python main.py comic https://mm.sfacg.com/b/ZXNWM/
uv run python main.py audio 153
uv run python main.py review https://m.sfacg.com/b/43708/
```

## 打包

```bash
# 桌面可执行文件
./build.sh desktop

# Android APK（需要 Android SDK）
./build.sh apk

# iOS（需要 macOS + Xcode）
./build.sh ios

# Web 静态文件
./build.sh web
```

## 登录

SFACG 登录需要验证码，不支持密码登录。请从浏览器导入 Cookie：

1. 浏览器打开 https://m.sfacg.com/ 并登录
2. F12 → Network → 刷新页面 → 点任意请求 → 复制 `Cookie` 头的值
3. 在 App 中粘贴导入

## 项目结构

```
sfacglib/          核心库
  config.py        常量配置
  fetcher.py       HTTP 请求（轮换 UA、重试、限速）
  auth.py          登录认证
  selectors.py     CSS 选择器注册表
  selectors.json   选择器配置
  ch.py            章节抓取
  book.py          小说下载
  comic.py         漫画下载
  audio.py         有声下载
  epub.py          EPUB 生成
app.py             Flet GUI
main.py            CLI 入口
review.py          评论下载
build.sh           打包脚本
```

## License

本项目用于技术学习，请遵守 [SF轻小说](https://book.sfacg.com) 的规章制度。
