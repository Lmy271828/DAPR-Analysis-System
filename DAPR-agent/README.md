# DAPR Agent - 雨中人绘画心理分析系统

基于 "Draw-A-Person-in-the-Rain (DAPR)" 绘画测试的交互式心理分析 Agent 系统。

## 🎯 系统概述

本系统结合多模态 AI 分析（Qwen3-VL-4B）和图像生成（FLUX.2 Klein 4B），为心理分析提供了一套完整的数字化解决方案：

1. **引导阶段** - 渐进式放松引导，引导用户进入绘画状态
2. **绘画阶段** - 标准画布，同步录制面部表情和绘画过程
3. **分析阶段** - Qwen3-VL 分析绘画、表情和过程视频
4. **交互阶段** - AI 与用户对话，深入了解心理状态
5. **生成阶段** - Flux2 根据分析结果生成多种心理图像变体
6. **选择阶段** - 用户选择最贴合心境的图像
7. **报告阶段** - 生成最终心理分析报告

## 📁 项目结构

```
DAPR-agent/
├── backend/                    # 后端服务
│   ├── main.py                # FastAPI 主服务
│   ├── config.py              # 配置文件
│   ├── models.py              # 数据模型
│   ├── llm_service.py         # Qwen3-VL 服务
│   ├── image_service.py       # ComfyUI 图像服务
│   └── __init__.py
├── frontend/                   # 前端页面
├── static/                     # 静态文件
│   ├── index.html             # 受试者界面
│   ├── therapist.html         # 咨询师监控面板
│   ├── css/
│   │   └── style.css          # 样式文件
│   └── js/
│       └── app.js             # 前端应用
├── sessions/                   # 会话数据存储
├── outputs/                    # 生成的图像
├── requirements.txt            # Python 依赖
├── start.bat                  # Windows 启动脚本
└── README.md                  # 项目文档
```

## 🚀 快速开始

### 环境要求

- Python 3.12
- SM>=8.9的NVIDIA GPU
- Windows 10/11 或 Linux（推荐）
  ```bash
  conda create -n dapr-agent python=3.12
  conda activate dapr-agent
  cd DAPR-agent
  pip install -r requirements.txt
  ```


### 前置准备

1. **准备 kimi api**
   - 登录moonshot官网获取api
   - 在终端设置你的api key
   ```bash
   export MOONSHOT_API_KEY = 'your-kimi-api-key'
   ```

2. **准备 ComfyUI 和 FLUX.2 Klein 4B**
   ```bash
   git clone https://github.com/Comfy-Org/ComfyUI.git
   cd ComfyUI
   pip install -r requirements.txt
   python main.py
   # 按快捷键 Ctrl+O，选择 color_the_dapr_doodle.json 导入
   ```
   - 确保 ComfyUI 服务运行在 `127.0.0.1:8188`
   - 确认ComfyUI导入工作流文件 `color_the_dapr_doodle.json`
   - 按照指引配置缺失的模型权重


### 启动服务

```bash
cd DAPR-agent/backend
python main.py
```

### 访问界面

- **受试者界面**: http://localhost:8000
- **咨询师监控面板**: http://localhost:8000/therapist

## 📖 使用指南

### 受试者流程

1. **阅读引导词** - 按照引导进行深呼吸和想象
2. **授权权限** - 允许使用摄像头和屏幕录制
3. **绘画** - 在标准画布上绘制"雨中人"
4. **回答问题** - 回答 AI 提出的问题
5. **选择图像** - 从生成的图像中选择最贴合心境的一幅
6. **完成** - 查看心理分析报告

### 咨询师监控

1. 打开 http://localhost:8000/therapist
2. 实时监控所有进行中的会话
3. 查看详细的 LLM 输入输出日志
4. 查看 FLUX2 图像生成参数和结果
5. 点击会话查看完整分析详情

## ⚙️ 配置说明

### 后端配置 (`backend/config.py`)

```python
# LLM 配置
LLM_CONFIG = {
    "model_path": "模型路径",
    "temperature": 0.7,
    "max_tokens": 2048,      # 8GB 显存建议 2048
    "max_context": 8192,     # 8GB 显存建议 8192
}

# ComfyUI 配置
COMFYUI_CONFIG = {
    "server_address": "127.0.0.1:8188",
    "workflow_path": "工作流文件路径",
}

# 画布配置
CANVAS_CONFIG = {
    "width": 850,   # 8.5 inches * 100 DPI
    "height": 1100, # 11 inches * 100 DPI
}
```

### 自定义系统提示词

编辑 `backend/prompts` 中的 `DAPR_ANALYSIS_PROMPT` 变量。

## 🔒 隐私说明

- 所有用户数据仅存储于本地 `sessions/` 目录
- 视频和绘画数据仅用于当前会话分析
- 咨询师可查看完整过程用于专业评估
- 建议在使用前获取用户知情同意

## 🛠️ 技术栈

- **后端**: FastAPI, WebSocket, Python 3.12
- **前端**: Vanilla JS, Canvas API, MediaRecorder API
- **AI 模型**: kimi-k2.5
- **图像生成**: FLUX.2 Klein 4B Distill (ComfyUI)
- **通信**: WebSocket 实时推送

## 📝 API 文档

### REST API

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/session/create` | POST | 创建新会话 |
| `/api/session/{id}` | GET | 获取会话信息 |
| `/api/session/{id}/drawing` | POST | 提交绘画和视频 |
| `/api/session/{id}/analyze` | POST | 启动分析 |
| `/api/session/{id}/answers` | POST | 提交回答 |
| `/api/session/{id}/select` | POST | 选择图像 |
| `/api/image/{session_id}/{filename}` | GET | 获取图像 |

### WebSocket

| 端点 | 描述 |
|------|------|
| `/ws/subject/{session_id}` | 受试者连接 |
| `/ws/therapist` | 咨询师监控连接 |

## 🔧 故障排除

### 模型加载失败
- 检查模型文件路径是否正确
- 确认 llama.cpp 已正确编译
- 检查 CUDA 驱动是否正常

### ComfyUI 连接失败
- 确认 ComfyUI 服务已启动
- 检查 `config.py` 中的地址配置
- 确认工作流文件存在且有效

### 视频录制失败
- 确保使用 HTTPS 或 localhost
- 检查浏览器权限设置
- 确认摄像头和屏幕录制权限已授予

### 前端显示异常
- 清除浏览器缓存
- 检查浏览器控制台错误
- 确认使用现代浏览器 (Chrome/Edge/Firefox)

## 📄 许可证

MIT License

## 🙏 致谢

- Qwen3-VL by Alibaba Cloud
- FLUX.2 by Black Forest Labs
- ComfyUI by comfyanonymous

## 📧 联系方式

如有问题或建议，欢迎提交 Issue 或 PR。
