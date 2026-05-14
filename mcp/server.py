#!/usr/bin/env python3
"""
MiMo Vision MCP Server.

Calls a configurable vision-language model (default: mimo-v2.5) to understand images,
then returns semantic HTML with structured metadata for downstream text-model reasoning.
"""

import base64
import json
import logging
import os
import re
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field
from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Configuration — defaults for the vision model only.
# The main reasoning model is selected by the MCP client session and is never
# configured by this server.
# ---------------------------------------------------------------------------

DEFAULT_API_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
DEFAULT_MODEL = "mimo-v2.5"
DEFAULT_TIMEOUT = 120.0

VISION_MODEL = os.environ.get("MIMO_VISION_MODEL", DEFAULT_MODEL)
VISION_API_BASE_URL = os.environ.get("MIMO_VISION_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")
VISION_API_KEY = os.environ.get("MIMO_VISION_API_KEY", "")
VISION_TIMEOUT = float(os.environ.get("MIMO_VISION_TIMEOUT", str(DEFAULT_TIMEOUT)))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=str(LOG_DIR / "mimo_vision.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("mimo_vision")

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "mimo_vision_mcp",
    instructions=(
        "Use this MCP server to understand images via a vision-language model. "
        "It returns semantic HTML with data-bbox coordinates, confidence scores, "
        "and uncertainty notes — designed for downstream text-model reasoning."
    ),
)

# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------

IMAGE_SOURCE_DESC = (
    "Image input. Accepts: "
    "(1) base64 string (raw or data-URI prefixed), "
    "(2) HTTP(S) URL, "
    "(3) local file path."
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
        description="Whether to include structured JSON metadata (bbox, confidence, object type) in the output.",
    )
    max_tokens: int = Field(
        default=4096,
        description="Max tokens for the vision model response.",
        ge=256,
        le=16384,
    )


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

def _prepare_image_content(raw: str) -> dict:
    """Normalise user-supplied image input into the API content block format."""
    raw = raw.strip()

    # Already a data-URI
    if raw.startswith("data:image/"):
        return {"type": "image_url", "image_url": {"url": raw}}

    # HTTP(S) URL
    if raw.startswith(("http://", "https://")):
        return {"type": "image_url", "image_url": {"url": raw}}

    # Local file path — read and encode
    path = Path(raw)
    if path.is_file():
        suffix = path.suffix.lower().lstrip(".")
        mime = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "webp": "image/webp",
            "gif": "image/gif", "bmp": "image/bmp",
        }.get(suffix, "image/png")
        b64 = base64.b64encode(path.read_bytes()).decode()
        return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}

    # Assume raw base64 string
    if re.match(r"^[A-Za-z0-9+/=\s]+$", raw):
        return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{raw}"}}

    raise ValueError(
        "Cannot parse 'image' input. Provide a base64 string, HTTP(S) URL, or local file path."
    )


# ---------------------------------------------------------------------------
# VLM API call
# ---------------------------------------------------------------------------

async def _call_vlm(
    image_content: dict,
    question: str,
    max_tokens: int,
) -> str:
    """Call the configured vision-language model and return its text response."""
    if not VISION_API_KEY:
        raise RuntimeError(
            "MIMO_VISION_API_KEY is not set. Export it as an environment variable or pass it via MCP config."
        )
    if not VISION_API_BASE_URL.startswith(("http://", "https://")):
        raise ValueError("MIMO_VISION_API_BASE_URL must start with http:// or https://.")

    messages = [
        {
            "role": "system",
            "content": _build_system_prompt(VISION_MODEL),
        },
        {
            "role": "user",
            "content": [
                image_content,
                {"type": "text", "text": question},
            ],
        },
    ]

    payload = {
        "model": VISION_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "top_p": 0.95,
    }

    async with httpx.AsyncClient(timeout=VISION_TIMEOUT) as client:
        resp = await client.post(
            f"{VISION_API_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {VISION_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()

    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Post-processing: strip markdown fences if the model wraps output
# ---------------------------------------------------------------------------

def _clean_html(raw: str) -> str:
    """Remove markdown code fences the model may have added."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:html)?\s*\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Tool: understand_image
# ---------------------------------------------------------------------------

@mcp.tool(
    name="mimo_understand_image",
    annotations={
        "title": "Understand Image (MiMo Vision)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def mimo_understand_image(
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
        description="Whether to include structured JSON metadata (bbox, confidence, object type) in the output.",
    ),
    max_tokens: int = Field(
        default=4096,
        description="Max tokens for the vision model response.",
        ge=256,
        le=16384,
    ),
) -> str:
    """Use a vision-language model to understand an image and return semantic HTML.

    The output is designed for a downstream text-only reasoning model:
    - Semantic HTML with <article>, <section>, <h1>-<h4>, <table>, etc.
    - data-bbox="x,y,w,h" on every detected region (normalized 0-1 coordinates)
    - data-confidence="high|medium|low" on every object
    - data-type="text|icon|photo|diagram|table|button|input|other"
    - Mandatory <section id="uncertainties"> for ambiguous content
    - NO CSS, NO scripts, NO presentational markup

    The returned HTML can be directly consumed by a text model for spatial reasoning
    (e.g., "the button in the top-left", "row 3 of the table").

    Args:
        params: Validated input containing:
            - image (str): base64 / URL / local file path
            - question (str): instruction for the vision model
            - include_json_metadata (bool): attach JSON metadata block
            - max_tokens (int): max generation tokens

    Returns:
        str: Semantic HTML string (plus optional JSON metadata block).
    """
    try:
        params = UnderstandImageInput(
            image=image,
            question=question,
            include_json_metadata=include_json_metadata,
            max_tokens=max_tokens,
        )
        image_content = _prepare_image_content(params.image)
        logger.info(
            "Calling vision model=%s base_url=%s question_len=%d",
            VISION_MODEL,
            VISION_API_BASE_URL,
            len(params.question),
        )

        html_output = await _call_vlm(image_content, params.question, params.max_tokens)
        html_output = _clean_html(html_output)

        # Optionally append JSON metadata block for programmatic parsing
        if params.include_json_metadata:
            metadata = _extract_metadata_from_html(html_output)
            html_output += f"\n\n<!-- METADATA_JSON\n{json.dumps(metadata, ensure_ascii=False, indent=2)}\n-->"

        logger.info("VLM response length=%d", len(html_output))
        return html_output

    except httpx.HTTPStatusError as e:
        msg = _handle_http_error(e)
        logger.error("HTTP error: %s", msg)
        return f'<article data-source="vision" data-error="true"><p>Error: {msg}</p></article>'
    except Exception as e:
        logger.error("Unexpected error: %s", e, exc_info=True)
        return f'<article data-source="vision" data-error="true"><p>Error: {type(e).__name__}: {e}</p></article>'


# ---------------------------------------------------------------------------
# Tool: get_model_info
# ---------------------------------------------------------------------------

@mcp.tool(
    name="mimo_get_model_info",
    annotations={
        "title": "Get Vision Model Info",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def mimo_get_model_info() -> str:
    """Return the startup vision model configuration.

    Returns:
        str: JSON with vision model name, API base URL, and timeout.
    """
    return json.dumps({
        "vision_model": VISION_MODEL,
        "vision_api_base_url": VISION_API_BASE_URL,
        "vision_timeout": VISION_TIMEOUT,
        "vision_api_key_env": "MIMO_VISION_API_KEY",
        "vision_api_key_set": bool(VISION_API_KEY),
        "main_reasoning_model": "selected by the MCP client session; this server never configures it",
    }, indent=2)


# ---------------------------------------------------------------------------
# Metadata extraction (best-effort regex from HTML)
# ---------------------------------------------------------------------------

def _extract_metadata_from_html(html: str) -> dict:
    """Extract structured metadata from the VLM's HTML output."""
    objects = []
    for m in re.finditer(
        r'<(?:li|span|td|data)[^>]*'
        r'data-bbox="([^"]*)"[^>]*'
        r'(?:data-confidence="([^"]*)")?[^>]*'
        r'(?:data-type="([^"]*)")?[^>]*'
        r'>(.*?)</(?:li|span|td|data)>',
        html,
        re.DOTALL,
    ):
        objects.append({
            "bbox": m.group(1),
            "confidence": m.group(2) or "unknown",
            "type": m.group(3) or "unknown",
            "text": re.sub(r"<[^>]+>", "", m.group(4)).strip(),
        })

    has_uncertainties = bool(re.search(r'id="uncertainties"', html))

    return {
        "vision_model": VISION_MODEL,
        "vision_api_base_url": VISION_API_BASE_URL,
        "object_count": len(objects),
        "has_uncertainties_section": has_uncertainties,
        "objects": objects[:200],  # cap at 200 to avoid huge payloads
    }


# ---------------------------------------------------------------------------
# Error handler
# ---------------------------------------------------------------------------

def _handle_http_error(e: httpx.HTTPStatusError) -> str:
    code = e.response.status_code
    if code == 401:
        return (
            "Invalid API key for the configured vision API. "
            f"Check MIMO_VISION_API_KEY for {VISION_API_BASE_URL} and model '{VISION_MODEL}'."
        )
    if code == 403:
        return "Access denied. Verify your API key has vision model permissions."
    if code == 404:
        return f"Model '{VISION_MODEL}' not found at {VISION_API_BASE_URL}. Check the vision model and API base URL."
    if code == 429:
        return "Rate limit exceeded. Wait before retrying."
    return f"API returned status {code}: {e.response.text[:200]}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
