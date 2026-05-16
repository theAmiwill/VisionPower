---
name: vision-power
description: Use the local VisionPower MCP server to let the current text/main model reason over images through semantic HTML. Use when the user asks to analyze, describe, OCR, inspect, compare, or reason about an image, screenshot, UI, chart, diagram, table image, local image path, image URL, or base64 image using the configured vision-power MCP tools. This skill covers calling `understand_image`, checking `get_vision_config`, interpreting semantic HTML evidence, and handling MCP/configuration errors without configuring or switching the main reasoning model.
metadata:
  { "openclaw": { "requires": { "anyBins": ["python", "python3"] }, "primaryEnv": "VISION_POWER_API_KEY", "install": [ { "id": "api_key", "kind": "input", "label": "Vision API Key", "description": "API key for the configured upstream vision model.", "secret": true, "envVar": "VISION_POWER_API_KEY" }, { "id": "model", "kind": "input", "label": "Vision Model", "description": "Example: mimo-v2.5", "envVar": "VISION_POWER_MODEL" }, { "id": "base_url", "kind": "input", "label": "Vision API Base URL", "description": "Use the provider's OpenAI-compatible or Anthropic-compatible base URL.", "envVar": "VISION_POWER_API_BASE_URL" }, { "id": "protocol", "kind": "select", "label": "API Protocol", "options": ["openai", "anthropic"], "default": "openai", "envVar": "VISION_POWER_API_PROTOCOL" } ] } }
---

# VisionPower

## Boundary

Use this skill to call the local `vision-power` MCP server for image understanding.

The MCP server configures only the upstream vision model. The active main reasoning model is selected by the MCP client session and receives the returned semantic HTML as normal tool output. Do not set, switch, or mention a main model inside this workflow.

## Available MCP Tools

- `understand_image`: analyze an image and return semantic HTML for text-model reasoning.
- `get_vision_config`: inspect the startup vision-model configuration and whether the API key is present.

If these tools are unavailable, tell the user the `vision-power` MCP server is not connected, then check the MCP client config.

## Workflow

1. For image, screenshot, chart, UI, diagram, table-image, or OCR requests, call `understand_image`.
2. If the image arrives as a chat attachment and the current main model may be text-only, ask for or use the saved local file path instead of reasoning over the attachment directly.
3. Pass `image` as an absolute local path, HTTP(S) URL, data URI, or raw base64 string.
4. Write `question` as the exact visual task the user wants answered.
5. Keep `include_json_metadata=true` unless the user explicitly wants a very short visual description.
6. Use default `max_tokens` for detailed UI, chart, or diagram analysis; lower it only for simple OCR or short descriptions.
7. Read the returned semantic HTML as evidence. Use `data-bbox`, `data-confidence`, `data-type`, `text-content`, `layout`, and `uncertainties` when reasoning.
8. Answer from the HTML, and mention uncertainty when low-confidence or ambiguous items appear.

## Attachment Boundary

Some MCP clients send uploaded image attachments to the current main model before tool calls are considered. If that main model is text-only, the client can fail before VisionPower runs. Prefer this user-facing pattern:

`Save the image locally, then ask me to call vision-power with the absolute file path.`

Do not infer that a `/model` error came from VisionPower if it appears immediately after uploading an image. VisionPower only runs after the main model successfully receives the text request and calls `understand_image`.

## Tool Arguments

`understand_image` accepts:

```json
{
  "image": "D:/path/to/image.png",
  "question": "Analyze the visible text and layout in this image.",
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

- OCR: `Extract all visible text, preserving reading order and approximate position.`
- UI screenshot: `Analyze layout, controls, clickable elements, visible text, and uncertainties.`
- Chart: `Identify chart type, axes, trends, key values, and likely conclusions.`
- Diagram: `List components, relationships, arrow directions, labels, and uncertainties.`
- Comparison: call `understand_image` once per image, then compare the returned HTML outputs.

## Error Handling

- Tool missing: the MCP server is not connected or the client config paths are wrong.
- API key error: check `VISION_POWER_API_KEY`.
- Model or endpoint error: check `VISION_POWER_MODEL`, `VISION_POWER_API_BASE_URL`, and `VISION_POWER_API_PROTOCOL`, then restart the MCP client.
- Path error: ask for an absolute image path or URL; do not guess file locations.

Do not use this skill for image generation or editing. Use it only for understanding visual input and returning text/HTML evidence to the current main model.
