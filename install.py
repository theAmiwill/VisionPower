#!/usr/bin/env python3
"""Install VisionPower MCP configuration for supported local clients."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

SERVER_NAME = "vision-power"
LEGACY_SERVER_NAMES = ("mimo-vision",)

DEFAULT_API_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
DEFAULT_MODEL = "mimo-v2.5"
DEFAULT_PROTOCOL = "openai"
DEFAULT_TIMEOUT = "120"

ROOT = Path(__file__).resolve().parent
MCP_SERVER = ROOT / "mcp" / "server.py"


@dataclass
class InstallConfig:
    api_key: str
    model: str
    base_url: str
    protocol: str
    timeout: str
    python_path: str
    server_path: str
    project_dir: Path
    kilo_scope: str


def _path_text(path: Path | str) -> str:
    return str(path).replace("\\", "/")


def _venv_python() -> Path:
    candidates = [
        ROOT / "mcp" / ".venv" / "Scripts" / "python.exe",
        ROOT / "mcp" / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def _prompt(label: str, default: str, secret: bool = False) -> str:
    suffix = f" [{default}]" if default and not secret else ""
    if secret:
        value = getpass.getpass(f"{label}{suffix}: ")
    else:
        value = input(f"{label}{suffix}: ")
    return value.strip() or default


def _confirm(question: str, yes: bool) -> bool:
    if yes:
        return True
    answer = input(f"{question} [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _collect_config(args: argparse.Namespace) -> InstallConfig:
    interactive = not args.dry_run and not args.yes
    protocol = args.protocol or (DEFAULT_PROTOCOL if not interactive else _prompt("API protocol (openai/anthropic)", DEFAULT_PROTOCOL))
    protocol = protocol.strip().lower()
    if protocol not in {"openai", "anthropic"}:
        raise SystemExit("API protocol must be 'openai' or 'anthropic'.")

    api_key = args.api_key
    if api_key is None:
        api_key = "" if args.dry_run else ("" if args.yes else _prompt("Vision API key", "", secret=True))

    return InstallConfig(
        api_key=api_key or "YOUR_VISION_API_KEY",
        model=args.model or (DEFAULT_MODEL if not interactive else _prompt("Vision model", DEFAULT_MODEL)),
        base_url=args.base_url or (DEFAULT_API_BASE_URL if not interactive else _prompt("Vision API base URL", DEFAULT_API_BASE_URL)),
        protocol=protocol,
        timeout=args.timeout or (DEFAULT_TIMEOUT if not interactive else _prompt("Timeout seconds", DEFAULT_TIMEOUT)),
        python_path=_path_text(Path(args.python) if args.python else _venv_python()),
        server_path=_path_text(Path(args.server) if args.server else MCP_SERVER),
        project_dir=Path(args.project_dir).expanduser().resolve(),
        kilo_scope=args.kilo_scope,
    )


def _env(config: InstallConfig, api_key: str | None = None) -> dict[str, str]:
    return {
        "VISION_POWER_API_KEY": api_key if api_key is not None else config.api_key,
        "VISION_POWER_MODEL": config.model,
        "VISION_POWER_API_BASE_URL": config.base_url.rstrip("/"),
        "VISION_POWER_API_PROTOCOL": config.protocol,
        "VISION_POWER_TIMEOUT": config.timeout,
    }


def _server_config(config: InstallConfig, env: dict[str, str] | None = None) -> dict[str, Any]:
    return {
        "type": "stdio",
        "command": config.python_path,
        "args": [config.server_path],
        "env": env or _env(config),
    }


def build_codex_toml(config: InstallConfig) -> str:
    env_items = ", ".join(f"{key} = {json.dumps(value, ensure_ascii=False)}" for key, value in _env(config).items())
    return (
        f"[mcp_servers.{SERVER_NAME}]\n"
        f"command = {json.dumps(config.python_path, ensure_ascii=False)}\n"
        f"args = [{json.dumps(config.server_path, ensure_ascii=False)}]\n"
        f"env = {{ {env_items} }}\n"
    )


def build_claude_json(config: InstallConfig) -> dict[str, Any]:
    return _server_config(config)


def build_vscode_json(config: InstallConfig) -> dict[str, Any]:
    return {
        "inputs": [
            {
                "type": "promptString",
                "id": "visionPowerApiKey",
                "description": "VisionPower API key",
                "password": True,
            }
        ],
        "servers": {
            SERVER_NAME: _server_config(config, env=_env(config, "${input:visionPowerApiKey}")),
        },
    }


def build_kilo_json(config: InstallConfig) -> dict[str, Any]:
    timeout_ms = int(float(config.timeout) * 1000)
    return {
        "mcp": {
            SERVER_NAME: {
                "type": "local",
                "command": [config.python_path, config.server_path],
                "environment": _env(config),
                "enabled": True,
                "timeout": timeout_ms,
            }
        }
    }


def _strip_jsonc_comments(text: str) -> str:
    output: list[str] = []
    i = 0
    in_string = False
    escaped = False
    while i < len(text):
        char = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            i += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            i += 1
            continue
        if char == "/" and nxt == "/":
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        if char == "/" and nxt == "*":
            i += 2
            while i + 1 < len(text) and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        output.append(char)
        i += 1
    return "".join(output)


def _load_jsonc(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.read_text(encoding="utf-8").strip():
        return {}
    return json.loads(_strip_jsonc_comments(path.read_text(encoding="utf-8")))


def _backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.bak-{timestamp}")
    shutil.copy2(path, backup)
    return backup


def _write_json(path: Path, data: dict[str, Any], yes: bool, dry_run: bool) -> None:
    rendered = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if dry_run:
        print(rendered)
        return
    if not _confirm(f"Write {path}?", yes):
        print("Skipped.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = _backup(path)
    path.write_text(rendered, encoding="utf-8")
    if backup:
        print(f"Backup: {backup}")
    print(f"Wrote: {path}")


def _remove_toml_server_block(text: str, name: str) -> tuple[str, bool]:
    table = re.escape(name)
    pattern = re.compile(
        rf'(?ms)^\[mcp_servers\.(?:"{table}"|{table})\]\s*.*?(?=^\[|\Z)'
    )
    return pattern.subn("", text)


def install_codex(config: InstallConfig, yes: bool, dry_run: bool) -> None:
    path = Path.home() / ".codex" / "config.toml"
    snippet = build_codex_toml(config)
    text = "" if dry_run else (path.read_text(encoding="utf-8") if path.exists() else "")
    for name in (SERVER_NAME, *LEGACY_SERVER_NAMES):
        text, removed = _remove_toml_server_block(text, name)
        if removed and name in LEGACY_SERVER_NAMES:
            print(f"Detected legacy Codex server '{name}'; migrating to '{SERVER_NAME}'.")
    next_text = text.rstrip() + ("\n\n" if text.strip() else "") + snippet
    print(f"--- Codex target: {path} ---")
    if dry_run:
        print(next_text)
        return
    if not _confirm(f"Write {path}?", yes):
        print("Skipped.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = _backup(path)
    path.write_text(next_text, encoding="utf-8")
    if backup:
        print(f"Backup: {backup}")
    print(f"Wrote: {path}")


def install_claude_code(config: InstallConfig, yes: bool, dry_run: bool) -> None:
    payload = json.dumps(build_claude_json(config), ensure_ascii=False)
    print("--- Claude Code target: user scope ---")
    print(json.dumps({"mcpServers": {SERVER_NAME: build_claude_json(config)}}, ensure_ascii=False, indent=2))
    claude = shutil.which("claude")
    if dry_run:
        if claude:
            print(f"Would run: claude mcp add-json --scope user {SERVER_NAME} '<json>'")
        else:
            print("Claude CLI not found. Use the JSON fragment above in .mcp.json or install Claude Code CLI.")
        return
    if not claude:
        print("Claude CLI not found. Use the JSON fragment above in .mcp.json.")
        return
    if not _confirm("Run claude mcp add-json --scope user?", yes):
        print("Skipped.")
        return
    claude_user_config = Path.home() / ".claude.json"
    backup = _backup(claude_user_config)
    subprocess.run(
        [claude, "mcp", "add-json", "--scope", "user", SERVER_NAME, payload],
        check=True,
    )
    if backup:
        print(f"Backup: {backup}")
    print("Claude Code MCP server added.")


def _merge_named_server(root: dict[str, Any], section: str, server: dict[str, Any], yes: bool) -> dict[str, Any]:
    root.setdefault(section, {})
    for legacy in LEGACY_SERVER_NAMES:
        if legacy in root[section]:
            if yes or _confirm(f"Replace legacy server '{legacy}' with '{SERVER_NAME}'?", False):
                del root[section][legacy]
    root[section][SERVER_NAME] = server
    return root


def install_vscode(config: InstallConfig, yes: bool, dry_run: bool) -> None:
    path = config.project_dir / ".vscode" / "mcp.json"
    current = {} if dry_run else _load_jsonc(path)
    server = build_vscode_json(config)["servers"][SERVER_NAME]
    merged = _merge_named_server(current, "servers", server, yes or dry_run)
    merged.setdefault("inputs", [])
    if not any(item.get("id") == "visionPowerApiKey" for item in merged["inputs"] if isinstance(item, dict)):
        merged["inputs"].append(build_vscode_json(config)["inputs"][0])
    print(f"--- VS Code / GitHub Copilot target: {path} ---")
    _write_json(path, merged, yes, dry_run)


def install_kilo(config: InstallConfig, yes: bool, dry_run: bool) -> None:
    if config.kilo_scope == "project":
        path = config.project_dir / ".kilo" / "kilo.jsonc"
    else:
        path = Path.home() / ".config" / "kilo" / "kilo.jsonc"
    current = {} if dry_run else _load_jsonc(path)
    server = build_kilo_json(config)["mcp"][SERVER_NAME]
    merged = _merge_named_server(current, "mcp", server, yes or dry_run)
    print(f"--- Kilo Code target: {path} ---")
    _write_json(path, merged, yes, dry_run)


def detect_clients(project_dir: Path) -> dict[str, bool]:
    return {
        "codex": (Path.home() / ".codex").exists(),
        "claude-code": bool(shutil.which("claude") or (Path.home() / ".claude.json").exists()),
        "vscode": bool(shutil.which("code") or (project_dir / ".vscode").exists()),
        "kilo": bool((Path.home() / ".config" / "kilo").exists() or (project_dir / ".kilo").exists()),
    }


def _resolve_clients(args: argparse.Namespace, project_dir: Path) -> list[str]:
    if args.client:
        return ["codex", "claude-code", "vscode", "kilo"] if args.client == "all" else [args.client]
    detected = detect_clients(project_dir)
    print("Detected clients:")
    for client, present in detected.items():
        print(f"  {client}: {'yes' if present else 'no'}")
    answer = _prompt("Clients to configure (comma-separated, or all)", "codex")
    if answer == "all":
        return ["codex", "claude-code", "vscode", "kilo"]
    clients = [item.strip() for item in answer.split(",") if item.strip()]
    invalid = sorted(set(clients) - {"codex", "claude-code", "vscode", "kilo"})
    if invalid:
        raise SystemExit(f"Unknown client(s): {', '.join(invalid)}")
    return clients


def main() -> int:
    parser = argparse.ArgumentParser(description="Install VisionPower MCP config for supported clients.")
    parser.add_argument("--client", choices=["codex", "claude-code", "vscode", "kilo", "all"])
    parser.add_argument("--dry-run", action="store_true", help="Print the config that would be written.")
    parser.add_argument("-y", "--yes", action="store_true", help="Do not prompt before writing.")
    parser.add_argument("--api-key", help="Vision API key. Omit in dry-run examples.")
    parser.add_argument("--model", help="Vision model name.")
    parser.add_argument("--base-url", help="Vision API base URL.")
    parser.add_argument("--protocol", choices=["openai", "anthropic"], help="Upstream API protocol.")
    parser.add_argument("--timeout", help="Request timeout in seconds.")
    parser.add_argument("--python", help="Python executable for the MCP server.")
    parser.add_argument("--server", help="Path to mcp/server.py.")
    parser.add_argument("--project-dir", default=os.getcwd(), help="Project directory for VS Code/Kilo project configs.")
    parser.add_argument("--kilo-scope", choices=["global", "project"], default="global")
    args = parser.parse_args()

    config = _collect_config(args)
    clients = _resolve_clients(args, config.project_dir)
    installers = {
        "codex": install_codex,
        "claude-code": install_claude_code,
        "vscode": install_vscode,
        "kilo": install_kilo,
    }
    for client in clients:
        installers[client](config, args.yes, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
