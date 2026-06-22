import json
from pathlib import Path
from openai import OpenAI
from loguru import logger

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
            'name': 'correct_ocr_text',
            'description': 'Correct OCR errors in Chinese text. Fixes garbled characters, missing punctuation, broken paragraphs, and OCR artifacts.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'text': {'type': 'string', 'description': 'The raw OCR text to correct'},
                    'context': {'type': 'string', 'description': 'Optional context about the content (e.g. novel genre, character names)'},
                },
                'required': ['text'],
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


def _load_env():
    env_path = Path(__file__).parent.parent / '.env'
    if not env_path.exists():
        return {}
    config = {}
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            k, v = line.split('=', 1)
            k, v = k.strip(), v.strip()
            if k and v:
                config[k] = v
    return config


class ChatBot:

    def __init__(
        self,
        base_url: str = '',
        api_key: str = '',
        model: str = '',
        system_prompt: str = '',
        max_turns: int = 20,
    ):
        env = _load_env()
        self.base_url = base_url or env.get('CHATBOT_BASE_URL', '')
        self.api_key = api_key or env.get('CHATBOT_API_KEY', '')
        self.model = model or env.get('CHATBOT_MODEL', '')

        if not self.base_url or not self.api_key or not self.model:
            raise ValueError(
                'Missing config. Set CHATBOT_BASE_URL, CHATBOT_API_KEY, CHATBOT_MODEL in .env, '
                'or pass base_url/api_key/model directly.'
            )

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.max_turns = max_turns
        self.system_prompt = system_prompt
        self.messages: list[dict] = []
        if system_prompt:
            self.messages.append({'role': 'system', 'content': system_prompt})

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
                result = self._exec_tool(tc.function.name, args)
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
            elif name == 'correct_ocr_text':
                return self._tool_correct_ocr(args['text'], args.get('context', ''))
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

    def reset(self):
        self.messages = []
        if self.system_prompt:
            self.messages.append({'role': 'system', 'content': self.system_prompt})

    def correct_ocr_file(self, input_path: str, output_path: str = '', context: str = '') -> str:
        p = Path(input_path)
        if not p.exists():
            raise FileNotFoundError(f'File not found: {input_path}')

        text = p.read_text(encoding='utf-8')
        logger.info(f'Read {len(text)} chars from {input_path}')

        corrected = self._tool_correct_ocr(text, context)
        logger.info(f'Corrected: {len(corrected)} chars')

        out = Path(output_path) if output_path else p.with_name(p.stem + '_corrected' + p.suffix)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(corrected, encoding='utf-8')
        logger.info(f'Saved to {out}')
        return str(out)

    def correct_ocr_dir(self, dir_path: str, pattern: str = '*.txt', context: str = '') -> list[str]:
        d = Path(dir_path)
        if not d.exists():
            raise FileNotFoundError(f'Directory not found: {dir_path}')

        files = sorted(d.rglob(pattern))
        results = []
        for i, f in enumerate(files, 1):
            logger.info(f'[{i}/{len(files)}] {f.name}')
            try:
                out = self.correct_ocr_file(str(f), context=context)
                results.append(out)
            except Exception as e:
                logger.error(f'Failed: {f.name} - {e}')
        return results


def interactive_chat(base_url: str = '', api_key: str = '', model: str = ''):
    bot = ChatBot(base_url=base_url, api_key=api_key, model=model)
    print(f'ChatBot ready ({bot.model})')
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
