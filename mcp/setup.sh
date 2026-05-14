#!/usr/bin/env bash
# MiMo Vision MCP Server ? Setup Script
# Requires: Python 3.10+, uv (https://docs.astral.sh/uv/)

set -e
echo "=== MiMo Vision MCP Server Setup ==="

# Check uv
if ! command -v uv &>/dev/null; then
    echo "[ERROR] uv not found. Install it first: https://docs.astral.sh/uv/"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Create venv and install deps
echo "Creating virtual environment..."
if [ -x ".venv/bin/python" ]; then
    echo "Reusing existing .venv"
else
    uv venv
fi

echo "Installing dependencies..."
uv pip install --python .venv/bin/python -r requirements.txt

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Copy .env.example to .env and fill in your API key"
echo "  2. Add the following to your ~/.mcp.json:"
echo ""
cat <<EOF
  {
    "mcpServers": {
      "mimo-vision": {
        "command": "$SCRIPT_DIR/.venv/bin/python",
        "args": ["$SCRIPT_DIR/server.py"],
        "env": {
          "MIMO_VISION_API_KEY": "YOUR_KEY_HERE",
          "MIMO_VISION_MODEL": "mimo-v2.5",
          "MIMO_VISION_API_BASE_URL": "https://token-plan-cn.xiaomimimo.com/v1"
        }
      }
    }
  }
EOF
echo ""
echo "  3. Restart Claude Code"
echo ""
