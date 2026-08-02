---
name: pdf2zh
description: |
  PDF英文转中文翻译。使用PDFMathTranslate进行PDF文档翻译，保留公式、图表、布局。
  当用户提到PDF翻译、pdf2zh、英文PDF转中文、科学文档翻译时触发。
version: 1.0.0
license: MIT
compatibility: uv 管理，无需 conda（install.py 一键安装）
---

# PDF to Chinese Translation Skill

PDF 英→中 翻译，基于 [PDFMathTranslate](https://github.com/PDFMathTranslate/PDFMathTranslate)
（Apache-2.0）。保留原版公式、图表与排版，输出**纯中文**与**中英双语**两个 PDF。

## 0. 定位本 skill（每次使用前）

安装器会把 skill 装到：

| Agent      | 路径                                    |
|------------|-----------------------------------------|
| Claude Code | `~/.claude/skills/pdf2zh`             |
| OpenCode    | `~/.config/opencode/skills/pdf2zh`    |

若当前环境没有 `PDF2ZH_SKILL_DIR` 变量，先定位并固定：

```bash
# bash（按实际安装位置调整）
SKILL_DIR="$HOME/.claude/skills/pdf2zh"
set -a; source "$SKILL_DIR/.env"; set +a   # 载入 服务/模型/API key/术语 prompt
```

> `.env` 由 `install.py` 生成：内含 `PDF2ZH_SKILL_DIR`、`PDF2ZH_SERVICE`、
> `PDF2ZH_MODEL`、`PDF2ZH_PROMPT` 与所选服务的 `xxx_API_KEY`。
> 没装过就提示用户先运行 `python install.py`（见仓库 README）。

## 1. 翻译（一行命令）

```bash
"$SKILL_DIR/run.sh" document.pdf -o output/     # bash / Git Bash / macOS
"%SKILL_DIR%\run.cmd" document.pdf -o output\   # Windows cmd / PowerShell
```

`run.sh` / `run.cmd` 自动完成：加载 `.env` → 按配置选服务与模型 →
注入术语约束 prompt → 调用 `pdf2zh`（`.venv` 内的官方包）。

常用选项（直接透传给 pdf2zh）：

```bash
run.sh document.pdf -o output/        # 指定输出目录
run.sh document.pdf -li en -lo zh     # 源/目标语言（默认已是 en->zh）
run.sh --dir /path/to/pdfs/           # 批量翻译整个目录
run.sh -i                             # 启动 GUI 界面
```

输出文件（在输出目录）：
- `<文件名>-mono.pdf` — 纯中文版
- `<文件名>-dual.pdf` — 中英双语版

## 2. 术语约束（避免 LLM 翻出「法学硕士」）

默认 Google 翻译不支持自定义 prompt，`LLM` 常被翻成「法学硕士」。两条修复路线：

### 路线 A：翻译前约束（推荐，仅 LLM 服务）

LLM 服务（`deepseek` / `openai` / `zhipu` / `qwen-mt` / `grok` / `gemini` 等）
支持 `--prompt`，`run.sh` 已自动注入 `assets/prompt.txt`（内置术语表：
`LLM → 大语言模型` 等，支持 `$lang_in` / `$lang_out` / `$text` 占位符）。
改 `"$SKILL_DIR/assets/prompt.txt"` 即可自定义术语。

> `google` / `bing` / `deepl` / `argos` 等机器翻译服务不接受 prompt，路线 A 无效。

### 路线 B：翻译后修补（所有服务通用）

```bash
python "$SKILL_DIR/assets/apply_glossary.py" paper-mono.pdf \
  -g "$SKILL_DIR/assets/glossary.txt" -o paper-mono-fixed.pdf
```

用 PyMuPDF 在原文位置盖白块、叠写正确术语，周边排版不变。
模板 `assets/glossary.txt` 已预置 LLM 常见词条；长词组放短词组前；字面量匹配。

典型工作流：

```bash
"$SKILL_DIR/run.sh" paper.pdf -o out/                 # 1. 翻译
python "$SKILL_DIR/assets/apply_glossary.py" \
  out/paper-mono.pdf -g my-glossary.txt -o out/fixed.pdf   # 2. 修补
```

## 3. 支持的翻译服务（pdf2zh v1.9+ 官方）

| 服务名（-s 值） | env 变量            | 默认模型              | 说明                         |
|-----------------|---------------------|-----------------------|------------------------------|
| `deepseek`      | `DEEPSEEK_API_KEY`  | `deepseek-chat`       | 便宜、中文好，推荐           |
| `openai`        | `OPENAI_API_KEY`    | `gpt-4o-mini`         | ChatGPT，需科学上网          |
| `zhipu`         | `ZHIPU_API_KEY`     | `glm-4-flash`         | 免费额度大                   |
| `qwen-mt`       | `ALI_API_KEY`       | `qwen-mt-turbo`       | 翻译专用模型，术语最稳       |
| `grok`          | `GROK_API_KEY`      | `grok-2-1212`         |                              |
| `gemini`        | `GEMINI_API_KEY`    | `gemini-1.5-flash`    |                              |
| `silicon`       | `SILICON_API_KEY`   | `Qwen/Qwen2.5-7B-Instruct` | 硅基流动，国产平替      |
| `modelscope`    | `MODELSCOPE_API_KEY`| `Qwen/Qwen2.5-32B-Instruct`| 魔搭                    |
| `groq`          | `GROQ_API_KEY`      | `llama-3-3-70b-versatile` | 极速                     |
| `azure-openai`  | `AZURE_OPENAI_*`    | `gpt-4o-mini`         |                              |
| `tencent`       | `TENCENTCLOUD_SECRET_ID/SECRET_KEY` | — | 腾讯云 |
| `deepl`         | `DEEPL_AUTH_KEY`    | —                     | 机器翻译，无术语控制         |
| `ollama`        | `OLLAMA_HOST`       | `gemma2`              | 本地模型，0 token 成本       |
| `openailiked`   | `OPENAILIKED_BASE_URL/API_KEY/MODEL` | — | 任意 OpenAI 兼容端点 |
| `google` / `bing` / `argos` | 无 | — | 免费机器翻译，术语不可控 |

> Kimi（Moonshot）官方提供 OpenAI 兼容 API：用 `openailiked` +
> `OPENAILIKED_BASE_URL=https://api.moonshot.cn/v1`。Claude 官方 API 不是
> OpenAI 兼容协议，需先搭 OpenAI→Anthropic 兼容网关，再走 `openailiked`。
> `install.py` 的交互向导已覆盖以上全部选项。

> **安全**：API key 只存在于 skill 目录的 `.env`（install.py 写入，权限 600，
> 仓库 .gitignore 已排除）。不要 key 写进 SKILL.md / README / 任何文档或 commit。

## 4. 其他

- 更换服务：改 `.env` 里的 `PDF2ZH_SERVICE` / `PDF2ZH_MODEL` / `xxx_API_KEY`，
  或重跑 `python install.py --skip-venv --skip-copy`（只走配置向导）。
- 升级引擎：`python install.py --skip-copy --skip-config` 会重装最新 pdf2zh。
- 想用 conda 代替 uv？官方包在 conda-forge：`conda create -n pdf2zh -c conda-forge pdf2zh`，
  然后把 run.sh 里的 `PDF2ZH` 指向 `$(which pdf2zh)` 即可。
