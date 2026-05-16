# VisionPower MCP Server

This MCP server calls a configured vision-language model and returns semantic HTML for a downstream text-only/main model.

It configures only the **vision model**. The current session's **main reasoning model** is selected by the MCP client and receives the returned HTML as normal tool output.

## Install From the Full Repository

Do not copy only this `mcp/` folder. Use the complete `VisionPower/` repository so `install.py`, `skills/vision-power/`, examples, and tests stay together. After copying to another machine, rerun setup and the root installer so client configs point at the new absolute paths.

## Tools

| Tool | Purpose | Read-only |
|------|---------|-----------|
| `understand_image` | Analyze an image and return semantic HTML | Yes |
| `get_vision_config` | Show startup vision-model configuration | Yes |

## Protocols

Set `VISION_POWER_API_PROTOCOL` to match the provider endpoint:

| Protocol | Endpoint | Auth | Image block |
|----------|----------|------|-------------|
| `openai` | `{base_url}/chat/completions` | `Authorization: Bearer ...` | `image_url` |
| `anthropic` | `{base_url}/messages` | `x-api-key` + `anthropic-version` | Anthropic `image` source |

Base URLs for OpenAI-compatible and Anthropic-compatible endpoints are not universal. Use the one that matches the selected protocol.

For Anthropic-compatible providers, VisionPower accepts either a base URL ending before `/v1` or one ending in `/v1`; it will try the provider's `/messages` endpoint and fall back to `/v1/messages` on a 404. This handles providers such as MiniMax that document `https://api.minimaxi.com/anthropic` as the Anthropic base URL.

`VISION_POWER_MODEL` must be image-capable. Text-only coding models may return a normal-looking response that says no image was received; VisionPower treats those as configuration errors instead of successful image understanding.

The server also rejects non-HTML upstream outputs. A valid response must contain an `<article>` element because the downstream main model relies on semantic HTML evidence rather than free-form text.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VISION_POWER_API_PROTOCOL` | `openai` | `openai` or `anthropic` |
| `VISION_POWER_API_BASE_URL` | none | Vision API base URL |
| `VISION_POWER_API_KEY` | none | Vision API key |
| `VISION_POWER_MODEL` | none | Vision model name |
| `VISION_POWER_TIMEOUT` | `120` | Request timeout in seconds |

## Install Dependencies

Windows:

```cmd
setup.bat
```

Linux / macOS:

```bash
chmod +x setup.sh
./setup.sh
```

Manual:

```bash
uv venv
uv pip install --python .venv/bin/python -r requirements.txt
```

On Windows, use `.venv\Scripts\python.exe` for the `uv pip install --python` path.

## Output Format

`understand_image` returns semantic HTML containing:

- `<section id="objects">` for detected objects with normalized `data-bbox="x,y,w,h"`.
- `data-confidence="high|medium|low"` and `data-type="text|icon|photo|diagram|table|button|input|other"` where applicable.
- `<section id="text-content">` for OCR text, with machine-readable `<data value="...">`.
- `<section id="layout">` for spatial relationships.
- `<section id="uncertainties">` for ambiguous or low-confidence observations.
- Optional `<!-- METADATA_JSON ... -->` extracted from the HTML.

## Example MCP Config

```json
{
  "mcpServers": {
    "vision-power": {
      "type": "stdio",
      "command": "C:/path/to/VisionPower/mcp/.venv/Scripts/python.exe",
      "args": ["C:/path/to/VisionPower/mcp/server.py"],
      "env": {
        "VISION_POWER_API_KEY": "your-vision-api-key",
        "VISION_POWER_MODEL": "mimo-v2.5",
        "VISION_POWER_API_BASE_URL": "https://token-plan-cn.xiaomimimo.com/v1",
        "VISION_POWER_API_PROTOCOL": "openai",
        "VISION_POWER_TIMEOUT": "120"
      }
    }
  }
}
```

Prefer the repository-level `install.py` for Codex, Claude Code, VS Code/GitHub Copilot, Kilo Code, and OpenClaw.

## Troubleshooting

- Tool missing: restart the MCP client and check `command` / `args` paths.
- API key error: check `VISION_POWER_API_KEY` for the configured base URL.
- Model not found: check `VISION_POWER_MODEL`, `VISION_POWER_API_BASE_URL`, and `VISION_POWER_API_PROTOCOL`.
- Anthropic/OpenAI mismatch: switch `VISION_POWER_API_PROTOCOL` and use the provider's matching base URL.
- Logs: `mcp/logs/vision_power.log`.
