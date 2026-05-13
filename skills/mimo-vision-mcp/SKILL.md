---
name: mimo-vision-mcp
description: Use the local MiMo Vision MCP server to let the current text/main model reason over images through semantic HTML. Use when the user asks to analyze, describe, OCR, inspect, compare, or reason about an image, screenshot, UI, chart, diagram, table image, local image path, image URL, or base64 image using the configured mimo-vision MCP tool. This skill covers calling `mimo_understand_image`, checking `mimo_get_model_info`, and handling configuration errors without configuring or switching the main reasoning model.
---

# MiMo Vision MCP

## Boundary

Use this skill to call the local `mimo-vision` MCP server for image understanding.

The MCP server only configures the **vision model**. The active main reasoning model is selected by the MCP client session, such as Claude Code, and receives the returned semantic HTML as normal tool output. Do not set, switch, or mention a main model inside this MCP workflow.

## Available MCP Tools

- `mimo_understand_image`: analyze an image and return semantic HTML for text-model reasoning.
- `mimo_get_model_info`: inspect the startup vision-model configuration and whether the API key is present.

If these tools are unavailable, do not improvise a replacement. Tell the user the `mimo-vision` MCP server is not connected, then check the MCP client config.

## Required Configuration

The MCP client config should run the local server:

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

On another machine, update only the `command` and `args` paths to that machine's project location. Use `/` in JSON paths on Windows to avoid escaping mistakes.

To change the vision model, edit `MIMO_VISION_MODEL`, `MIMO_VISION_API_BASE_URL`, and `MIMO_VISION_API_KEY` in the MCP config, then restart the MCP client. Do not add per-call model switching.

## Workflow

1. If the user asks about an image, screenshot, chart, UI, diagram, or OCR task, use `mimo_understand_image`.
2. Pass the image as a local path, HTTP(S) URL, data URI, or raw base64 string.
3. Write `question` as the exact visual task the user wants answered.
4. Keep `include_json_metadata=true` unless the user only wants a short visual description.
5. Use a lower `max_tokens` for quick OCR or one-sentence description; use the default for detailed UI, chart, or diagram analysis.
6. Read the returned semantic HTML as evidence. Use `data-bbox`, `data-confidence`, `data-type`, `text-content`, `layout`, and `uncertainties` when reasoning.
7. Answer the user from the HTML. Mention uncertainty when the HTML includes low-confidence or ambiguous items.

## Tool Arguments

`mimo_understand_image` accepts:

```json
{
  "image": "D:/path/to/image.png",
  "question": "请分析这张图的布局和可见文字",
  "include_json_metadata": true,
  "max_tokens": 4096
}
```

Required:

- `image`

Optional:

- `question`: defaults to a detailed Chinese visual description prompt.
- `include_json_metadata`: defaults to `true`.
- `max_tokens`: defaults to `4096`.

## Question Patterns

Use direct task prompts:

- OCR: `请提取图片中的所有可见文字，保留顺序和大致位置。`
- UI screenshot: `请分析这个界面的布局、控件、可点击元素、可见文字和不确定项。`
- Chart: `请识别图表类型、坐标轴、趋势、关键数值和可能的结论。`
- Diagram: `请列出组件、连接关系、箭头方向、标签和不确定项。`
- Comparison: call `mimo_understand_image` once per image, then compare the returned HTML outputs.

## Error Handling

- API key error: tell the user to check `MIMO_VISION_API_KEY` for the configured `MIMO_VISION_API_BASE_URL`.
- Model not found: tell the user to check `MIMO_VISION_MODEL` and `MIMO_VISION_API_BASE_URL`, then restart the MCP client.
- Tool missing: tell the user the MCP server is not connected or the config paths are wrong.
- Path error: ask for an absolute image path or URL; do not guess file locations.

Do not use this skill for image generation or editing. Use it only for understanding visual input and returning text/HTML evidence to the current main model.
