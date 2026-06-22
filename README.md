# SFACG Spider

[SF轻小说](https://book.sfacg.com) 多内容下载器 — 小说 / 漫画 / 有声 / 评论

> 学习项目，仅供学习使用

## 功能

- 小说下载（EPUB / MD / HTML / TXT）
- 漫画下载（目录 / HTML / EPUB / PDF）
- 有声小说下载（MP3）
- 评论下载（长评 + 回复）
- 格式转换（漫画目录 → HTML / EPUB / PDF）
- VIP 章节 OCR + LLM 纠错
- 多线程并发下载
- Cookie 持久化登录
- CSS 选择器集中管理

## 安装

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# 可选：OCR 支持
uv sync --extra ocr
```

## 快速开始

```bash
# 下载小说
uv run python main.py novel 43708 -f epub -o ./output/

# 下载小说带评论
uv run python main.py novel 43708 -f epub -r -o ./output/

# 下载漫画
uv run python main.py comic https://manhua.sfacg.com/mh/LYZJ/ -o ./output/

# 下载有声小说
uv run python main.py audio 153 -o ./output/

# 下载评论
uv run python main.py review https://m.sfacg.com/b/43708/ -o ./output/

# 转换漫画格式
uv run python main.py convert output/落樱之剑 -f html,epub,pdf

# OCR 图片
uv run python main.py ocr <image_url_or_path> -o output.txt

# 交互式聊天
uv run python main.py chat

# OCR 纠错
uv run python main.py ocr-fix input.txt -o corrected.txt
uv run python main.py ocr-fix ./ocr_output/ --pattern "*.txt" -c "玄幻小说"
```

## 详细用法

### 小说下载

```bash
uv run python main.py novel <novel_id> -f <format> -o <output_dir>

# 格式：epub（默认）, md, txt, html
# 章节范围：-sc "第一章" -ec "第十章" 或 -c "1-10,20,30-40"
# 卷过滤：-v "第一卷,第二卷"
# 评论：-r
```

### 漫画下载

```bash
uv run python main.py comic <url> -f <format> -o <output_dir>

# 格式：dir（默认）, html, epub, pdf
# HTML 远程图片：--url-mode
# 章节范围：-sc "第1话" -ec "第10话"
```

### 有声小说下载

```bash
uv run python main.py audio <audio_id> -o <output_dir>
# 章节范围：-c "1-10"
```

### 格式转换

```bash
uv run python main.py convert <comic_dir> -f <formats>
# 示例：-f html,epub,pdf
# PDF 边距：-p 20
```

### Chatbot（OCR 纠错）

在 `.env` 中配置：

```env
CHATBOT_BASE_URL=https://your-api-endpoint/v1
CHATBOT_API_KEY=your-api-key
CHATBOT_MODEL=your-model-name
```

```bash
# 交互式聊天（tool calling：读写文件、列表目录）
uv run python main.py chat

# OCR 纠错单文件
uv run python main.py ocr-fix input.txt -o corrected.txt

# OCR 纠错目录
uv run python main.py ocr-fix ./ocr_output/ --pattern "*.txt" -c "玄幻小说，主角名：xxx"
```

## 登录

SFACG 登录需要验证码，不支持密码登录。从浏览器导入 Cookie：

1. 浏览器打开 https://m.sfacg.com/ 并登录
2. F12 → Network → 刷新页面 → 复制任意请求的 `Cookie` 头
3. 写入 `.env` 文件的 `COOKIE=` 字段

## 项目结构

```
sfacglib/
  base.py           # 抽象基类：Container, Section, Item
  config.py         # 集中常量
  fetcher.py        # HTTP 请求（轮换 UA、重试、限速、认证）
  auth.py           # Cookie 管理
  selectors.py      # CSS 选择器注册表
  ch.py             # 章节内容抓取（移动端 + PC + VIP）
  novel.py          # 小说下载器
  comic.py          # 漫画下载器
  audio.py          # 有声下载器
  epub.py           # EPUB 生成
  convert.py        # 格式转换
  vip.py            # VIP 章节处理
  ocr.py            # OCR 引擎（RapidOCR）
  ocr_fast.py       # 优化 OCR（去拼音、rec_only、并行）
  chatbot.py        # 聊天机器人（tool calling、OCR 纠错）
  nlp.py            # NLP 后处理（合并断行）
  progress.py       # 进度追踪（SQLite）
  utils.py          # 共享工具

main.py             # CLI 入口
.env                # 配置（Cookie、Chatbot API）
```

## 三层抽象

所有内容类型遵循 Container → Section → Item 层次：

| 内容 | Container | Section | Item |
|------|-----------|---------|------|
| 小说 | Novel | NovelVolume | NovelChapter |
| 漫画 | Comic | ComicChapter | ComicPage |
| 有声 | Audio | AudioVolume | AudioChapter |

下载产物目录结构：

```
{title}/
  catalog.json          # 元数据 + 章节映射
  vol_{idx}_{name}/     # 卷目录
    ch_{idx}_{name}.md  # 章节文件
```

## VIP 章节

VIP 章节通过 `.icn_vip` 标记检测，下载为 GIF 格式。

### OCR 流程

```
GIF → 帧提取 → 分行 → 去拼音 → RapidOCR → NLP 合并断行 → [可选] LLM 纠错
```

- `ocr_fast.py`：本地 OCR，纯 CPU，~57s/GIF
- `chatbot.py`：LLM 纠错，修正错别字和伪影

## CSS 选择器

所有选择器位于 `sfacglib/selectors.json`。失效时更新 JSON 即可，无需改代码。

## License

本项目用于技术学习，请遵守 [SF轻小说](https://book.sfacg.com) 的规章制度。
