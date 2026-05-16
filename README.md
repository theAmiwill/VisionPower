# VisionPower

VisionPower packages a local image-understanding MCP server with a matching Codex skill.

The MCP server calls a configured vision model and returns semantic HTML. The skill tells Codex when to call the MCP, how to phrase image-understanding requests, and how to reason over the returned HTML. The active main reasoning model remains controlled by your MCP client, not by this project.

## What It Does

```text
image path / URL / base64
        ↓
understand_image (VisionPower MCP)
        ↓
configured vision model API
        ↓
semantic HTML with bbox, confidence, OCR, layout, uncertainties
        ↓
current main model in Codex / Claude Code / VS Code / Kilo Code
```

VisionPower supports two upstream API protocols:

- `openai`: `{VISION_POWER_API_BASE_URL}/chat/completions`
- `anthropic`: `{VISION_POWER_API_BASE_URL}/messages`

These base URLs are not interchangeable. Pick the protocol that matches the provider endpoint.

## Download the Whole Repository

Do not download only `mcp/` or only `skills/vision-power/`. VisionPower needs the complete repository because the installer, examples, MCP server, skill, and tests reference each other by repo-relative paths.

Use one of these full-repo methods:

```powershell
git clone git@github.com:theAmiwill/VisionPower.git
```

or download the repository ZIP from GitHub and extract the whole `VisionPower/` folder. After moving machines, rerun `mcp/setup.bat` or `mcp/setup.sh`, then rerun `install.py` so client configs point at the new absolute paths.

## Repository Layout

```text
VisionPower/
├── install.py                    # Cross-client MCP installer
├── install-skill.ps1             # Copies the Codex skill into ~/.codex/skills
├── install-skill.sh
├── mcp/
│   ├── server.py                 # VisionPower MCP server
│   ├── requirements.txt
│   ├── setup.bat
│   ├── setup.sh
│   └── .env.example
├── skills/
│   └── vision-power/             # Codex skill
├── examples/
│   ├── codex.config.toml
│   ├── claude-code.mcp.json
│   ├── vscode.mcp.json
│   ├── kilo.jsonc
│   └── openclaw.openclaw.json
└── tests/
```

## Quick Start

1. Clone the repository:

```powershell
git clone git@github.com:theAmiwill/VisionPower.git
cd VisionPower
```

2. Install MCP server dependencies:

```powershell
cd mcp
.\setup.bat
cd ..
```

3. Install client configuration:

```powershell
python install.py
```

Use `--client` for a specific target:

```powershell
python install.py --client codex
python install.py --client claude-code
python install.py --client vscode
python install.py --client kilo
python install.py --client openclaw
python install.py --client all
```

4. Install the Codex skill if you use Codex:

```powershell
.\install-skill.ps1
```

5. Restart the MCP client.

## Configuration

VisionPower reads these environment variables at MCP server startup:

| Variable | Required | Description |
|----------|----------|-------------|
| `VISION_POWER_API_KEY` | Yes | Vision model API key |
| `VISION_POWER_MODEL` | Yes | Vision model name |
| `VISION_POWER_API_BASE_URL` | Yes | Provider base URL |
| `VISION_POWER_API_PROTOCOL` | Yes | `openai` or `anthropic` |
| `VISION_POWER_TIMEOUT` | No | Request timeout in seconds, default `120` |

OpenAI-compatible MiMo example:

```text
VISION_POWER_API_KEY=your-api-key
VISION_POWER_MODEL=mimo-v2.5
VISION_POWER_API_BASE_URL=https://token-plan-cn.xiaomimimo.com/v1
VISION_POWER_API_PROTOCOL=openai
VISION_POWER_TIMEOUT=120
```

Use a model that actually accepts image input for `VISION_POWER_MODEL`. Text/coding models can still be excellent **main reasoning models** in Claude Code or other clients, but they are not valid VisionPower upstream models if their API ignores `image_url` or image content blocks. For example, MiniMax-M2.7 is documented for coding/text workflows and can be used as a main model in compatible clients, but its OpenAI-compatible and Anthropic-compatible text APIs do not currently support image inputs.

For Claude Code with MiniMax as the **main model**, configure Claude Code with MiniMax's Anthropic-compatible endpoint, such as `https://api.minimaxi.com/anthropic` for Mainland China or `https://api.minimax.io/anthropic` for Global. Keep VisionPower configured separately with a vision-capable model.

VisionPower validates that the upstream response is semantic HTML and that it does not look like a "no image received" response. If a text-only model returns plain text or says it cannot see the image, VisionPower reports a configuration error instead of passing weak evidence to the main model.

## Passing Images From Text-Only Main Models

When the current main model cannot accept image attachments, do not upload the image directly to the MCP client chat. Some clients try to include uploaded attachments in the main model request before the model can call MCP tools. That can fail before VisionPower is invoked, with errors such as:

```text
There's an issue with the selected model (...). It may not exist or you may not have access to it. Run /model to pick a different model.
```

Save the image as a local file and send its path as text instead:

```text
Please use vision-power understand_image to analyze:
C:\Users\WILL\OneDrive\Desktop\screenshot.png
```

The main model receives only text, then VisionPower reads the file path and sends the image to the configured vision model. This keeps text-only main models separate from image-capable upstream vision models.

## Client Formats

- Codex: `~/.codex/config.toml`, see `examples/codex.config.toml`.
- Claude Code: `claude mcp add-json --scope user` when the CLI is available; otherwise use `examples/claude-code.mcp.json`.
- GitHub Copilot / VS Code: `.vscode/mcp.json` with root key `servers`, see `examples/vscode.mcp.json`.
- Kilo Code: `~/.config/kilo/kilo.jsonc` or project `.kilo/kilo.jsonc` with root key `mcp`, see `examples/kilo.jsonc`.
- OpenClaw: copies the skill to `~/.openclaw/skills/vision-power` and registers `mcp.servers.vision-power`, see `examples/openclaw.openclaw.json`.

Run dry-runs before writing:

```powershell
python install.py --client codex --dry-run
python install.py --client vscode --dry-run
python install.py --client kilo --dry-run
python install.py --client openclaw --dry-run
```

The installer creates a timestamped backup before overwriting an existing config file.

For OpenClaw, the installer prefers `openclaw mcp set vision-power <json>` when the CLI exists. If the CLI is missing, it tries to merge `~/.openclaw/openclaw.json`; if the existing file uses JSON5 syntax the fallback cannot safely parse, it prints the exact config fragment for manual insertion.

## Migration From Old MiMo-Bound Names

| Old name | New name |
|----------|----------|
| `mimo-vision` | `vision-power` |
| `mimo_understand_image` | `understand_image` |
| `mimo_get_model_info` | `get_vision_config` |
| `MIMO_VISION_API_KEY` | `VISION_POWER_API_KEY` |
| `MIMO_VISION_MODEL` | `VISION_POWER_MODEL` |
| `MIMO_VISION_API_BASE_URL` | `VISION_POWER_API_BASE_URL` |
| `MIMO_VISION_TIMEOUT` | `VISION_POWER_TIMEOUT` |
| none | `VISION_POWER_API_PROTOCOL` |

Runtime compatibility with `MIMO_*` variables was intentionally removed to keep the server code small and explicit.

## Important Boundary

Do not configure the main reasoning model in this project. Codex, Claude Code, VS Code, or Kilo Code decides the active main model. VisionPower only provides an image-understanding tool and returns semantic HTML for whichever main model is currently in use.

## Validation

```powershell
.\mcp\.venv\Scripts\python.exe -m py_compile mcp\server.py install.py tests\test_payloads.py tests\test_installer.py tests\test_mcp_stdio.py
.\mcp\.venv\Scripts\python.exe -m unittest discover -s tests
.\mcp\.venv\Scripts\python.exe install.py --client codex --dry-run
.\mcp\.venv\Scripts\python.exe install.py --client claude-code --dry-run
.\mcp\.venv\Scripts\python.exe install.py --client vscode --dry-run
.\mcp\.venv\Scripts\python.exe install.py --client kilo --dry-run
.\mcp\.venv\Scripts\python.exe install.py --client openclaw --dry-run
```
