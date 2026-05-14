# MiMo Vision MCP Server

将视觉语言模型封装为 MCP 工具，供 Claude Code 或任何 MCP 客户端调用。图片理解结果以语义 HTML 返回，专为下游纯文本模型推理设计。

本 MCP 只配置和调用**识图模型**。当前会话使用的**主推理模型**由 Claude Code / MCP 客户端自己决定；本 MCP 不设置、不切换、也不绑定主推理模型。

## 工作原理

```
用户传入图片
      ↓
mimo_understand_image (本 MCP)
      ↓
调用视觉语言模型 (mimo-v2.5 / 可切换)
      ↓
返回语义 HTML (data-bbox, confidence, uncertainties)
      ↓
当前使用的文本模型读取 HTML 进行推理
```

## 注册工具

| 工具名 | 功能 | 只读 |
|--------|------|------|
| `mimo_understand_image` | 调用视觉模型理解图片，返回语义 HTML | Yes |
| `mimo_get_model_info` | 查看当前启动时读取到的识图模型配置 | Yes |

## 输出格式

返回的语义 HTML 包含：

- **`<section id="objects">`** — 检测到的对象，每个带 `data-bbox="x,y,w,h"` (归一化 0-1 坐标)、`data-confidence="high|medium|low"`、`data-type="text|icon|photo|diagram|table|button|input|other"`
- **`<section id="text-content">`** — OCR 文字，用 `<data value="...">` 包裹
- **`<section id="layout">`** — 空间布局描述
- **`<section id="uncertainties">`** — **强制包含**，列出所有不确定内容
- **`<!-- METADATA_JSON ... -->`** — 附加 JSON 元数据注释块，供程序解析

文本模型可据此做空间推理，例如"左上角的按钮"、"表格第 3 行"。

## 快速开始

### 前置条件

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) 包管理器
- 视觉语言模型的 API Key

### 安装

**Windows:**
```cmd
setup.bat
```

**Linux / macOS:**
```bash
chmod +x setup.sh && ./setup.sh
```

**或手动安装:**
```bash
uv venv
# Windows
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
# Linux/macOS
uv pip install --python .venv/bin/python -r requirements.txt
```

### 配置

1. 复制环境变量文件并填入 API Key：
```bash
cp .env.example .env
# 编辑 .env，填入 MIMO_VISION_API_KEY
```

2. 在 `~/.mcp.json` (Claude Code 的 MCP 配置文件) 中添加：

```json
{
  "mcpServers": {
    "mimo-vision": {
      "command": "C:\\path\\to\\mimo-vision-mcp\\.venv\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\mimo-vision-mcp\\server.py"],
      "env": {
        "MIMO_VISION_API_KEY": "你的API_KEY",
        "MIMO_VISION_MODEL": "mimo-v2.5",
        "MIMO_VISION_API_BASE_URL": "https://token-plan-cn.xiaomimimo.com/v1"
      }
    }
  }
}
```

3. 重启 Claude Code。

## 使用方式

在 Claude Code 中直接描述你的需求即可，Claude 会自动调用 `mimo_understand_image`：

- "帮我看看这张图片里有什么"
- "识别图片中的文字"
- "分析这个截图的布局"

也可以直接传入本地文件路径、URL 或 base64：

```
图片路径: C:\photos\screenshot.png
图片URL:  https://example.com/image.jpg
Base64:   iVBORw0KGgo...
```

## 切换识图模型

主推理模型不用在本 MCP 中配置。你在 Claude Code 里使用 A 模型时，MCP 返回的 HTML 会交给 A 模型继续推理；你切到 B 模型后，MCP 返回的同样是 HTML，后续推理由 B 模型完成。

识图模型只在 MCP 启动时读取。要切换识图模型，修改 `.mcp.json` 中的环境变量，然后重启 MCP 客户端：

```json
"env": {
  "MIMO_VISION_API_KEY": "你的key",
  "MIMO_VISION_MODEL": "gpt-4o",
  "MIMO_VISION_API_BASE_URL": "https://api.openai.com/v1"
}
```

兼容任何 OpenAI `/v1/chat/completions` 格式的视觉模型：

| 模型 | API 地址 |
|------|----------|
| mimo-v2.5 | `https://token-plan-cn.xiaomimimo.com/v1` |
| GPT-4o | `https://api.openai.com/v1` |
| Claude (Anthropic) | 需适配 Anthropic 格式 |
| Qwen2.5-VL | 自部署或 DashScope |
| DeepSeek-VL | `https://api.deepseek.com/v1` |

## 环境变量说明

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MIMO_VISION_API_BASE_URL` | `https://token-plan-cn.xiaomimimo.com/v1` | 识图 API 端点 (OpenAI 兼容) |
| `MIMO_VISION_API_KEY` | (必填) | 识图 API 密钥 |
| `MIMO_VISION_MODEL` | `mimo-v2.5` | 默认识图模型名称 |
| `MIMO_VISION_TIMEOUT` | `120` | 识图请求超时 (秒) |

> 注意：主聊天模型能使用 `mimo-v2.5`，不代表 MCP 子进程会自动继承同一套凭据。`mimo-vision` MCP 必须在 `.mcp.json` 的 `env` 里单独传入对 `MIMO_VISION_API_BASE_URL` 有效的 `MIMO_VISION_API_KEY`。

## 文件结构

```
mimo-vision-mcp/
├── server.py           # MCP server 主文件
├── requirements.txt    # Python 依赖
├── .env.example        # 环境变量模板
├── setup.bat           # Windows 安装脚本
├── setup.sh            # Linux/macOS 安装脚本
└── README.md           # 本文件
```

## 迁移到其他机器

1. 将整个 `mimo-vision-mcp/` 文件夹复制到目标机器
2. 运行 `setup.bat` (Windows) 或 `setup.sh` (Linux/macOS)
3. 配置 `~/.mcp.json`（注意更新路径）
4. 重启 Claude Code

## 故障排查

**Q: 工具没有出现在 Claude Code 中**
A: 检查 `~/.mcp.json` 路径是否正确，重启 Claude Code。

**Q: API 调用失败**
A: 检查 `.mcp.json` 中的 `MIMO_VISION_API_KEY` 是否正确，网络是否可达。

**Q: 想查看运行日志**
A: 日志在 `mimo-vision-mcp/logs/mimo_vision.log`。

## License

MIT
