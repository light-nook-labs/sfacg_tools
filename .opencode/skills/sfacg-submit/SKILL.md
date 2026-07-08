---
name: sfacg-submit
description: "Use when submitting/editing chapters on SFACG (sfacg.com / i.sfacg.com) via browser editor. Automates navigation, content insertion, title update, and publish confirmation using Chrome DevTools MCP. Works for any novel. Trigger keywords: submit chapter, 提交章节, 上传章节, sfacg, 菠萝包, 替换章节, 编辑章节, 更新章节."
---

# SFACG Chapter Submit Skill

Automates chapter creation/editing on SFACG (sfacg.com) via browser editor. Works for **any** novel on the platform.

## Prerequisites

- Chrome DevTools MCP server connected (or Playwright as fallback)
- Browser authenticated on `i.sfacg.com`
- User is the author of the target novel

## Platform Rules (MUST KNOW)

| Rule | Description |
|------|-------------|
| **No chapter deletion** | Chapters cannot be deleted, only edited. Extra chapters must be repurposed (e.g., "后记"). |
| **Review required** | All changes (content, title, info, cover) go through review (up to 3 business days). Changes are NOT instant. |
| **No text on covers** | Cover images must NOT contain any text (title, author name, labels). Review will reject text. |
| **Risk control** | Rapid operations trigger anti-automation. Session expires on `i.sfacg.com` while `book.sfacg.com` still works. |
| **Unpublished drafts** | New chapters created via `?volumeId=` become drafts if not properly published. |

## Scripts

| File | Purpose |
|------|---------|
| `scripts/sfacg_editor.js` | Browser-side JS helper. Inject once per page, then call `sfacg.*` methods. |
| `scripts/playwright_single.py` | Single chapter create/edit via Playwright (recommended for batch operations). |
| `scripts/playwright_batch.py` | Batch chapter creation via Playwright (restarts browser for each chapter). |

## URLs

| Page | URL Pattern |
|------|-------------|
| Management | `https://i.sfacg.com/MyNovel/manage/{novelId}/update` |
| Edit existing chapter | `https://i.sfacg.com/MyNovel/v2/manage/{novelId}/editor?chapterId={chapterId}` |
| Create new chapter | `https://i.sfacg.com/MyNovel/v2/manage/{novelId}/editor?volumeId={volumeId}` |
| Novel info edit | `https://i.sfacg.com/MyNovel/manage/{novelId}/update` → click "编辑资料" |
| Cover upload | `https://i.sfacg.com/MyNovel/manage/{novelId}/cover` |
| Book page | `https://book.sfacg.com/Novel/{novelId}/` |

## Decision Tree

```
用户请求 → 判断操作类型：
├── 编辑现有章节 → [Workflow: Edit Existing Chapter]
├── 创建新章节 → 判断数量：
│   ├── 单章 → [Workflow: Create New Chapter]
│   └── 多章 → [Workflow: Batch Creation]
├── 修改小说信息 → [Novel Info Update]
├── 上传封面 → [Cover Upload]
└── 发表评论 → [Post Comment]
```

## Workflow: Edit Existing Chapter

### Step 1: Navigate to Editor

**Input**: `novelId` (小说ID), `chapterId` (章节ID)

```
chrome-devtools_navigate_page(type="url", url="https://i.sfacg.com/MyNovel/v2/manage/{novelId}/editor?chapterId={chapterId}")
```

Wait 1s → Step 2

**If redirected to login** → See [Fallback: Session Expired](#fallback-session-expired)

### Step 2: Inject JS Helper (once per page)

**Input**: `scripts/sfacg_editor.js` file content

```
chrome-devtools_evaluate_script(function="<file content>")
```

**Output**: 
- `{ loaded: true }` → Step 3
- `{ error: "no editor" }` → Page not loaded, wait 2s, retry once
- Still fails → abort, report "Editor not loaded" error

### Step 3: Insert Content + Fill Title

**Input**: 
- `CONTENT`: Chapter text, paragraphs separated by `\n`, no markdown heading
- `TITLE`: Title format "第N章 标题" (must include chapter number)

**Content Format Example**:
```
第一段内容，这是开头。

第二段内容，继续叙述。

第三段内容，章节结尾。
```

**Title Format Examples**:
- ✅ "第一章 初遇"
- ✅ "第十五章 暗流涌动"
- ❌ "初遇" (缺少章节号)
- ❌ "第1章 初遇" (应用中文数字)

```
chrome-devtools_evaluate_script(function="() => { const r1 = sfacg.insert(CONTENT); if (r1.error) return r1; const r2 = sfacg.fillTitle(TITLE); if (r2.error) return r2; return { inserted: r1.chars, title: r2.value }; }")
```

**Output**:
- `{ inserted: N, title: "..." }` → Step 4
- `{ error: "..." }` → Content insertion failed, take screenshot, abort

**🔴 CHECKPOINT**: `inserted` ≈ file char count (±10%). If off → [Fallback: Content Truncated](#fallback-content-truncated)

### Step 4: Confirm Edit + Publish

**Input**: None (uses editor state from Step 3)

```
chrome-devtools_evaluate_script(function="() => { const c = sfacg.confirm(); if (c.error) return c; return { confirmed: true }; }")
```

Wait 1s, then:

```
chrome-devtools_evaluate_script(function="() => { const p = sfacg.publish(); if (p.error) return p; return { published: true }; }")
```

Wait 1s → Step 5

**Output**:
- `{ confirmed: true, published: true }` → Step 5
- `{ error: "..." }` → Failed, take screenshot, report error

### Step 5: Verify

Take snapshot. Check URL changed from `editor` to `manage`.

**🔴 CHECKPOINT**: If still on editor page → abort and report error.

## Workflow: Create New Chapter

### Step 1: Navigate to New Chapter Editor

```
chrome-devtools_navigate_page(type="url", url="https://i.sfacg.com/MyNovel/v2/manage/{novelId}/editor?volumeId={volumeId}")
```

Get `volumeId` from management page snapshot (look for "本卷添加新章节" link).

**Step 2-6**: Same as standard workflow.

### Batch Creation (RECOMMENDED: Use Playwright)

**🔴 CHECKPOINT**: Before starting batch, confirm with user:
- "我将使用Playwright逐章创建，每章会重启浏览器。确认继续？"

**⚠️ Important**: Do NOT use Chrome DevTools MCP for batch creation. It will trigger risk control after 1-2 chapters.

**Use Playwright instead**:

```bash
# Create new chapter
python scripts/playwright_single.py --novel-id 681842 --volume-id 896483 --title "第七章 新的开始" --content-file 反派标签_Rewrite/Ch7.md

# Edit existing chapter
python scripts/playwright_single.py --novel-id 681842 --chapter-id 8215598 --title "第一章 标签" --content-file 反派标签_Rewrite/Ch1.md
```

**Input**: 
- `--novel-id`: 小说ID (从URL获取: `i.sfacg.com/MyNovel/manage/{novelId}/update`)
- `--volume-id`: 卷ID (从管理页面获取: "本卷添加新章节"链接)
- `--chapter-id`: 章节ID (从管理页面获取: 章节列表)
- `--title`: 章节标题 (格式: "第N章 标题")
- `--content-file`: 内容文件路径 (相对或绝对路径)

**Key points**:
- Restart browser for each chapter (prevents session accumulation)
- Wait 2-3 seconds between chapters
- Use `launch_persistent_context(user_data_dir=...)` to save login state
- Each chapter must be published before creating the next

## Fallback: Session Expired / Risk Control

**Trigger**: Page redirects to `passport.sfacg.com` or management page also redirects to login.

**Symptoms**:
- `i.sfacg.com` pages redirect to login while `book.sfacg.com` still works
- Happens after 1-3 rapid consecutive operations
- Editor pages (`/editor?`) are more sensitive than management pages

**Recovery**:
1. Tell user: "Session expired. Please login on i.sfacg.com in browser."
2. Wait for user to confirm login
3. Retry operation

**Playwright Fallback** (when MCP session consistently fails):

```bash
# Single chapter - edit existing
python scripts/playwright_single.py --novel-id {id} --chapter-id {id} --title "第N章 标题" --content-file path/to/file.md

# Single chapter - create new
python scripts/playwright_single.py --novel-id {id} --volume-id {id} --title "第N章 标题" --content-file path/to/file.md
```

**Playwright Script Workflow**:
1. Check login status at `passport.sfacg.com`
2. If not logged in, wait for user to scan QR code (up to 2 minutes)
3. Navigate to editor URL
4. Insert content via `window.wangEditor.dangerouslyInsertHtml()`
5. Fill title via input element
6. Click "确认编辑" then "确定发布"
7. Close browser

## Fallback: Content Truncated

**Trigger**: `inserted` chars < 70% of expected

**Fix**:
1. Split content in half
2. Insert first half: `sfacg.insert(firstHalf)`
3. Append second half: `sfacg.insert(secondHalf)` (appends, not replaces)
4. Verify total char count

## Fallback: Title Input Not Found

**Trigger**: `sfacg.fillTitle` returns `{ error: "title input not found" }`

**Fix**:
1. Take snapshot
2. Find textbox with placeholder containing "章节"
3. Use `chrome-devtools_fill(uid=found_uid, value=TITLE)`
4. Continue to Step 4

## Fallback: JS Injection Failed

**Trigger**: `sfacg_editor.js` returns `{ error: "no editor" }` after 2 retries

**Symptoms**:
- Page loaded but WangEditor not initialized
- Editor iframe not accessible

**Fix**:
1. Take screenshot to verify page state
2. Wait 3s for editor to fully load
3. Retry injection once more
4. If still fails → abort and report "Editor initialization failed"
5. Suggest user refresh page and retry manually

## Fallback: Network Error

**Trigger**: Navigation fails or times out

**Symptoms**:
- `navigate_page` returns timeout error
- Page shows connection error

**Fix**:
1. Wait 5s for network to recover
2. Retry navigation once
3. If still fails → abort and report "Network error"
4. Suggest user check network connection

## Fallback: Content Too Long

**Trigger**: Content exceeds editor limit (typically >50,000 chars)

**Symptoms**:
- Insert returns `{ inserted: N }` but N is much less than expected
- Editor becomes unresponsive

**Fix**:
1. Check content length: `len(content)`
2. If > 50,000 chars → split into parts
3. Insert first part, then append remaining parts
4. Verify total char count after all insertions

**Error Message Format**:
```
❌ 操作失败：{操作类型}
原因：{具体错误}
建议：{用户可执行的下一步}
```

## Novel Info Update

**🔴 CHECKPOINT**: Before updating novel info, confirm with user:
- "修改小说信息需要审核（最多3个工作日）。确认修改以下内容：{列出修改项}"

1. Navigate to `https://i.sfacg.com/MyNovel/manage/{novelId}/update`
2. Click "编辑资料"
3. Modify fields:
   - **Status**: Find "状态" dropdown, select "连载中" or "已完结"
   - **Synopsis**: Find "简介" textarea, clear and enter new text
   - **Category**: Find "分类" dropdown, select appropriate category
   - **Tags**: Find "标签" input, add/remove tags
4. Click save button
5. **All changes require review**

## Cover Upload

**🔴 CHECKPOINT**: Before uploading cover, verify with user:
- "封面不能包含任何文字（标题、作者名、标签）。确认图片无文字？"

1. Navigate to `https://i.sfacg.com/MyNovel/manage/{novelId}/cover`
2. Find file input element (usually `<input type="file">`)
3. Use `chrome-devtools_upload_file(uid=input_uid, filePath="path/to/image.png")`
4. Wait for upload to complete
5. **No text allowed** - review will reject

## Post Comment

**🔴 CHECKPOINT**: Before posting comment, confirm with user:
- "作者评论自己的小说要自然（如感谢读者、讨论创作过程），不要像普通读者。确认评论内容？"

1. Navigate to `https://book.sfacg.com/Novel/{novelId}/`
2. Find textarea in comment section
3. Fill comment and click "提交评论"
4. **Note**: Author commenting on own novel should sound natural (e.g., thanking readers), not like a random reader

## Anti-Patterns (DO NOT)

| # | Anti-Pattern | Why | Alternative |
|---|--------------|-----|-------------|
| 1 | Hardcode UIDs | UIDs change every page load | Query DOM or use snapshot |
| 2 | Use paste event | Unreliable, often fails | Always use `dangerouslyInsertHtml` |
| 3 | Skip verification | Content may be truncated | Verify char count after insert |
| 4 | Title without chapter number | Can't track submitted chapters | Always use "第N章 标题" format |
| 5 | Submit multiple chapters via MCP | Triggers risk control after 1-2 chapters | Use Playwright with browser restart |
| 6 | Sleep > 2 seconds | Wastes time, pages load in <1s | Fixed 1-2s sleep |
| 7 | Ignore "已保存到云端" | This is cloud save, NOT submit | Must click 确认编辑 → 确定发布 |
| 8 | Batch create without browser restart | Session accumulates, triggers risk control | Restart browser for each chapter |
| 9 | Try to delete chapters | SFACG doesn't allow deletion | Repurpose as "后记" or reorder |
| 10 | Resubmit same changes | Clogs review queue | Submit once, wait for review |
| 11 | Comment as author praising own novel | Looks fake,读者会发现 | Thank readers or discuss writing process |

## Quick Reference

| 操作 | 工具 | 关键命令 |
|------|------|----------|
| 编辑章节 | MCP | `navigate → inject → insert → confirm → publish → verify` |
| 创建单章 | MCP | 同上，使用 `?volumeId=` URL |
| 创建多章 | Playwright | `python scripts/playwright_single.py` (每章重启浏览器) |
| 修改信息 | MCP | `navigate → click编辑资料 → modify → save` |
| 上传封面 | MCP | `navigate → upload_file` |
| 发表评论 | MCP | `navigate → fill → submit` |

## Common IDs (Reference)

| Novel | ID | Volume ID | Management URL |
|-------|----|-----------|----------------|
| 反派标签 | 681842 | 896483 | `i.sfacg.com/MyNovel/manage/681842/update` |
| 这个家伙不正经 | 665245 | 873334 | `i.sfacg.com/MyNovel/manage/665245/update` |

**Note**: Volume IDs may change. Always verify from management page before batch operations.

## Runtime Compatibility

Works with any Chrome DevTools MCP environment: OpenCode, Claude Code, Codex, Cursor, etc. Playwright fallback available for all Python environments.
