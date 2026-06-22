# SFACG Spider

[SF轻小说](https://book.sfacg.com) 多内容下载器 — 小说 / 漫画 / 有声 / 评论

> 学习项目，仅供学习使用

## 功能

- [x] 小说下载（EPUB / MD / HTML / TXT）
- [x] 漫画下载（目录 / HTML / EPUB / PDF）
- [x] 有声小说下载（MP3）
- [x] 评论下载（长评 + 回复）
- [x] 格式转换（漫画目录 → HTML / EPUB / PDF）
- [x] 三种 UI（PC / Mobile / Web）
- [x] 多线程并发下载
- [x] 单进度条显示
- [x] Cookie 持久化登录
- [x] CSS 选择器集中管理
- [x] 流式写入防止数据丢失
- [x] 目录模式便于断点续传
- [x] OCR + LLM 纠错（VIP 章节）

## 安装

```bash
# 安装 uv（如果没有）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安装依赖
uv sync

# 安装 OCR 支持（可选）
uv sync --extra ocr

# 安装 PDF 导出（可选）
uv add reportlab

# 安装 EPUB 导出（可选）
uv add ebooklib
```

## 快速开始

### CLI 命令

```bash
# 下载小说（EPUB）
uv run python main.py novel 43708 -f epub -o ./output/

# 下载小说带评论
uv run python main.py novel 43708 -f epub -r -o ./output/

# 下载漫画（目录模式）
uv run python main.py comic https://manhua.sfacg.com/mh/LYZJ/ -o ./output/

# 下载漫画（EPUB）
uv run python main.py comic https://manhua.sfacg.com/mh/LYZJ/ -f epub -o ./output/

# 下载有声小说
uv run python main.py audio 153 -o ./output/

# 下载评论
uv run python main.py review https://m.sfacg.com/b/43708/ -o ./output/

# 转换漫画格式
uv run python main.py convert output/落樱之剑 -f html,epub,pdf

# OCR 图片
uv run python main.py ocr <image_url_or_path> -o output.txt

# 交互式聊天（tool-calling agent）
uv run python main.py chat

# OCR 纠错（单文件）
uv run python main.py ocr-fix input.txt -o corrected.txt

# OCR 纠错（批量目录）
uv run python main.py ocr-fix ./ocr_output/ --pattern "*.txt" -c "玄幻小说，主角名：xxx"
```

### GUI

```bash
# PC GUI（CustomTkinter）
uv run python main.py app

# Mobile GUI（Flet/Flutter）
uv run python main.py mobile --target app

# Web UI（FastAPI）
uv run python main.py web

# 打包 APK
uv run python main.py mobile --target apk
```

## 详细用法

### 小说下载

```bash
# 基本用法
uv run python main.py novel <novel_id> -f <format> -o <output_dir>

# 格式选项
#   epub  - EPUB 电子书（默认）
#   md    - Markdown
#   txt   - 纯文本
#   html  - HTML

# 示例
uv run python main.py novel 43708 -f epub -o ./output/
uv run python main.py novel 43708 -f md -o ./output/
uv run python main.py novel 43708 -f html -o ./output/

# 带评论下载
uv run python main.py novel 43708 -f epub -r -o ./output/

# 章节范围
uv run python main.py novel 43708 -f epub -sc "第一章" -ec "第十章"
uv run python main.py novel 43708 -f epub -c "1-10,20,30-40"

# 卷过滤
uv run python main.py novel 43708 -f epub -v "第一卷,第二卷"
```

### 漫画下载

```bash
# 基本用法
uv run python main.py comic <url> -f <format> -o <output_dir>

# 格式选项
#   dir   - 目录模式（默认）
#   html  - HTML 文件
#   epub  - EPUB 电子书
#   pdf   - PDF 文件

# 示例
uv run python main.py comic https://manhua.sfacg.com/mh/LYZJ/ -f dir -o ./output/
uv run python main.py comic https://manhua.sfacg.com/mh/LYZJ/ -f epub -o ./output/
uv run python main.py comic https://manhua.sfacg.com/mh/LYZJ/ -f pdf -o ./output/

# HTML 使用远程 URL（不下载图片）
uv run python main.py comic https://manhua.sfacg.com/mh/LYZJ/ -f html --url-mode

# 章节范围
uv run python main.py comic https://manhua.sfacg.com/mh/LYZJ/ -f epub -sc "第1话" -ec "第10话"
```

### 格式转换

```bash
# 转换已下载的漫画目录
uv run python main.py convert <comic_dir> -f <formats>

# 示例
uv run python main.py convert output/落樱之剑 -f html,epub,pdf

# PDF 自定义边距
uv run python main.py convert output/落樱之剑 -f pdf -p 20
```

### 有声小说下载

```bash
# 基本用法
uv run python main.py audio <audio_id> -o <output_dir>

# 示例
uv run python main.py audio 153 -o ./output/

# 章节范围
uv run python main.py audio 153 -c "1-10"
```

## 项目结构

```
sfacglib/
  __init__.py         # 包导出
  base.py             # 抽象基类：Container, Section, Item
  config.py           # 集中常量（URL、路径、线程数）
  fetcher.py          # HTTP 请求（轮换 UA、重试、限速、认证）
  auth.py             # 登录、会话持久化、Cookie 管理
  selectors.py        # CSS 选择器注册表
  selectors.json      # 所有 CSS 选择器
  ch.py               # 章节内容抓取（移动端 + PC + VIP）
  novel.py            # 小说下载器（NovelVolume, NovelChapter, ReviewComment）
  comic.py            # 漫画下载器（ComicChapter, ComicPage）
  audio.py            # 有声下载器（AudioVolume, AudioChapter）
  epub.py             # EPUB 生成
  convert.py          # 格式转换（HTML, EPUB, PDF）
  vip.py              # VIP 章节处理（图片下载、GIF→PNG、OCR）
  ocr.py              # OCR 引擎（RapidOCR、图像预处理）
  ocr_fast.py         # 优化本地 OCR（智能去拼音、rec_only 模式、并行识别）
  llm_vision.py       # LLM Vision API
  web_llm_vision.py   # 浏览器 LLM Vision
  chatbot.py          # OpenAI 兼容聊天机器人（tool calling、OCR 纠错）
  nlp.py              # NLP 后处理（合并图片宽度导致的断行）
  progress.py         # 进度追踪（SQLite）
  utils.py            # 共享工具
  audiobooks.json     # 有声书目录缓存
  ui/
    __init__.py       # UI 入口
    pc/
      __init__.py
      app.py          # CustomTkinter 主窗口
      novel_tab.py    # 小说标签页
      comic_tab.py    # 漫画标签页
      audio_tab.py    # 有声标签页
      settings_tab.py # 设置标签页
    mobile/
      __init__.py
      app.py          # Flet 移动端（Flutter）
    web/
      __init__.py
      server.py       # FastAPI Web 服务器
      templates/
        index.html    # Web UI 模板

main.py               # 统一 CLI 入口
buildozer.spec        # Android APK 构建配置
.env                  # 配置文件（Cookie、Chatbot API）
```

## 三层抽象

所有内容类型遵循三层层次结构：

| 内容 | Container | Section | Item |
|------|-----------|---------|------|
| 小说 | Novel | NovelVolume | NovelChapter |
| 漫画 | Comic | ComicChapter | ComicPage |
| 有声 | Audio | AudioVolume | AudioChapter |
| 评论 | Novel | ReviewSection | ReviewComment |

### 目录结构

```
{title}/
  catalog.json          # 元数据 + 章节映射
  info.md               # 内容信息
  001_{section_title}/  # 卷/章节（带 ID 前缀）
    001_{item_title}.md # 章节/页面（带 ID 前缀）
    002_{item_title}.md
  002_{section_title}/
    ...
```

## 登录

SFACG 登录需要验证码，不支持密码登录。请从浏览器导入 Cookie：

1. 浏览器打开 https://m.sfacg.com/ 并登录
2. F12 → Network → 刷新页面 → 点任意请求 → 复制 `Cookie` 头的值
3. 在 App 中粘贴导入

### CLI 导入

```bash
uv run python -c "
from sfacglib.fetcher import Fetcher
f = Fetcher()
f.import_cookies('paste_your_cookie_string_here')
"
```

## Chatbot（OCR 纠错）

在 `.env` 中配置 LLM API：

```env
CHATBOT_BASE_URL=https://your-api-endpoint/v1
CHATBOT_API_KEY=your-api-key
CHATBOT_MODEL=your-model-name
```

使用：

```bash
# 交互式聊天（支持 tool calling：读写文件、列表目录）
uv run python main.py chat

# OCR 纠错单文件
uv run python main.py ocr-fix input.txt -o corrected.txt

# OCR 纠错目录（批量）
uv run python main.py ocr-fix ./ocr_output/ --pattern "*.txt" -c "小说类型、角色名等上下文"
```

## CSS 选择器

所有 CSS 选择器位于 `sfacglib/selectors.json`。当选择器失效时：

1. 使用 chrome-devtools-mcp 诊断
2. 更新 `selectors.json`
3. 无需修改代码

## VIP 章节

VIP 章节在目录解析时通过 `.icn_vip` 标记检测。

**重要：只有 GIF 格式才是有效的 VIP 章节内容。** 如果获取到的图片不是 GIF，说明 VIP 内容未成功获取。

### OCR 方案

#### 方案 1：本地 OCR + NLP（推荐）

离线、纯 CPU、速度最快。

```
GIF → 帧提取 → 分行 → 智能去拼音（笔画连续性分析） → RapidOCR 识别（rec_only 模式） → NLP 合并断行
```

- `ocr_fast.py`：优化版本地 OCR，6x faster
- `nlp.py`：合并图片宽度导致的断行
- 性能：~57s/GIF，50 字/s，纯 CPU，4 线程

#### 方案 2：DeepSeek Web LLM OCR

浏览器自动化，准确率最高但较慢，有少量幻觉错误。

```
GIF → 帧提取 → 分段（1500px） → 上传 DeepSeek Vision → 识别文本 → 去空格 → 去重
```

- `web_llm_vision.py`：DeepSeek Web LLM OCR
- 性能：~92s/GIF，23.5 字/s，需要浏览器 + 网络

#### 性能对比（同一 GIF: ch_081）

| 方案 | 时间 | 字数 | 准确率 |
|------|------|------|--------|
| 本地 OCR | 39.2s | 2020 | 低（乱码、错字） |
| 本地 OCR + LLM 纠正 | 66.4s | 2074 | 高（修正所有乱码） |
| DeepSeek Web LLM | 91.7s | 2153 | 近 100%（少量幻觉） |

**建议：** 日常用本地 OCR + NLP，高质量需求用 LLM 纠正。

## 并发模型

- 章节级：`ThreadPoolExecutor(max_workers=8)` 并发下载多章
- 页面级：每章内部 `ThreadPoolExecutor(max_workers=8)` 并发下载多页
- 进度条：单 `tqdm` + `threading.Lock` 线程安全更新

## 依赖

```bash
# 核心
uv sync

# OCR 支持（本地 OCR）
uv sync --extra ocr
# 安装 playwright（Web LLM OCR）
uv sync --extra web && uv run playwright install chromium

# EPUB 导出
uv add ebooklib

# PDF 导出
uv add reportlab
```

## 流式写入

所有格式默认目录模式，每章独立文件：

- `txt/md` → 单文件流式写入
- `html` → 目录模式（每章独立 HTML）
- `epub` → 从目录转换
- `pdf` → 从目录转换

## 打包

```bash
# Android APK
uv run python main.py mobile --target apk

# 桌面可执行文件
./build.sh desktop
```

## License

本项目用于技术学习，请遵守 [SF轻小说](https://book.sfacg.com) 的规章制度。
