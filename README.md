# SFACG Spider

[SF轻小说](https://book.sfacg.com) 多内容下载器 — 小说 / 漫画 / 有声 / 评论

> [!NOTE]
> 学习项目，仅供学习使用。API 随时变动，无 CLI。

## 功能

- 小说下载（MD 目录，可通过 convert 转 HTML/EPUB/PDF）
- 漫画下载（JPG 目录，可通过 convert 转 HTML/EPUB/PDF）
- 有声小说下载（MP3 目录）
- 评论下载（长评 + 回复）
- 搜索小说/漫画（关键词搜索、相关推荐、作者作品）
- VIP 章节处理（OCR / LLM 纠错）
- Cookie 持久化登录
- 多线程并发下载

## 安装

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# 可选：OCR 支持（CPU）
uv sync --extra ocr

# 可选：OCR 支持（GPU，需要 NVIDIA CUDA）
uv sync --extra ocr --extra gpu
```

> [!TIP]
> 配置文件 `.env` 可从 `.sample.env` 复制：`cp .sample.env .env`

## Python API

### 下载小说

```python
from sfacglib.novel import Novel
from sfacglib.fetcher import Fetcher
from sfacglib.utils.convert import convert

fetcher = Fetcher()
fetcher.auto_auth()  # 手动认证，非必须

novel = Novel(43708, output_dir='./output/', fetcher=fetcher)
# __init__ 调用 setup() 获取首页 + 目录，生成 catalog.json
# setup() 返回 True 表示成功，False 表示失败（会抛出 InvalidNovelError）
novel.download()                  # 下载所有章节为 .md
novel.download(ext='epub')        # 下载后转换为 epub

# 下载单卷
vol = novel.create_vol(1)
vol.download(novel.dir_path)

# 下载单章
chapter = vol.create_chapter(3)
chapter.download(save_path)

# 下载评论
review = novel.create_review()
review.download()
```

### 下载漫画

```python
from sfacglib.comic import Comic
from sfacglib.utils.convert import convert

comic = Comic('https://manhua.sfacg.com/mh/LYZJ/', output_dir='./output/', fetcher=fetcher)
comic.download()                  # 下载所有章节图片为 .jpg
comic.download(ext='html')        # 下载后转换为 html
```

### 下载有声小说

```python
from sfacglib.audio import Audio

audio = Audio(153, output_dir='./output/', fetcher=fetcher)
audio.download()                  # 下载所有章节为 .mp3
```

### 格式转换

```python
from sfacglib.utils.convert import convert

convert('output/小说目录', formats=['html', 'epub'])
convert('output/漫画目录', formats=['html', 'epub', 'pdf'])
```

### 搜索

```python
from sfacglib.search import search, search_novel_api, get_related, get_author_works

results = search('魔法少女')              # HTML 搜索
results = search_novel_api('转生')        # JSON API（带评分）
results = get_related('43708')            # 相关推荐
results = get_author_works('43708')       # 作者作品

for r in results:
    print(r.id, r.title, r.author, r.url, r.score)
```

## 登录

SFACG 需要 Cookie 登录：

1. 浏览器打开 https://book.sfacg.com/ 并登录
2. F12 → Network → 刷新页面 → 复制任意请求的 `Cookie` 头
3. 写入 `.env` 文件的 `COOKIE=` 字段

> [!NOTE]
> Cookie 文件存储在 `~/.config/sfacg/.cookies.json`，权限为 `0600`（仅当前用户可读写）。
> 验证使用 `passport.sfacg.com/Ajax/GetLoginInfo.ashx` API，PC 站用户信息通过 AJAX 加载，不在 HTML 中。

## ChatBot Agent

`ocr/chatbot.py` 实现了一个 Agent（不仅仅是聊天机器人），可以通过自然语言理解意图，自动执行简单任务。

```python
from sfacglib.ocr import ChatBot, interactive_chat

# 交互式聊天
interactive_chat()

# 纠错 OCR 文本
bot = ChatBot()
bot.correct_ocr_file('input.txt', 'output.txt', context='玄幻小说')
```

## VIP 章节与 OCR

VIP 章节分两种类型（`is_gif` 字段）：

| 类型 | 目录图标 | 下载格式 | 说明 |
|------|---------|---------|------|
| `false` (free/image) | 无图标 / `.icn` + `\ue905` | 正常文本 / `.jpg` | 免费章节或图片 VIP |
| `true` (encrypted) | `.icn_vip` | `.gif` | 加密 VIP，需 OCR 提取文本 |

### OCR 处理方式（仅加密 VIP 需要）

| 方式 | 2014 低配 PC | 现代 PC | 输出 | 适用场景 |
|------|-------------|---------|------|----------|
| 本地 OCR | ~39s | ~5s | 文本 | 需要文字版 |
| OCR + LLM 纠正 | ~66s | ~30s | 纠正文本 | 高质量需求 |

### GPU 加速

OCR 自动检测 GPU 并启用加速，无需手动配置。安装 GPU 支持：

```bash
uv sync --extra ocr --extra gpu
```

## 配置文件

所有持久化配置存储在 `~/.config/sfacg/`：

| 文件 | 说明 |
|------|------|
| `selectors.toml` | CSS 选择器（失效时更新即可，无需改代码） |
| `audiobooks.json` | 有声小说目录缓存 |
| `.cookies.json` | 登录 Cookie（0600 权限） |

包目录中保留 `selectors.toml` 和 `audiobooks.json` 的副本作为备用值，首次运行时自动迁移到配置目录。

## 配置

配置使用 `pydantic-settings`，自动从 `.env` 加载：

```python
from sfacglib.config import settings

print(settings.chatbot_model)
print(settings.llm_api_key)
```

## 项目结构

```
sfacglib/
  base.py           # 抽象基类：Container, Section, Item
  config.py         # 集中常量 + Pydantic Settings + 配置目录迁移
  fetcher.py        # HTTP 请求（轮换 UA、重试、限速、双会话认证）
  auth.py           # Cookie 管理（GetLoginInfo API 验证）
  selectors.py      # CSS 选择器注册表（tomllib）
  selectors.toml    # CSS 选择器定义（备用副本）
  novel.py          # 小说下载器（Novel/NovelVolume/NovelChapter/ReviewComment/Review）
  comic.py          # 漫画下载器（Comic/ComicChapter/ComicPage）
  audio.py          # 有声下载器（Audio/AudioVolume/AudioChapter）
  audiobooks.json   # 有声目录缓存（备用副本）
  search.py         # 搜索 API（关键词、相关推荐、作者作品）
  nlp.py            # NLP 后处理（合并断行）
  progress.py       # 进度追踪（SQLite，批量提交）
  utils/            # 共享工具
    __init__.py     # sanitize_filename, fix_url_protocol, validate_gif, run_tasks, load_json, save_json
    json.py         # JSON 文件工具（load_json, save_json）
    convert.py      # 格式转换（小说/漫画 → HTML/EPUB/PDF）
    epub.py         # EPUB 生成
  ocr/              # OCR 包
    __init__.py     # 导出 ChatBot, ocr_gif, remove_pinyin 等
    engine.py       # OCR 引擎（RapidOCR、去拼音、rec_only、并行、GPU 自动检测）
    chatbot.py      # Agent（tool calling、OCR 纠错）

scripts/
  check_docs.py     # 验证 AGENTS.md 和 README.md 与代码同步

opencode.json       # opencode 项目配置
.env                # 配置（Cookie、Chatbot API）
```

## 三层抽象

| 内容 | Container | Section | Item |
|------|-----------|---------|------|
| 小说 | Novel | NovelVolume | NovelChapter |
| 漫画 | Comic | (flat, chapters as sections) | (pages fetched dynamically) |
| 有声 | Audio | AudioVolume | AudioChapter |
| 书评 | Review | (flat, comments as sections) | (reviews downloaded directly) |

### catalog.json 结构

```json
{
  "id": "43708",
  "title": "小说标题",
  "author": "作者名",
  "cover": "https://...",
  "info_file": "info.md",
  "sections": [
    {
      "idx": 1,
      "title": "第一卷",
      "vol_id": 12345,
      "dir": "vol_001_第一卷",
      "items": [
        {
          "idx": 1,
          "title": "第一章",
          "chapter_id": 67890,
          "is_gif": false,
          "file": "vol_001_第一卷/ch_001_第一章.md"
        }
      ]
    }
  ]
}
```

有声小说的 catalog 额外包含 `mp3_url` 字段（setup 时预取）：

```json
{
  "id": "19",
  "title": "公会看板娘之野望",
  "cover": "https://rss.sfacg.com/web/audio/images/albumCover/...",
  "sections": [
    {
      "idx": 1,
      "title": "第一卷 日渐丰富的日常",
      "dir": "sec_001_第一卷_日渐丰富的日常",
      "items": [
        {
          "idx": 1,
          "title": "1. 失业人士(哑巴)",
          "url": "https://m.sfacg.com/a/699/",
          "mp3_url": "https://rss.sfacg.com/web/audio/files/19/xxx.mp3",
          "file": "sec_001_第一卷_日渐丰富的日常/item_001_1._失业人士(哑巴).mp3"
        }
      ]
    }
  ]
}
```

### 目录结构

```
{title}/
  catalog.json          # 元数据 + 嵌套章节映射
  info.md               # 简介信息（仅小说/漫画）
  sec_{idx}_{name}/     # 卷/章目录
    ch_{idx}_{name}.md  # 章节文件（小说）
    item_{idx}_{name}.mp3  # 音频文件（有声）
```

## License

本项目用于技术学习，请遵守 [SF轻小说](https://book.sfacg.com) 的规章制度。
