#!/usr/bin/env python3
"""VisionPower MCP server.

Calls a configured vision-language model, then returns semantic HTML for the
current text/main model to reason over. This server configures only the upstream
vision model, never the MCP client's main reasoning model.
"""

import base64
import html
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_API_BASE_URL = ""
DEFAULT_MODEL = ""
DEFAULT_PROTOCOL = "openai"
DEFAULT_TIMEOUT = 120.0

VISION_MODEL = os.environ.get("VISION_POWER_MODEL", DEFAULT_MODEL)
VISION_API_BASE_URL = os.environ.get("VISION_POWER_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")
VISION_API_KEY = os.environ.get("VISION_POWER_API_KEY", "")
VISION_API_PROTOCOL = os.environ.get("VISION_POWER_API_PROTOCOL", DEFAULT_PROTOCOL).strip().lower()
VISION_TIMEOUT = float(os.environ.get("VISION_POWER_TIMEOUT", str(DEFAULT_TIMEOUT)))

SUPPORTED_PROTOCOLS = {"openai", "anthropic"}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=str(LOG_DIR / "vision_power.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("vision_power")

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "vision-power",
    instructions=(
        "Use this MCP server to understand images via a configured vision-language model. "
        "It returns semantic HTML with data-bbox coordinates, confidence scores, "
        "and uncertainty notes for downstream text-model reasoning."
    ),
)

# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------

IMAGE_SOURCE_DESC = (
    "Image input. Accepts a raw base64 string, data:image/* base64 URI, HTTP(S) URL, "
    "or local file path."
)

DEFAULT_QUESTION = "请详细描述这张图片中的所有可见内容，包括对象、文字、布局、空间关系。如有看不清或不确定的部分，请明确指出。"


class UnderstandImageInput(BaseModel):
    """Input for image understanding."""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    image: str = Field(
        ...,
        description=IMAGE_SOURCE_DESC,
        min_length=1,
        max_length=1_000_000,
    )
    question: str = Field(
        default=DEFAULT_QUESTION,
        description="The question or instruction to ask about the image.",
        max_length=4096,
    )
    include_json_metadata: bool = Field(
        default=True,
        description="Whether to include structured JSON metadata extracted from the returned HTML.",
    )
    max_tokens: int = Field(
        default=4096,
        description="Max tokens for the vision model response.",
        ge=256,
        le=16384,
    )


@dataclass(frozen=True)
class PreparedImage:
    """Normalized image input used by protocol-specific payload builders."""

    kind: str
    media_type: str
    data: str | None = None
    url: str | None = None

    def as_data_uri(self) -> str:
        if self.kind == "url" and self.url:
            return self.url
        if self.kind == "base64" and self.data:
            return f"data:{self.media_type};base64,{self.data}"
        raise ValueError("Prepared image is missing URL or base64 data.")


# ---------------------------------------------------------------------------
# Prompt template for semantic HTML output
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """\
You are a vision-language model tasked with describing images for a downstream **text-only** reasoning model.
Your output MUST be **semantic HTML** that a text model can parse as source code (NOT rendered visually).

## Output Rules

1. **Structure** — use ONLY these HTML tags:
   <article>, <section>, <h1>-<h4>, <p>, <ul>, <ol>, <li>, <table>, <thead>, <tbody>, <tr>, <th>, <td>, <figure>, <figcaption>, <span>, <div>, <data>
   NO <style>, <script>, <iframe>, or any presentational attributes except data-*.

2. **Spatial coordinates** — for every identifiable region/object, use data-bbox="x,y,w,h" (normalized 0-1) on the element.
   Example: <span data-bbox="0.12,0.34,0.25,0.10">Submit button</span>

3. **Confidence** — add data-confidence="high|medium|low" to each object element.

4. **Object type** — add data-type="text|icon|photo|diagram|table|button|input|other" where applicable.

5. **Uncertainties section** — MANDATORY. Include a <section id="uncertainties"> listing every item you are NOT 100% sure about. Use <li data-confidence="low"> for ambiguous items. If nothing is uncertain, write <li>None detected</li>.

6. **Text content** — use <data value="..."> for machine-readable text values (OCR results, numbers, labels).

7. **No CSS, no scripts, no complex nesting.** Keep it flat and semantic.

8. **Language** — describe in the same language as the user's question.

## Output Template

`html
<article data-source="vision" data-model="{model_name}">
  <h1>Image Summary</h1>
  <p>One-sentence overall description.</p>

  <section id="objects">
    <h2>Detected Objects</h2>
    <ul>
      <li data-bbox="x,y,w,h" data-confidence="..." data-type="...">Object description</li>
      ...
    </ul>
  </section>

  <section id="text-content">
    <h2>Text / OCR</h2>
    <table>
      <thead><tr><th>Region</th><th>Text</th><th>Confidence</th></tr></thead>
      <tbody>
        <tr><td data-bbox="..."><data value="...">Region label</data></td><td data-confidence="...">Extracted text</td></tr>
        ...
      </tbody>
    </table>
  </section>

  <section id="layout">
    <h2>Layout &amp; Spatial Relationships</h2>
    <p>Describe spatial arrangement.</p>
  </section>

  <section id="uncertainties">
    <h2>Uncertainties</h2>
    <ul>
      <li data-confidence="low">Description of uncertain element</li>
      ...
    </ul>
  </section>
</article>
`

Follow this template strictly. Output ONLY the HTML, no markdown fences, no commentary.
"""


def _build_system_prompt(model_name: str) -> str:
    return SYSTEM_PROMPT_TEMPLATE.replace("{model_name}", model_name)


# ---------------------------------------------------------------------------
# Image encoding helpers
# ---------------------------------------------------------------------------

def _guess_media_type(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "gif": "image/gif",
        "bmp": "image/bmp",
    }.get(suffix, "image/png")


def _strip_base64_whitespace(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _prepare_image(raw: str) -> PreparedImage:
    """Normalize user-supplied image input before protocol-specific formatting."""
    raw = raw.strip()

    if raw.startswith(("http://", "https://")):
        return PreparedImage(kind="url", media_type="", url=raw)

    data_uri_match = re.match(r"^data:(image/[A-Za-z0-9.+-]+);base64,(.*)$", raw, re.DOTALL)
    if data_uri_match:
        return PreparedImage(
            kind="base64",
            media_type=data_uri_match.group(1),
            data=_strip_base64_whitespace(data_uri_match.group(2)),
        )

    path = Path(raw)
    if path.is_file():
        return PreparedImage(
            kind="base64",
            media_type=_guess_media_type(path),
            data=base64.b64encode(path.read_bytes()).decode("ascii"),
        )

    compact = _strip_base64_whitespace(raw)
    if re.fullmatch(r"[A-Za-z0-9+/]+={0,2}", compact):
        return PreparedImage(kind="base64", media_type="image/png", data=compact)

    raise ValueError(
        "Cannot parse 'image' input. Provide a raw base64 string, data:image/* URI, HTTP(S) URL, or local file path."
    )


def _build_openai_image_block(image: PreparedImage) -> dict[str, Any]:
    return {"type": "image_url", "image_url": {"url": image.as_data_uri()}}


def _build_anthropic_image_block(image: PreparedImage) -> dict[str, Any]:
    if image.kind == "url" and image.url:
        return {"type": "image", "source": {"type": "url", "url": image.url}}
    if image.kind == "base64" and image.data:
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image.media_type,
                "data": image.data,
            },
        }
    raise ValueError("Prepared image is missing URL or base64 data.")


# ---------------------------------------------------------------------------
# Protocol-specific payload builders
# ---------------------------------------------------------------------------

def _build_openai_payload(image: PreparedImage, question: str, max_tokens: int) -> dict[str, Any]:
    return {
        "model": VISION_MODEL,
        "messages": [
            {"role": "system", "content": _build_system_prompt(VISION_MODEL)},
            {
                "role": "user",
                "content": [
                    _build_openai_image_block(image),
                    {"type": "text", "text": question},
                ],
            },
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "top_p": 0.95,
    }


def _build_anthropic_payload(image: PreparedImage, question: str, max_tokens: int) -> dict[str, Any]:
    return {
        "model": VISION_MODEL,
        "system": _build_system_prompt(VISION_MODEL),
        "messages": [
            {
                "role": "user",
                "content": [
                    _build_anthropic_image_block(image),
                    {"type": "text", "text": question},
                ],
            }
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "top_p": 0.95,
    }


def _anthropic_messages_endpoints(base_url: str) -> list[str]:
    base = base_url.rstrip("/")
    endpoints = [f"{base}/messages"]
    if not base.endswith("/v1"):
        endpoints.append(f"{base}/v1/messages")
    return endpoints


def _extract_openai_text(data: dict[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("OpenAI-compatible response did not contain choices[0].message.content.") from exc
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)


def _extract_anthropic_text(data: dict[str, Any]) -> str:
    content = data.get("content", [])
    parts = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("text"):
                parts.append(str(block["text"]))
    if parts:
        return "".join(parts)
    if isinstance(data.get("completion"), str):
        return data["completion"]
    raise RuntimeError("Anthropic-compatible response did not contain content[].text.")


# ---------------------------------------------------------------------------
# VLM API call
# ---------------------------------------------------------------------------

async def _call_vlm(image: PreparedImage, question: str, max_tokens: int) -> str:
    """Call the configured vision-language model and return its text response."""
    if VISION_API_PROTOCOL not in SUPPORTED_PROTOCOLS:
        raise ValueError("VISION_POWER_API_PROTOCOL must be either 'openai' or 'anthropic'.")
    if not VISION_API_KEY:
        raise RuntimeError(
            "VISION_POWER_API_KEY is not set. Export it as an environment variable or pass it via MCP config."
        )
    if not VISION_MODEL:
        raise RuntimeError("VISION_POWER_MODEL is not set. Pass it via MCP config.")
    if not VISION_API_BASE_URL:
        raise RuntimeError("VISION_POWER_API_BASE_URL is not set. Pass it via MCP config.")
    if not VISION_API_BASE_URL.startswith(("http://", "https://")):
        raise ValueError("VISION_POWER_API_BASE_URL must start with http:// or https://.")

    if VISION_API_PROTOCOL == "anthropic":
        endpoints = _anthropic_messages_endpoints(VISION_API_BASE_URL)
        headers = {
            "x-api-key": VISION_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = _build_anthropic_payload(image, question, max_tokens)
        extractor = _extract_anthropic_text
    else:
        endpoints = [f"{VISION_API_BASE_URL}/chat/completions"]
        headers = {
            "Authorization": f"Bearer {VISION_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = _build_openai_payload(image, question, max_tokens)
        extractor = _extract_openai_text

    async with httpx.AsyncClient(timeout=VISION_TIMEOUT) as client:
        last_response: httpx.Response | None = None
        for endpoint in endpoints:
            resp = await client.post(endpoint, headers=headers, json=payload)
            last_response = resp
            if resp.status_code == 404 and endpoint != endpoints[-1]:
                continue
            resp.raise_for_status()
            return extractor(resp.json())

    if last_response is not None:
        last_response.raise_for_status()
    raise RuntimeError("Vision API request failed before receiving a response.")


# ---------------------------------------------------------------------------
# Post-processing and metadata extraction
# ---------------------------------------------------------------------------

def _clean_html(raw: str) -> str:
    """Remove markdown code fences the model may have added."""
    text = raw.strip()
    text = re.sub(r"^\s*<think>.*?</think>\s*", "", text, flags=re.IGNORECASE | re.DOTALL)
    if text.startswith("```"):
        text = re.sub(r"^```(?:html)?\s*\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _looks_like_missing_image_response(html_text: str) -> bool:
    if "data-bbox=" in html_text:
        return False
    text = re.sub(r"<[^>]+>", " ", html_text).lower()
    patterns = (
        "no image",
        "image not provided",
        "image was not provided",
        "no image provided",
        "no image attached",
        "did not receive image",
        "no visual input",
        "未检测到输入图片",
        "未检测到传入的图片",
        "未接收到图片",
        "未收到图片",
        "未提供图片",
        "未附上任何图像",
        "无图片内容",
    )
    return any(pattern in text for pattern in patterns)


def _looks_like_semantic_html(html_text: str) -> bool:
    return bool(re.search(r"<article(?:\s|>)", html_text, flags=re.IGNORECASE))


def _extract_metadata_from_html(html_text: str) -> dict[str, Any]:
    """Extract structured metadata from the VLM's HTML output."""
    objects = []
    for match in re.finditer(
        r'<(?:li|span|td|data)[^>]*'
        r'data-bbox="([^"]*)"[^>]*'
        r'(?:data-confidence="([^"]*)")?[^>]*'
        r'(?:data-type="([^"]*)")?[^>]*'
        r'>(.*?)</(?:li|span|td|data)>',
        html_text,
        re.DOTALL,
    ):
        objects.append({
            "bbox": match.group(1),
            "confidence": match.group(2) or "unknown",
            "type": match.group(3) or "unknown",
            "text": re.sub(r"<[^>]+>", "", match.group(4)).strip(),
        })

    return {
        "vision_model": VISION_MODEL,
        "vision_api_base_url": VISION_API_BASE_URL,
        "vision_api_protocol": VISION_API_PROTOCOL,
        "object_count": len(objects),
        "has_uncertainties_section": bool(re.search(r'id="uncertainties"', html_text)),
        "objects": objects[:200],
    }


def _error_article(message: str) -> str:
    safe_message = html.escape(message, quote=True)
    return f'<article data-source="vision" data-error="true"><p>Error: {safe_message}</p></article>'


def _handle_http_error(exc: httpx.HTTPStatusError) -> str:
    code = exc.response.status_code
    if code == 401:
        return (
            "Invalid API key for the configured vision API. "
            f"Check VISION_POWER_API_KEY for {VISION_API_BASE_URL} using protocol '{VISION_API_PROTOCOL}'."
        )
    if code == 403:
        return "Access denied. Verify your API key has permission to call the configured vision model."
    if code == 404:
        return f"Model or endpoint not found. Check VISION_POWER_MODEL='{VISION_MODEL}' and VISION_POWER_API_BASE_URL='{VISION_API_BASE_URL}'."
    if code == 429:
        return "Rate limit exceeded. Wait before retrying."
    return f"API returned status {code}: {exc.response.text[:300]}"


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@mcp.tool(
    name="understand_image",
    annotations={
        "title": "Understand Image",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def understand_image(
    image: str = Field(
        ...,
        description=IMAGE_SOURCE_DESC,
        min_length=1,
        max_length=1_000_000,
    ),
    question: str = Field(
        default=DEFAULT_QUESTION,
        description="The question or instruction to ask about the image.",
        max_length=4096,
    ),
    include_json_metadata: bool = Field(
        default=True,
        description="Whether to include structured JSON metadata extracted from the returned HTML.",
    ),
    max_tokens: int = Field(
        default=4096,
        description="Max tokens for the vision model response.",
        ge=256,
        le=16384,
    ),
) -> str:
    """Understand an image and return semantic HTML for text-model reasoning."""
    try:
        params = UnderstandImageInput(
            image=image,
            question=question,
            include_json_metadata=include_json_metadata,
            max_tokens=max_tokens,
        )
        prepared_image = _prepare_image(params.image)
        logger.info(
            "Calling vision model=%s protocol=%s base_url=%s question_len=%d",
            VISION_MODEL,
            VISION_API_PROTOCOL,
            VISION_API_BASE_URL,
            len(params.question),
        )

        html_output = await _call_vlm(prepared_image, params.question, params.max_tokens)
        html_output = _clean_html(html_output)
        if not _looks_like_semantic_html(html_output):
            raise RuntimeError(
                "The configured vision model did not return the required semantic HTML. "
                "Use a vision-capable model/endpoint for VISION_POWER_MODEL."
            )
        if _looks_like_missing_image_response(html_output):
            raise RuntimeError(
                "The configured vision model did not process the supplied image. "
                "Use a vision-capable model/endpoint for VISION_POWER_MODEL."
            )

        if params.include_json_metadata:
            metadata = _extract_metadata_from_html(html_output)
            html_output += f"\n\n<!-- METADATA_JSON\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n-->"

        logger.info("Vision response length=%d", len(html_output))
        return html_output

    except httpx.HTTPStatusError as exc:
        message = _handle_http_error(exc)
        logger.error("HTTP error: %s", message)
        return _error_article(message)
    except Exception as exc:
        logger.error("Unexpected error: %s", exc, exc_info=True)
        return _error_article(f"{type(exc).__name__}: {exc}")


@mcp.tool(
    name="get_vision_config",
    annotations={
        "title": "Get VisionPower Config",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def get_vision_config() -> str:
    """Return startup vision-model configuration."""
    return json.dumps({
        "vision_model": VISION_MODEL,
        "vision_api_base_url": VISION_API_BASE_URL,
        "vision_api_protocol": VISION_API_PROTOCOL,
        "vision_timeout": VISION_TIMEOUT,
        "vision_api_key_env": "VISION_POWER_API_KEY",
        "vision_api_key_set": bool(VISION_API_KEY),
        "supported_protocols": sorted(SUPPORTED_PROTOCOLS),
        "main_reasoning_model": "selected by the MCP client session; this server never configures it",
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
