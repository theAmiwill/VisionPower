import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = ROOT / "install.py"


def load_installer():
    spec = importlib.util.spec_from_file_location("vision_power_installer", INSTALLER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


installer = load_installer()


def make_config():
    return installer.InstallConfig(
        api_key="test-key",
        model="mimo-v2.5",
        base_url="https://token-plan-cn.xiaomimimo.com/v1",
        protocol="openai",
        timeout="120",
        python_path="C:/VisionPower/mcp/.venv/Scripts/python.exe",
        server_path="C:/VisionPower/mcp/server.py",
        project_dir=ROOT,
        kilo_scope="global",
    )


class InstallerShapeTests(unittest.TestCase):
    def test_codex_uses_mcp_servers_toml(self):
        text = installer.build_codex_toml(make_config())
        self.assertIn("[mcp_servers.vision-power]", text)
        self.assertIn("VISION_POWER_API_PROTOCOL", text)

    def test_claude_code_uses_stdio_server_json(self):
        data = installer.build_claude_json(make_config())
        self.assertEqual(data["type"], "stdio")
        self.assertEqual(data["env"]["VISION_POWER_MODEL"], "mimo-v2.5")

    def test_vscode_uses_servers_root(self):
        data = installer.build_vscode_json(make_config())
        self.assertIn("servers", data)
        self.assertIn("vision-power", data["servers"])
        self.assertEqual(data["servers"]["vision-power"]["env"]["VISION_POWER_API_KEY"], "${input:visionPowerApiKey}")

    def test_kilo_uses_mcp_root_and_command_array(self):
        data = installer.build_kilo_json(make_config())
        self.assertIn("mcp", data)
        self.assertIsInstance(data["mcp"]["vision-power"]["command"], list)
        self.assertEqual(data["mcp"]["vision-power"]["timeout"], 120000)


if __name__ == "__main__":
    unittest.main()
