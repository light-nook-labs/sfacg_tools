import json
import os
import subprocess
from pathlib import Path
from openai import OpenAI
from loguru import logger

AGENT_SYSTEM_PROMPT = """你是 SFACG Spider 的智能助手，可以通过自然语言帮助用户完成以下任务：

1. **去拼音**：对 VIP GIF 去除拼音注音，生成可阅读的图像
2. **OCR 识别**：将 GIF 图片识别为文本
3. **OCR 纠错**：纠正 OCR 文本中的错别字
4. **格式转换**：漫画目录转换为 HTML/EPUB/PDF
5. **文件操作**：读写文件、列出目录
6. **信息查询**：查看目录结构、文件内容

你可以调用工具来执行这些任务。当用户描述一个任务时，分析意图并调用合适的工具。

常用路径规则：
- GIF 文件通常在 output/ 目录下
- 输出文件通常保存到同目录，添加 _de_pinyin 或 _corrected 后缀
- .env 文件包含配置信息

回复要简洁，只报告结果。"""

TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'read_file',
            'description': 'Read the contents of a file',
            'parameters': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': 'File path to read'},
                },
                'required': ['path'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'write_file',
            'description': 'Write content to a file, creating directories if needed',
            'parameters': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': 'File path to write'},
                    'content': {'type': 'string', 'description': 'Content to write'},
                },
                'required': ['path', 'content'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'list_dir',
            'description': 'List files and directories in a path',
            'parameters': {
                'type': 'object',
                'properties': {
                    'path': {'type': 'string', 'description': 'Directory path to list'},
                    'pattern': {'type': 'string', 'description': 'Glob pattern to filter, e.g. "*.txt"'},
                },
                'required': ['path'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'remove_pinyin',
            'description': 'Remove pinyin annotations from VIP GIF image. Returns a clean readable image without pinyin. Much faster than OCR (0.2s vs 39s).',
            'parameters': {
                'type': 'object',
                'properties': {
                    'input_path': {'type': 'string', 'description': 'Path to the GIF file'},
                    'output_path': {'type': 'string', 'description': 'Output image path (default: *_de_pinyin.png)'},
                },
                'required': ['input_path'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'ocr_gif',
            'description': 'OCR a VIP GIF image to text. Extracts text from the image using line detection + pinyin removal + RapidOCR.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'input_path': {'type': 'string', 'description': 'Path to the GIF file'},
                    'output_path': {'type': 'string', 'description': 'Output text file path (default: same name with .txt)'},
                },
                'required': ['input_path'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'correct_ocr_text',
            'description': 'Correct OCR errors in Chinese text using LLM.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'text': {'type': 'string', 'description': 'The raw OCR text to correct'},
                    'context': {'type': 'string', 'description': 'Optional context (genre, character names)'},
                },
                'required': ['text'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'correct_ocr_file',
            'description': 'Correct OCR errors in a text file using LLM.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'input_path': {'type': 'string', 'description': 'Path to the text file'},
                    'output_path': {'type': 'string', 'description': 'Output path (default: *_corrected.txt)'},
                    'context': {'type': 'string', 'description': 'Optional context about the content'},
                },
                'required': ['input_path'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'convert_comic',
            'description': 'Convert downloaded comic directory to HTML/EPUB/PDF format.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'dir_path': {'type': 'string', 'description': 'Path to the comic directory'},
                    'formats': {'type': 'string', 'description': 'Output formats, comma separated (e.g. "html,epub,pdf")'},
                },
                'required': ['dir_path'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'batch_remove_pinyin',
            'description': 'Remove pinyin from all GIF files in a directory.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'dir_path': {'type': 'string', 'description': 'Directory containing GIF files'},
                    'pattern': {'type': 'string', 'description': 'File pattern (default: *.gif)'},
                },
                'required': ['dir_path'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'batch_ocr',
            'description': 'OCR all GIF files in a directory to text files.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'dir_path': {'type': 'string', 'description': 'Directory containing GIF files'},
                    'pattern': {'type': 'string', 'description': 'File pattern (default: *.gif)'},
                },
                'required': ['dir_path'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'batch_correct_ocr',
            'description': 'Correct OCR errors in all text files in a directory.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'dir_path': {'type': 'string', 'description': 'Directory containing text files'},
                    'pattern': {'type': 'string', 'description': 'File pattern (default: *.txt)'},
                    'context': {'type': 'string', 'description': 'Optional context about the content'},
                },
                'required': ['dir_path'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'run_command',
            'description': 'Run a shell command. Use for advanced operations not covered by other tools.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'command': {'type': 'string', 'description': 'Shell command to run'},
                },
                'required': ['command'],
            },
        },
    },
]

CORRECT_OCR_SYSTEM_PROMPT = """你是一个专业的中文OCR文本纠错助手。你的任务是纠正OCR识别产生的错误，包括：

1. 乱码/错别字：修正识别错误的汉字（如"已"→"己"，"末"→"未"）
2. 标点符号：修正全角/半角混用、缺失的标点
3. 段落断行：合并被错误断开的句子，保留合理的段落分隔
4. OCR伪影：删除页码、页眉页脚、乱码符号等非正文内容
5. 繁简转换：如有需要，统一为简体中文

规则：
- 保持原文风格和语气不变
- 不要添加或删减内容
- 不要改变原文意思
- 只修正明显的OCR错误，不要"润色"文字
- 如果原文看起来已经正确，直接返回原文
- 返回纠正后的纯文本，不要加任何解释"""


class ChatBot:

    def __init__(
        self,
        base_url: str = '',
        api_key: str = '',
        model: str = '',
        system_prompt: str = '',
        max_turns: int = 30,
    ):
        self.base_url = base_url or os.environ.get('CHATBOT_BASE_URL', '')
        self.api_key = api_key or os.environ.get('CHATBOT_API_KEY', '')
        self.model = model or os.environ.get('CHATBOT_MODEL', '')

        if not self.base_url or not self.api_key or not self.model:
            raise ValueError(
                'Missing config. Set CHATBOT_BASE_URL, CHATBOT_API_KEY, CHATBOT_MODEL in .env, '
                'or pass base_url/api_key/model directly.'
            )

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.max_turns = max_turns
        self.system_prompt = system_prompt or AGENT_SYSTEM_PROMPT
        self.messages: list[dict] = []
        self.messages.append({'role': 'system', 'content': self.system_prompt})

    def chat(self, user_input: str) -> str:
        self.messages.append({'role': 'user', 'content': user_input})

        for turn in range(self.max_turns):
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=TOOLS,
                max_tokens=4096,
            )

            if not resp.choices:
                raise RuntimeError('Empty response from LLM')

            msg = resp.choices[0].message
            self.messages.append(msg.model_dump(exclude_none=True))

            if not msg.tool_calls:
                return msg.content or ''

            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments)
                logger.info(f'Tool call: {tc.function.name}({args})')
                result = self._exec_tool(tc.function.name, args)
                logger.info(f'Tool result: {result[:200]}...' if len(result) > 200 else f'Tool result: {result}')
                self.messages.append({
                    'role': 'tool',
                    'tool_call_id': tc.id,
                    'content': result,
                })

        return '[达到最大对话轮数]'

    def _exec_tool(self, name: str, args: dict) -> str:
        try:
            if name == 'read_file':
                return self._tool_read_file(args['path'])
            elif name == 'write_file':
                return self._tool_write_file(args['path'], args['content'])
            elif name == 'list_dir':
                return self._tool_list_dir(args['path'], args.get('pattern', '*'))
            elif name == 'remove_pinyin':
                return self._tool_remove_pinyin(args['input_path'], args.get('output_path', ''))
            elif name == 'ocr_gif':
                return self._tool_ocr_gif(args['input_path'], args.get('output_path', ''))
            elif name == 'correct_ocr_text':
                return self._tool_correct_ocr(args['text'], args.get('context', ''))
            elif name == 'correct_ocr_file':
                return self._tool_correct_ocr_file(args['input_path'], args.get('output_path', ''), args.get('context', ''))
            elif name == 'convert_comic':
                return self._tool_convert_comic(args['dir_path'], args.get('formats', 'html,epub,pdf'))
            elif name == 'batch_remove_pinyin':
                return self._tool_batch_remove_pinyin(args['dir_path'], args.get('pattern', '*.gif'))
            elif name == 'batch_ocr':
                return self._tool_batch_ocr(args['dir_path'], args.get('pattern', '*.gif'))
            elif name == 'batch_correct_ocr':
                return self._tool_batch_correct_ocr(args['dir_path'], args.get('pattern', '*.txt'), args.get('context', ''))
            elif name == 'run_command':
                return self._tool_run_command(args['command'])
            else:
                return f'Unknown tool: {name}'
        except Exception as e:
            return f'Error: {e}'

    def _tool_read_file(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            return f'File not found: {path}'
        if p.stat().st_size > 500_000:
            return f'File too large ({p.stat().st_size} bytes). Read a smaller file or use list_dir first.'
        return p.read_text(encoding='utf-8')

    def _tool_write_file(self, path: str, content: str) -> str:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        return f'Wrote {len(content)} chars to {path}'

    def _tool_list_dir(self, path: str, pattern: str = '*') -> str:
        p = Path(path)
        if not p.exists():
            return f'Directory not found: {path}'
        entries = sorted(p.glob(pattern))
        lines = []
        for e in entries[:100]:
            kind = 'd' if e.is_dir() else 'f'
            size = e.stat().st_size if e.is_file() else 0
            lines.append(f'[{kind}] {e.name} ({size}B)')
        if len(entries) > 100:
            lines.append(f'... and {len(entries) - 100} more')
        return '\n'.join(lines) or '(empty)'

    def _tool_remove_pinyin(self, input_path: str, output_path: str = '') -> str:
        from .ocr_fast import remove_pinyin_gif
        p = Path(input_path)
        if not p.exists():
            return f'File not found: {input_path}'
        if not p.suffix.lower() == '.gif':
            return f'Not a GIF file: {input_path}'
        gif_bytes = p.read_bytes()
        img = remove_pinyin_gif(gif_bytes)
        out = Path(output_path) if output_path else p.with_name(p.stem + '_de_pinyin.png')
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out))
        return f'Done: {out} ({img.width}x{img.height})'

    def _tool_ocr_gif(self, input_path: str, output_path: str = '') -> str:
        from .ocr_fast import ocr_gif
        from .nlp import merge_wrapped_lines
        p = Path(input_path)
        if not p.exists():
            return f'File not found: {input_path}'
        gif_bytes = p.read_bytes()
        raw = ocr_gif(gif_bytes)
        text = merge_wrapped_lines(raw)
        out = Path(output_path) if output_path else p.with_suffix('.txt')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding='utf-8')
        return f'Done: {out} ({len(text)} chars)'

    def _tool_correct_ocr(self, text: str, context: str = '') -> str:
        prompt = f'请纠正以下OCR文本中的错误：\n\n{text}'
        if context:
            prompt = f'背景信息：{context}\n\n{prompt}'
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {'role': 'system', 'content': CORRECT_OCR_SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt},
            ],
            max_tokens=4096,
        )
        return resp.choices[0].message.content or text

    def _tool_correct_ocr_file(self, input_path: str, output_path: str = '', context: str = '') -> str:
        p = Path(input_path)
        if not p.exists():
            return f'File not found: {input_path}'
        text = p.read_text(encoding='utf-8')
        corrected = self._tool_correct_ocr(text, context)
        out = Path(output_path) if output_path else p.with_name(p.stem + '_corrected' + p.suffix)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(corrected, encoding='utf-8')
        return f'Done: {out} ({len(corrected)} chars)'

    def _tool_convert_comic(self, dir_path: str, formats: str = 'html,epub,pdf') -> str:
        from .convert import convert_comic
        from .fetcher import Fetcher
        f = Fetcher()
        f.auto_auth()
        convert_comic(dir_path, formats=formats.split(','), fetcher=f)
        return f'Done: converted {dir_path} to {formats}'

    def _tool_batch_remove_pinyin(self, dir_path: str, pattern: str = '*.gif') -> str:
        d = Path(dir_path)
        if not d.exists():
            return f'Directory not found: {dir_path}'
        files = sorted(d.rglob(pattern))
        if not files:
            return f'No files matching {pattern} in {dir_path}'
        results = []
        for i, f in enumerate(files, 1):
            try:
                logger.info(f'[{i}/{len(files)}] {f.name}')
                result = self._tool_remove_pinyin(str(f))
                results.append(result)
            except Exception as e:
                results.append(f'Failed: {f.name} - {e}')
        return '\n'.join(results)

    def _tool_batch_ocr(self, dir_path: str, pattern: str = '*.gif') -> str:
        d = Path(dir_path)
        if not d.exists():
            return f'Directory not found: {dir_path}'
        files = sorted(d.rglob(pattern))
        if not files:
            return f'No files matching {pattern} in {dir_path}'
        results = []
        for i, f in enumerate(files, 1):
            try:
                logger.info(f'[{i}/{len(files)}] {f.name}')
                result = self._tool_ocr_gif(str(f))
                results.append(result)
            except Exception as e:
                results.append(f'Failed: {f.name} - {e}')
        return '\n'.join(results)

    def _tool_batch_correct_ocr(self, dir_path: str, pattern: str = '*.txt', context: str = '') -> str:
        d = Path(dir_path)
        if not d.exists():
            return f'Directory not found: {dir_path}'
        files = sorted(d.rglob(pattern))
        if not files:
            return f'No files matching {pattern} in {dir_path}'
        results = []
        for i, f in enumerate(files, 1):
            try:
                logger.info(f'[{i}/{len(files)}] {f.name}')
                result = self._tool_correct_ocr_file(str(f), context=context)
                results.append(result)
            except Exception as e:
                results.append(f'Failed: {f.name} - {e}')
        return '\n'.join(results)

    def _tool_run_command(self, command: str) -> str:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=60
        )
        output = result.stdout + result.stderr
        return output[:2000] if output else '(no output)'

    def reset(self):
        self.messages = []
        self.messages.append({'role': 'system', 'content': self.system_prompt})


def interactive_chat(base_url: str = '', api_key: str = '', model: str = ''):
    bot = ChatBot(base_url=base_url, api_key=api_key, model=model)
    print(f'SFACG Agent ready ({bot.model})')
    print('Type "quit" to exit, "reset" to clear history\n')

    while True:
        try:
            user_input = input('You: ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() == 'quit':
            break
        if user_input.lower() == 'reset':
            bot.reset()
            print('(history cleared)\n')
            continue

        try:
            reply = bot.chat(user_input)
            print(f'\nBot: {reply}\n')
        except Exception as e:
            print(f'\nError: {e}\n')
