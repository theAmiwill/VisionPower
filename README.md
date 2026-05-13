# VisionPower

VisionPower packages a local image-understanding MCP server with a matching Codex skill.

The MCP server calls a configured vision model and returns semantic HTML. The skill tells Codex when to call the MCP, how to phrase image-understanding requests, and how to reason over the returned HTML. The active main reasoning model remains controlled by your MCP client, not by this project.

## Repository Layout

```text
VisionPower/
├── mcp/                         # MiMo vision MCP server
│   ├── server.py
│   ├── requirements.txt
│   ├── setup.bat
│   ├── setup.sh
│   └── .env.example
├── skills/
│   └── mimo-vision-mcp/          # Codex skill that calls the MCP
├── examples/
│   └── mcp.json.example
└── install-skill.ps1             # Copies the skill into ~/.codex/skills
```

## Windows Deployment

1. Clone the repository:

```powershell
git clone git@github.com:theAmiwill/VisionPower.git
cd VisionPower
```

2. Install the MCP server dependencies:

```powershell
cd mcp
.\setup.bat
cd ..
```

3. Install the Codex skill:

```powershell
.\install-skill.ps1
```

4. Add the MCP server to your MCP client config, usually `C:\Users\<you>\.mcp.json`.

Use the paths printed by `mcp\setup.bat`, or adapt `examples\mcp.json.example`.

```json
{
  "mcpServers": {
    "mimo-vision": {
      "command": "C:/path/to/VisionPower/mcp/.venv/Scripts/python.exe",
      "args": ["C:/path/to/VisionPower/mcp/server.py"],
      "env": {
        "MIMO_VISION_API_KEY": "your-vision-api-key",
        "MIMO_VISION_MODEL": "mimo-v2.5-pro",
        "MIMO_VISION_API_BASE_URL": "https://api.xiaomimimo.com/v1",
        "MIMO_VISION_TIMEOUT": "120"
      }
    }
  }
}
```

5. Restart the MCP client.

## Changing Devices

After moving to another machine, only these paths should change:

- `command`
- `args`

The skill content is portable. The MCP server reads the vision configuration from `MIMO_VISION_*` environment variables when it starts. To change the vision model, edit those variables and restart the MCP client.

## Important Boundary

Do not configure the main reasoning model in this project. Claude Code or another MCP client decides the active main model. VisionPower only provides an image-understanding tool and returns semantic HTML for whichever main model is currently in use.

## Validation

The current package has been validated with:

```text
quick_validate.py skills/mimo-vision-mcp
MCP stdio initialize
MCP list_tools
MCP call_tool mimo_get_model_info
```

If `mimo_understand_image` returns an API-key error, the MCP server is running but `MIMO_VISION_API_KEY` is not valid for the configured `MIMO_VISION_API_BASE_URL` and `MIMO_VISION_MODEL`.

