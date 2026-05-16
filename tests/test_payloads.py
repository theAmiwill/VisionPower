import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "mcp" / "server.py"
PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="


def load_server():
    spec = importlib.util.spec_from_file_location("vision_power_server", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


server = load_server()


class PayloadBuilderTests(unittest.TestCase):
    def test_openai_payload_accepts_local_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "image.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
            prepared = server._prepare_image(str(image_path))
            payload = server._build_openai_payload(prepared, "describe", 256)

        block = payload["messages"][1]["content"][0]
        self.assertEqual(block["type"], "image_url")
        self.assertTrue(block["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_openai_payload_accepts_url(self):
        prepared = server._prepare_image("https://example.com/image.png")
        payload = server._build_openai_payload(prepared, "describe", 256)
        block = payload["messages"][1]["content"][0]
        self.assertEqual(block["image_url"]["url"], "https://example.com/image.png")

    def test_openai_payload_accepts_raw_base64(self):
        prepared = server._prepare_image(PNG_B64)
        payload = server._build_openai_payload(prepared, "describe", 256)
        block = payload["messages"][1]["content"][0]
        self.assertEqual(block["image_url"]["url"], f"data:image/png;base64,{PNG_B64}")

    def test_anthropic_payload_accepts_local_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "image.png"
            image_path.write_bytes(b"\x89PNG\r\n\x1a\n")
            prepared = server._prepare_image(str(image_path))
            payload = server._build_anthropic_payload(prepared, "describe", 256)

        block = payload["messages"][0]["content"][0]
        self.assertEqual(block["type"], "image")
        self.assertEqual(block["source"]["type"], "base64")
        self.assertEqual(block["source"]["media_type"], "image/png")

    def test_anthropic_payload_accepts_url(self):
        prepared = server._prepare_image("https://example.com/image.png")
        payload = server._build_anthropic_payload(prepared, "describe", 256)
        block = payload["messages"][0]["content"][0]
        self.assertEqual(block["source"], {"type": "url", "url": "https://example.com/image.png"})

    def test_anthropic_payload_accepts_raw_base64(self):
        prepared = server._prepare_image(PNG_B64)
        payload = server._build_anthropic_payload(prepared, "describe", 256)
        block = payload["messages"][0]["content"][0]
        self.assertEqual(block["source"]["type"], "base64")
        self.assertEqual(block["source"]["data"], PNG_B64)

    def test_anthropic_endpoint_supports_base_with_or_without_v1(self):
        self.assertEqual(
            server._anthropic_messages_endpoints("https://api.example.com/anthropic"),
            [
                "https://api.example.com/anthropic/messages",
                "https://api.example.com/anthropic/v1/messages",
            ],
        )
        self.assertEqual(
            server._anthropic_messages_endpoints("https://api.example.com/anthropic/v1"),
            ["https://api.example.com/anthropic/v1/messages"],
        )

    def test_clean_html_strips_reasoning_block(self):
        cleaned = server._clean_html("<think>hidden reasoning</think>\n<article>ok</article>")
        self.assertEqual(cleaned, "<article>ok</article>")

    def test_missing_image_response_is_detected(self):
        html = "<article><p>未检测到传入的图片内容，无法进行文字识别。</p></article>"
        self.assertTrue(server._looks_like_missing_image_response(html))

    def test_semantic_html_requires_article(self):
        self.assertTrue(server._looks_like_semantic_html("<article data-source=\"vision\"></article>"))
        self.assertFalse(server._looks_like_semantic_html("无法识别"))


if __name__ == "__main__":
    unittest.main()
