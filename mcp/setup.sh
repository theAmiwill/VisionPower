#!/usr/bin/env bash
# VisionPower MCP Server Setup Script
# Requires: Python 3.10+, uv (https://docs.astral.sh/uv/)

set -e
echo "=== VisionPower MCP Server Setup ==="

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
echo "  1. From the repository root, run: python install.py"
echo "  2. Or add the following to your MCP client config:"
echo ""
cat <<EOF
  {
    "mcpServers": {
      "vision-power": {
        "type": "stdio",
        "command": "$SCRIPT_DIR/.venv/bin/python",
        "args": ["$SCRIPT_DIR/server.py"],
        "env": {
          "VISION_POWER_API_KEY": "YOUR_KEY_HERE",
          "VISION_POWER_MODEL": "mimo-v2.5",
          "VISION_POWER_API_BASE_URL": "https://token-plan-cn.xiaomimimo.com/v1",
          "VISION_POWER_API_PROTOCOL": "openai",
          "VISION_POWER_TIMEOUT": "120"
        }
      }
    }
  }
EOF
echo ""
echo "  3. Restart your MCP client"
echo ""
