#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf2zh-skill 一键安装向导
==========================

做四件事（可以任选跳过）：

1. 用 uv 创建独立虚拟环境并安装官方 pdf2zh 包（PDFMathTranslate）
   —— 不再依赖 conda，一条命令完成原项目的安装；
2. 把本 skill（SKILL.md + assets + 运行脚本）部署到目标 agent 的 skills 目录：
   - Claude Code  -> ~/.claude/skills/pdf2zh
   - OpenCode     -> ~/.config/opencode/skills/pdf2zh
3. 交互式选择翻译服务（deepseek / chatgpt / glm / qwen / grok / gemini /
   silicon / modelscope / groq / 免费机器翻译 / ollama / openailiked），
   并输入对应的 API key —— 写入 <skill 目录>/.env（已被 .gitignore 排除）；
4. 可选：对新 key 做一次连通性测试。

依赖：Python 3.10+，无任何第三方包；uv 缺了会自动提示安装方式。

用法：
    python install.py                 # 完整安装（默认 Claude Code）
    python install.py --agent opencode
    python install.py --agent dir --target D:/my/skills/pdf2zh
    python install.py --skip-venv --skip-copy   # 只做配置向导
    python install.py --help
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# 常量与数据
# ---------------------------------------------------------------------------

REPO_SKILL = Path(__file__).resolve().parent
APP_NAME = "pdf2zh"
PDF2ZH_PKG = "pdf2zh"  # PyPI 上官方 PDFMathTranslate 的包名

# 官方支持的翻译服务（pdf2zh v1.9.x 实测）。
# "mode": llm -> 需要 API key，支持 --prompt 术语约束；mt -> 免费机器翻译；local -> 本地模型
SERVICES: list[dict] = [
    {
        "key": "deepseek", "label": "DeepSeek（官方）", "mode": "llm",
        "env": "DEEPSEEK_API_KEY", "model_env": "DEEPSEEK_MODEL",
        "default_model": "deepseek-chat",
        "test_url": "https://api.deepseek.com/chat/completions",
        "note": "便宜、中文论文效果好，推荐默认",
    },
    {
        "key": "openai", "label": "OpenAI / ChatGPT", "mode": "llm",
        "env": "OPENAI_API_KEY", "model_env": "OPENAI_MODEL",
        "default_model": "gpt-4o-mini",
        "test_url": "https://api.openai.com/v1/chat/completions",
        "note": "需要能访问 OpenAI 的网络",
    },
    {
        "key": "zhipu", "label": "智谱 GLM", "mode": "llm",
        "env": "ZHIPU_API_KEY", "model_env": "ZHIPU_MODEL",
        "default_model": "glm-4-flash",
        "test_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "note": "glm-4-flash 免费额度大",
    },
    {
        "key": "qwen-mt", "label": "阿里通义 qwen-mt（翻译专用模型）", "mode": "llm",
        "env": "ALI_API_KEY", "model_env": "ALI_MODEL",
        "default_model": "qwen-mt-turbo",
        "test_url": None,
        "note": "专门为翻译训练的模型，术语最稳；海外用户可设 ALI_DOMAINS=dashscope-intl.aliyuncs.com",
    },
    {
        "key": "grok", "label": "xAI Grok", "mode": "llm",
        "env": "GROK_API_KEY", "model_env": "GROK_MODEL",
        "default_model": "grok-2-1212",
        "test_url": "https://api.x.ai/v1/chat/completions",
        "note": "",
    },
    {
        "key": "gemini", "label": "Google Gemini", "mode": "llm",
        "env": "GEMINI_API_KEY", "model_env": "GEMINI_MODEL",
        "default_model": "gemini-1.5-flash",
        "test_url": None,
        "note": "",
    },
    {
        "key": "silicon", "label": "硅基流动 SiliconFlow", "mode": "llm",
        "env": "SILICON_API_KEY", "model_env": "SILICON_MODEL",
        "default_model": "Qwen/Qwen2.5-7B-Instruct",
        "test_url": "https://api.siliconflow.cn/v1/chat/completions",
        "note": "国产平替，便宜",
    },
    {
        "key": "modelscope", "label": "魔搭 ModelScope", "mode": "llm",
        "env": "MODELSCOPE_API_KEY", "model_env": "MODELSCOPE_MODEL",
        "default_model": "Qwen/Qwen2.5-32B-Instruct",
        "test_url": "https://api-inference.modelscope.cn/v1/chat/completions",
        "note": "",
    },
    {
        "key": "groq", "label": "Groq（极速推理）", "mode": "llm",
        "env": "GROQ_API_KEY", "model_env": "GROQ_MODEL",
        "default_model": "llama-3-3-70b-versatile",
        "test_url": "https://api.groq.com/openai/v1/chat/completions",
        "note": "响应速度最快",
    },
    {
        "key": "google", "label": "Google 翻译（免费，无需 key）", "mode": "mt",
        "note": "无法自定义术语，LLM 词条可能翻错，配合路线 B 修补",
    },
    {
        "key": "bing", "label": "必应翻译（免费，无需 key）", "mode": "mt",
        "note": "同上",
    },
    {
        "key": "argos", "label": "Argos 离线翻译（免费，质量一般）", "mode": "mt",
        "note": "",
    },
    {
        "key": "deepl", "label": "DeepL", "mode": "mt",
        "env": "DEEPL_AUTH_KEY",
        "note": "高质量机器翻译，但同样无法自定义术语",
    },
    {
        "key": "ollama", "label": "Ollama（本地模型，免费）", "mode": "local",
        "env": "OLLAMA_HOST", "model_env": "OLLAMA_MODEL",
        "default_model": "gemma2", "default_host": "http://localhost:11434",
        "note": "0 token 成本，吃显存；需先自行安装 Ollama",
    },
    {
        "key": "openailiked", "label": "任意 OpenAI 兼容端点（Kimi / Claude 网关等）", "mode": "llm",
        "env": "OPENAILIKED_API_KEY", "model_env": "OPENAILIKED_MODEL",
        "base_url_env": "OPENAILIKED_BASE_URL",
        "test_url": None,  # 由用户填 base_url 后拼 /chat/completions
        "note": "Kimi(moonshot) 官方就是 OpenAI 兼容 API，直接填 https://api.moonshot.cn/v1；"
                "Claude 需先配一个 OpenAI->Anthropic 兼容网关，再填网关地址",
    },
]

AGENTS = {
    "claude": "Claude Code（~/.claude/skills/pdf2zh）",
    "opencode": "OpenCode（~/.config/opencode/skills/pdf2zh）",
}


def service_env_map(svc: dict, key: str, base_url: str | None, model: str) -> list[tuple[str, str]]:
    """根据用户输入生成 .env 里的键值对。"""
    lines = []
    mode = svc["mode"]
    if mode == "mt" and svc.get("env"):
        lines.append((svc["env"], key))
        return lines
    if mode == "local":
        lines.append((svc["env"], base_url or svc.get("default_host", "")))
        if model:
            lines.append((svc["model_env"], model))
        return lines
    if mode == "llm":
        if svc.get("env"):
            lines.append((svc["env"], key))
        if svc.get("base_url_env") and base_url:
            lines.append((svc["base_url_env"], base_url))
        if model and svc.get("model_env"):
            lines.append((svc["model_env"], model))
        return lines
    return []


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def pprint(*a: str) -> None:
    print(*a, flush=True)


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    pprint("  $ " + " ".join(cmd))
    return subprocess.run(cmd, **kw)


def find_uv() -> Path | None:
    exe = shutil.which("uv")
    if exe:
        return Path(exe)
    for cand in (Path.home() / ".local" / "bin" / "uv", Path.home() / ".cargo" / "bin" / "uv"):
        if cand.exists():
            return cand
    return None


def ensure_uv() -> Path:
    uv = find_uv()
    if uv:
        return uv
    pprint("未检测到 uv —— 官方一行安装（约 1 分钟）：")
    if sys.platform == "win32":
        pprint("  powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\"")
    else:
        pprint("  curl -LsSf https://astral.sh/uv/install.sh | sh")
    pprint("装完重新运行本脚本即可。")
    sys.exit(2)


def is_windows() -> bool:
    return sys.platform == "win32"


def venv_paths(skill_dir: Path) -> tuple[Path, Path]:
    """返回 (python, pdf2zh 可执行文件) 在 venv 中的路径。"""
    if is_windows():
        return (
            skill_dir / ".venv" / "Scripts" / "python.exe",
            skill_dir / ".venv" / "Scripts" / "pdf2zh.exe",
        )
    return skill_dir / ".venv" / "bin" / "python", skill_dir / ".venv" / "bin" / "pdf2zh"


# ---------------------------------------------------------------------------
# 各安装步骤
# ---------------------------------------------------------------------------

def install_venv(skill_dir: Path, uv: Path) -> None:
    """用 uv 建 .venv 并安装官方 pdf2zh（等价于原项目 conda 环境）。"""
    pprint("\n[1/4] 创建虚拟环境并安装 pdf2zh（官方 PDFMathTranslate）...")
    python, _ = venv_paths(skill_dir)
    if python.exists():
        pprint(f"  已存在 {python}，跳过创建。")
    else:
        r = run([str(uv), "venv", str(skill_dir / ".venv")])
        if r.returncode != 0:
            sys.exit(f"uv venv 失败：{r.returncode}")
    # --only-binary: 全部用预编译 wheel，避免 Windows 上缺 MSVC/Rust 时
    # 从源码编译 pydantic-core 等失败；网络慢可设 UV_DEFAULT_INDEX 换国内镜像
    r = run(
        [str(uv), "pip", "install", "--python", str(python),
         "--only-binary", ":all:", "-U", PDF2ZH_PKG],
        env={**os.environ, "UV_HTTP_TIMEOUT": "300"},
    )
    if r.returncode != 0:
        sys.exit(f"pip 安装 {PDF2ZH_PKG} 失败：{r.returncode}")


def copy_skill_files(skill_dir: Path) -> None:
    """把 SKILL.md / assets / 运行脚本 部署到目标 skills 目录。"""
    pprint(f"\n[2/4] 部署 skill 文件到 {skill_dir} ...")
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "assets").mkdir(parents=True, exist_ok=True)

    for name in ("SKILL.md",):
        src = REPO_SKILL / name
        if src.exists():
            shutil.copy2(src, skill_dir / name)
    for name in ("prompt.txt", "glossary.txt", "apply_glossary.py"):
        src = REPO_SKILL / "assets" / name
        if src.exists():
            shutil.copy2(src, skill_dir / "assets" / name)

    write_run_sh(skill_dir)
    write_run_cmd(skill_dir)
    pprint("  已写入 run.sh / run.cmd 一键翻译入口。")


RUN_SH_TEMPLATE = r'''#!/usr/bin/env bash
# 一键翻译入口：自动加载 .env（服务/模型/API key/术语 prompt），再调 pdf2zh。
# 用法:  ./run.sh paper.pdf -o out/
#        ./run.sh --dir papers/        # 批量
#        ./run.sh -i                   # GUI
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

set -a
# shellcheck disable=SC1091
source "$SKILL_DIR/.env"
set +a

if [ -x "$SKILL_DIR/.venv/Scripts/pdf2zh.exe" ]; then
  PDF2ZH="$SKILL_DIR/.venv/Scripts/pdf2zh.exe"
elif [ -x "$SKILL_DIR/.venv/bin/pdf2zh" ]; then
  PDF2ZH="$SKILL_DIR/.venv/bin/pdf2zh"
else
  PDF2ZH="$(command -v pdf2zh || true)"
  if [ -z "$PDF2ZH" ]; then
    echo "错误: 找不到 pdf2zh，请先运行 python install.py" >&2
    exit 1
  fi
fi

ARGS=()
if [ -n "${PDF2ZH_SERVICE:-}" ]; then
  if [ -n "${PDF2ZH_MODEL:-}" ]; then
    ARGS+=(-s "$PDF2ZH_SERVICE:$PDF2ZH_MODEL")
  else
    ARGS+=(-s "$PDF2ZH_SERVICE")
  fi
fi
if [ -n "${PDF2ZH_PROMPT:-}" ] && [ -f "${PDF2ZH_PROMPT:-}" ]; then
  ARGS+=(--prompt "$PDF2ZH_PROMPT")
fi

exec "$PDF2ZH" "${ARGS[@]}" "$@"
'''

RUN_CMD_TEMPLATE = r'''@echo off
rem 一键翻译入口（Windows cmd / PowerShell 用）。用法:  run.cmd paper.pdf -o out\
setlocal
for /f "usebackq delims=" %%a in ('findstr /v /b "#" "%~dp0.env"') do set "%%a"

set "PDF2ZH=%~dp0.venv\Scripts\pdf2zh.exe"
if not exist "%PDF2ZH%" set "PDF2ZH=pdf2zh"

set "ARGS="
if defined PDF2ZH_SERVICE (
  if defined PDF2ZH_MODEL (
    set "ARGS=%ARGS% -s %PDF2ZH_SERVICE%:%PDF2ZH_MODEL%"
  ) else (
    set "ARGS=%ARGS% -s %PDF2ZH_SERVICE%"
  )
)
if defined PDF2ZH_PROMPT if exist "%PDF2ZH_PROMPT%" set "ARGS=%ARGS% --prompt "%PDF2ZH_PROMPT%""

"%PDF2ZH%" %ARGS% %*
endlocal
'''


def write_run_sh(skill_dir: Path) -> None:
    f = skill_dir / "run.sh"
    f.write_text(RUN_SH_TEMPLATE, encoding="utf-8", newline="\n")
    f.chmod(f.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def write_run_cmd(skill_dir: Path) -> None:
    (skill_dir / "run.cmd").write_text(RUN_CMD_TEMPLATE, encoding="utf-8", newline="\r\n")


# ---------------------------------------------------------------------------
# 交互式配置向导
# ---------------------------------------------------------------------------

def ask(prompt: str, default: str = "", secret: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        import getpass
        if secret and sys.stdin.isatty():
            val = getpass.getpass(prompt + suffix + "（输入时不回显）: ")
        else:
            val = input(prompt + suffix + ": ")
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(1)
    val = val.strip()
    return val or default


def pick_service() -> dict:
    pprint("\n[3/4] 选择翻译服务：")
    pprint("  " + "-" * 62)
    for i, svc in enumerate(SERVICES, 1):
        star = " *" if svc.get("note") else ""
        pprint(f"  [{i:>2}] {svc['label']:<32} {star}")
    pprint("  " + "-" * 62)
    pprint("  * = 有额外说明（输入序号时留意）")
    while True:
        raw = input("  请选择服务编号（默认 1 deepseek）: ").strip()
        if not raw:
            return SERVICES[0]
        if raw.isdigit() and 1 <= int(raw) <= len(SERVICES):
            return SERVICES[int(raw) - 1]
        pprint("  输入无效，请重新选择。")


def test_key(svc: dict, key: str, base_url: str | None) -> bool:
    url = svc.get("test_url")
    if not url and svc.get("base_url_env"):
        url = f"{base_url.rstrip('/')}/chat/completions"
    if not url:
        return False  # 协议不兼容 /chat/completions，跳过测试
    model = svc.get("default_model", "")
    body = json.dumps({
        "model": model, "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            ok = 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        pprint(f"  ✗ 测试失败：HTTP {e.code} {e.reason}")
        if e.code in (401, 403):
            pprint("    大概率是 API key 无效或没有该模型权限，请检查 key / 模型名。")
        return False
    except Exception as e:  # noqa: BLE001
        pprint(f"  ✗ 测试失败（网络或端点问题）：{e}")
        return False
    if ok:
        pprint(f"  ✓ 连通性测试通过（模型 {model}）")
    return ok


def configure(skill_dir: Path) -> None:
    svc = pick_service()
    mode = svc["mode"]
    pprint(f"\n  已选择：{svc['label']}")

    key = ""
    base_url = ""
    model = svc.get("default_model", "")

    if mode == "llm" and svc.get("env"):
        key = ask(f"  粘贴 {svc['env']} 对应的 API key", secret=True)
        if not key:
            pprint("  ⚠ 未输入 key，将跳过测试并写空值（之后可编辑 .env 补上）")
    if svc.get("base_url_env"):
        base_url = ask("  OpenAI 兼容端点 base_url", default="https://api.moonshot.cn/v1")
    if mode == "local":
        base_url = ask("  Ollama 服务地址", default=svc.get("default_host", "http://localhost:11434"))
    if svc.get("model_env") and mode in ("llm", "local"):
        model = ask(f"  模型名（写入 {svc['model_env']}）", default=model)

    pairs = service_env_map(svc, key, base_url or None, model)

    # 写入 .env
    lines = [
        "# 由 install.py 生成 —— 内含 API key，切勿提交到任何 git 仓库",
        f"PDF2ZH_SKILL_DIR={skill_dir.as_posix()}",
        f"PDF2ZH_SERVICE={svc['key']}",
    ]
    if mode in ("llm", "local") and model:
        lines.append(f"PDF2ZH_MODEL={model}")
    for k, v in pairs:
        lines.append(f"{k}={v}")
    if mode == "llm":
        lines.append(f"PDF2ZH_PROMPT={(skill_dir / 'assets' / 'prompt.txt').as_posix()}")
    env_file = skill_dir / ".env"
    skill_dir.mkdir(parents=True, exist_ok=True)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    if not is_windows():
        env_file.chmod(0o600)
    pprint(f"  ✓ 已写入 {env_file}（权限 600，gitignore 已排除）")

    # 连通性测试
    if mode == "llm" and key:
        if ask("  现在测一下 key 连通性？", default="y").lower() in ("y", "yes", ""):
            test_key(svc, key, base_url or None)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def resolve_skill_dir(args) -> Path:
    if args.agent == "dir":
        if not args.target:
            sys.exit("--agent dir 需要 --target 指定目标目录")
        return Path(args.target).expanduser().resolve()
    home = Path.home()
    if args.agent == "opencode":
        base = home / ".config" / "opencode" / "skills"
    else:
        base = home / ".claude" / "skills"
    return base / APP_NAME


def main() -> int:
    # Windows 控制台默认 cp936，强制 UTF-8 输出避免中文乱码
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    ap = argparse.ArgumentParser(
        description="pdf2zh-skill 一键安装：uv 环境 + skill 部署 + 翻译服务/API key 配置",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument(
        "--agent", choices=["claude", "opencode", "dir"], default="claude",
        help="目标 agent：Claude Code / OpenCode / 自定义目录",
    )
    ap.add_argument("--target", default=None, help="--agent dir 时的目标目录")
    ap.add_argument("--skip-venv", action="store_true", help="跳过 pdf2zh 安装（已装过时用）")
    ap.add_argument("--skip-copy", action="store_true", help="跳过 skill 文件部署（已部署时用）")
    ap.add_argument("--skip-config", action="store_true", help="跳过服务/key 配置向导")
    args = ap.parse_args()

    pprint("╭──────────────────────────────────────────────╮")
    pprint("│  pdf2zh-skill 安装向导                         │")
    pprint("╰──────────────────────────────────────────────╯")

    skill_dir = resolve_skill_dir(args)
    pprint(f"  目标 skill 目录: {skill_dir}")

    if not args.skip_venv:
        uv = ensure_uv()
        install_venv(skill_dir, uv)
    if not args.skip_copy:
        copy_skill_files(skill_dir)
    if not args.skip_config:
        configure(skill_dir)

    python, pdf2zh = venv_paths(skill_dir)
    pprint("\n[4/4] 安装完成 🎉")
    pprint("  ── 现在你可以：")
    pprint(f"    Claude Code 里直接说「翻译这篇 PDF」；或手动执行：")
    if is_windows():
        pprint(f'    bash  :  "{skill_dir}/run.sh" paper.pdf -o out/')
        pprint(f'    cmd   :  "{skill_dir}\\run.cmd" paper.pdf -o out\\')
    else:
        pprint(f'    ./run.sh paper.pdf -o out/   （在 {skill_dir} 下）')
    pprint("    批量  :  run.sh --dir papers/")
    pprint("    GUI   :  run.sh -i")
    pprint("    测试  :  run.sh --version")
    return 0


if __name__ == "__main__":
    sys.exit(main())
