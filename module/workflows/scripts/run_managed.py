#!/usr/bin/env python3
"""Run the existing workflow with external local credentials and Managed Agents."""
from __future__ import annotations

import argparse
import json
import os
import sys
import subprocess
import time
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "source"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="使用外部 config 目录运行智谱 Managed 工作流，不复制凭据。")
    parser.add_argument("--config-dir", type=Path, required=True,
                        help="含 zhipu.json 和 deepseek.json 的私有目录；仅读取 api_key")
    parser.add_argument("workflow_args", nargs=argparse.REMAINDER,
                        help="-- 后传递 frontmind 参数，例如 preflight 或 start --help")
    args = parser.parse_args(argv)
    environment = dict(os.environ)
    if environment.get("FRONTMIND_CONTENT_PROVIDER_PROXY"):
        parser.error("当前私有任务网关不支持 Managed Agents；请在直接接入的本地环境运行。")
    for provider in ("zhipu", "deepseek"):
        variable = "FRONTMIND_CONTENT_" + provider.upper() + "_API_KEY"
        if environment.get(variable, "").strip():
            continue
        path = args.config_dir.expanduser().resolve() / (provider + ".json")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            key = value.get("api_key") if isinstance(value, dict) else None
        except (OSError, ValueError):
            parser.error(f"无法读取 {provider}.json 私有配置。")
        if not isinstance(key, str) or not key.strip():
            parser.error(f"{provider}.json 缺少 api_key。")
        environment[variable] = key.strip()
    environment["FRONTMIND_CONTENT_HOST_PROVIDER"] = "zhipu"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    command = args.workflow_args
    if command[:1] == ["--"]:
        command = command[1:]
    command = command or ["start"]
    script = "check_runtime_dependencies.py" if command[0] == "preflight" else "frontmind_workflow.py"
    forwarded = command[1:] if command[0] == "preflight" else command
    # A separate process summarizes API evidence without blocking the executor.
    # Read-only history requests never start this worker or bill a model call.
    cache = environment.get("FRONTMIND_PROCESS_SUMMARY_CACHE")
    if cache and environment.get("FRONTMIND_ENABLE_MODEL_SUMMARIES") == "1" and "--job-dir" in forwarded:
        job = Path(forwarded[forwarded.index("--job-dir")+1]).resolve()
        if not Path(cache).resolve().is_relative_to(job):
            try:
                subprocess.Popen([sys.executable, "-B", str(Path(__file__).with_name("process_summary.py")),
                    "--job-dir", str(job), "--cache-dir", cache,
                    "--since", str(int(time.time()*1000)), "--parent-pid", str(os.getpid())],
                    env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True)
            except OSError:
                pass  # Summary startup failure cannot stop an authorized task.
    child_argv = [sys.executable, "-B", str(SOURCE / "scripts" / script), *forwarded]
    if os.name == "nt":
        return subprocess.call(child_argv, env=environment)
    os.execve(sys.executable, child_argv, environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
