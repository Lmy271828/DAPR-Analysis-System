# DAPR-Analysis-System 项目说明书

## 项目概述

**DAPR-Analysis-System** 是一个基于 "Draw-A-Person-in-the-Rain (DAPR)" 绘画活动的 AI 情绪探索与艺术表达系统。该系统采用双模型安全架构（本地 Qwen3.5 VLM + 云端 Kimi-K2.5 LLM），结合多模态情感分析（绘画+面部表情视频+绘画过程视频）与情感条件图像生成（FLUX.2），为用户提供沉浸式的情绪觉察与创意艺术表达体验。

> ⚠️ **重要声明**：本系统仅为艺术创作与情绪探索工具，不提供任何医学诊断、心理治疗或精神健康评估。如有心理健康需求，请咨询专业持证心理咨询师或精神科医生。

---

## 一、项目架构和功能

### 1.1 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           DAPR-Analysis-System                          │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                │
│  │  创作者界面  │    │  观察伙伴面板  │    │  后端服务   │                │
│  │  (Frontend) │    │ (Therapist) │    │  (Backend)  │                │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                │
│         │                  │                  │                        │
│         └──────────────────┴──────────────────┘                        │
│                            │                                           │
│                    ┌───────┴───────┐                                   │
│                    │  FastAPI +    │                                   │
│                    │   WebSocket   │                                   │
│                    └───────┬───────┘                                   │
│                            │                                           │
│    ┌───────────────────────┼───────────────────────┐                   │
│    │                       │                       │                   │
│    ▼                       ▼                       ▼                   │
│ ┌─────────┐          ┌─────────┐           ┌─────────────┐            │
│ │ 本地VLM │          │ 云端LLM │           │  Image      │            │
│ │ Qwen3.5 │          │Kimi-K2.5│           │  Service    │            │
│ │ AWQ INT4│          │  API    │           │             │            │
│ └────┬────┘          └────┬────┘           └──────┬──────┘            │
│      │                    │                       │                   │
│      ▼                    ▼                       ▼                   │
│ ┌─────────┐          ┌─────────┐           ┌─────────────┐            │
│ │图像/视频│          │文字任务 │           │ ComfyUI     │            │
│ │本地处理 │          │云端处理 │           │ FLUX.2      │            │
│ └─────────┘          └─────────┘           └─────────────┘            │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.2 核心功能模块

#### 1.2.1 受试者交互模块

| 功能 | 描述 |
|------|------|
| **引导阶段** | 提供DAPR绘画活动引导词，帮助用户进入放松的创作状态 |
| **绘画采集** | 支持标准画布(850×1100像素)绘制"雨中人"，同时录制摄像头视频(面部表情)和屏幕录制(绘画过程) |
| **信息采集** | 收集用户基本信息(年龄段、性别)用于年龄适配的观察参考 |
| **图像选择** | 展示AI生成的3个艺术方向图像变体，记录选择行为供用户自我觉察 |
| **报告展示** | 呈现基于画面元素的艺术观察与情绪探索反馈（非诊断） |

#### 1.2.2 观察伙伴模块

| 功能 | 描述 |
|------|------|
| **实时观察** | 通过WebSocket实时查看所有进行中的创作会话 |
| **LLM日志** | 查看详细的LLM输入输出日志，包括分析过程、生成的问题、图像编辑指令等 |
| **FLUX2日志** | 查看图像生成参数和结果，包括工作流配置、生成变体详情 |
| **会话管理** | 查看历史会话列表，支持预览涂鸦、复用历史创作数据进行回顾 |

#### 1.2.3 后端服务模块

| 模块 | 职责 |
|------|------|
| **main.py** | FastAPI主服务，提供REST API和WebSocket接口，管理会话生命周期 |
| **services/llm/core.py** | 双模型LLM服务：本地Qwen3.5 VLM(多模态分析) + 云端Kimi-K2.5(纯文字任务) |
| **services/llm/parsers.py** | JSON解析、契约验证、约束解码集成 |
| **image_service.py** | ComfyUI异步图像生成服务，批量提交+并行轮询，NVFP4/FP4 量化降低显存占用 |
| **agent/** | Agent编排模块：Tool Registry + Plan Engine + Orchestrator + InterviewAgent |
| **models.py** | 数据模型定义，会话状态管理与数据持久化 |
| **db_models.py** | SQLAlchemy ORM模型，支持自动迁移 |
| **config.py** | 系统配置，包括LLM、VLM、ComfyUI、画布、视频等配置参数 |
| **start.sh / stop.sh** | 一键启动/停止脚本（检查环境→启动ComfyUI→启动后端） |

### 1.3 技术栈

| 层级 | 技术 |
|------|------|
| **后端框架** | FastAPI, Python 3.12, SQLite + SQLAlchemy |
| **实时通信** | WebSocket |
| **本地VLM** | Qwen3.5 2B AWQ INT4 (~2.3GB), bf16推理, 支持图像+视频 |
| **云端LLM** | Kimi-K2.5 (Moonshot AI) |
| **图像生成** | FLUX.2 Klein 4B **NVFP4** + Qwen3-4B FP4 (ComfyUI), 0.5MP |
| **结构化输出** | lm-format-enforcer 约束解码 |
| **HTTP 客户端** | aiohttp (异步连接池) |
| **前端** | Vanilla JS, Canvas API, MediaRecorder API |
| **数据存储** | SQLite + Fernet加密, 会话状态持久化 |
| **视频处理** | ffmpeg/ffprobe |
| **Agent架构** | Tool Registry + Plan Engine + Orchestrator |

---

## 二、Agent工作流及记忆继承机制

### 2.1 会话状态流转

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   GUIDANCE  │────▶│  PERMISSION │────▶│   DRAWING   │
│   (引导)    │     │  (权限申请)  │     │   (绘画)    │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                                               ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  QUESTIONING│◀────│  ANALYZING  │◀────│   SUBMIT    │
│   (提问)    │     │   (分析)    │     │  (提交作品)  │
└──────┬──────┘     └─────────────┘     └─────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  GENERATING │────▶│  SELECTING  │────▶│FINAL_QUESTS │
│  (图像生成)  │     │  (图像选择)  │     │ (最终问题)  │
└─────────────┘     └─────────────┘     └──────┬──────┘
                                               │
                                               ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  COMPLETED  │◀────│FINAL_ANALYS │◀────│FINAL_ANSWER │
│   (完成)    │     │  (最终分析)  │     │ (最终回答)  │
└─────────────┘     └─────────────┘     └─────────────┘
```

### 2.2 Agent工作流详解

#### 阶段1：初始分析 (Initial Analysis)

```
输入: 绘画图像 + 摄像头视频(面部表情) + 屏幕录制(绘画过程)
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  LLM分析 (analyze_drawing_stream)                       │
│  - 多模态内容理解 (图像 + 视频帧序列)                      │
│  - 绘画特征观察 (人物大小、位置、雨量表现、遮蔽物等)          │
│  - 表情变化观察 (情绪轨迹描述)                           │
│  - 绘画过程观察 (笔触特征、修改行为)                      │
│  - 生成3个开放式问题用于创作探索                          │
│  - 提出3个温和的氛围推测供用户参考                        │
└─────────────────────────────────────────────────────────┘
    │
    ▼
输出: {analysis, questions, creative_guesstimates}
```

**关键代码片段** (llm_service.py):
```python
def analyze_drawing_stream(self, drawing_path, webcam_video, screen_video):
    # 构建多模态提示词
    prompt = f"""请分析提供的素材（视频帧按时序排列）
    1. 第一张图像：绘画成品
    2. 第一个视频：绘画时的面部表情变化
    3. 第二个视频：绘画过程
    
    JSON结构必须包含以下字段：
    {{
        "analysis": {{...详细分析...}},
        "questions_for_user": ["问题1", "问题2", "问题3"],
        "psychological_guesstimates": ["猜想1", "猜想2", "猜想3"]
    }}"""
    
    # 流式生成，实时返回分析结果
    for chunk, result in self.generate_stream(...):
        yield (chunk, result)
```

#### 阶段2：深度访谈 (Deep Interview)

```
输入: 用户对3个问题的回答 + 基本信息(年龄、性别)
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  对话历史保存                                            │
│  - 保存问答到ConversationManager                        │
│  - 用于最终报告生成时的上下文理解                         │
└─────────────────────────────────────────────────────────┘
    │
    ▼
输出: 更新后的对话历史
```

**记忆继承机制**:
```python
# 保存问答到LLM对话历史（用于最终报告生成）
llm = get_llm_service()
qa_text = "\n\n".join([f"Q: {q}\nA: {a}" for q, a in zip(questions, request.answers)])
llm.conversation.add_message("user", f"【用户回答】\n{qa_text}")
```

#### 阶段3：自适应图像生成 (Adaptive Image Generation)

```
输入: 心理假设 + 绘画分析结果 + 原始绘画图像
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  生成编辑指令 (generate_edit_instructions)               │
│  - 基于DAPR艺术表达方向探索                               │
│  - 分析绘画特征(人物大小、雨强度、遮蔽物、整体氛围等)       │
│  - 生成3个艺术方向的图像编辑变体                           │
│    * 温暖庇护 (安全感增强)                                │
│    * 雨中希望 (希望感引导)                                │
│    * 宁静平衡 (自我力量强化)                              │
└─────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  FLUX.2图像生成 (ComfyUI)                                │
│  - 调用本地ComfyUI服务                                    │
│  - 使用color_the_dapr_doodle_api.json工作流              │
│  - 为每个变体生成彩色化图像                               │
└─────────────────────────────────────────────────────────┘
    │
    ▼
输出: 3个生成的图像变体 (含名称、描述、编辑指令)
```

**自适应风格实现**:
```python
def generate_edit_instructions(self, hypotheses, drawing_path, drawing_analysis):
    # 构建分析摘要
    analysis_summary = f"""
    绘画分析摘要：
    - 人物大小：{drawing_analysis.get('drawing_features', {}).get('figure_size', '未知')}
    - 人物位置：{drawing_analysis.get('drawing_features', {}).get('figure_position', '未知')}
    - 雨的强度：{drawing_analysis.get('drawing_features', {}).get('rain_intensity', '未知')}
    - 遮蔽物：{drawing_analysis.get('drawing_features', {}).get('shelter', '未知')}
    - 整体氛围：{drawing_analysis.get('drawing_features', {}).get('mood', '未知')}
    """
    
    # 生成3个干预方向的编辑指令
    prompt = f"基于DAPR艺术表达方向探索，生成3个图像编辑变体..."
    return self.generate(prompt=prompt, images=[drawing_path])
```

#### 阶段4：投射选择 (Projective Selection)

```
输入: 3个图像变体展示给用户
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  选择行为追踪                                            │
│  - 记录查看顺序 (viewOrder)                              │
│  - 记录鼠标悬停时间 (hoverTime)                          │
│  - 记录犹豫指标 (hesitationIndicators)                   │
│  - 记录最终选择 (finalSelection)                         │
└─────────────────────────────────────────────────────────┘
    │
    ▼
输出: 选择的图像ID + 选择行为数据
```

#### 阶段5：深度探索与最终报告 (Final Analysis)

```
输入: 选择的图像 + 心理假设 + 对话历史 + 选择行为数据
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  生成深入问题 (generate_follow_up_questions)             │
│  - 基于创作选择偏好探索                                   │
│  - 对比原始绘画与选择变体的差异                           │
│  - 探索选择背后的情感倾向                                 │
└─────────────────────────────────────────────────────────┘
    │
    ▼
输入: 用户对深入问题的回答
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  生成最终报告 (generate_final_report)                    │
│  - 整合所有对话历史                                       │
│  - 画面氛围与情绪感受整合                                 │
│  - 自我形象想象观察                                      │
│  - 画面中保护方式的描述                                  │
│  - 创作洞察与后续探索建议                                │
│  - 积极方向与成长潜能关注                                │
└─────────────────────────────────────────────────────────┘
    │
    ▼
输出: 完整JSON格式艺术创作反馈报告（非诊断）
```

### 2.3 记忆继承机制详解

#### 2.3.1 对话历史管理 (ConversationManager)

```python
class ConversationManager:
    """对话历史管理器 - 支持长上下文窗口的记忆继承"""
    
    def __init__(self, max_context_length=32000, max_keep_turns=20):
        self.max_context_length = max_context_length  # 最大上下文长度
        self.max_keep_turns = max_keep_turns          # 保留的最大对话轮数
        self.messages = []                            # 消息列表
        self.summary = ""                             # 历史摘要
    
    def add_message(self, role, content):
        """添加消息并触发智能摘要"""
        self.messages.append({"role": role, "content": content})
        self._manage_context()
    
    def _manage_context(self):
        """上下文管理 - 智能摘要机制"""
        total_length = sum(len(m["content"]) for m in self.messages)
        
        if total_length > self.max_context_length:
            # 保留最近的消息
            recent_messages = self.messages[-self.max_keep_turns:]
            older_messages = self.messages[:-self.max_keep_turns]
            
            # 对旧消息生成摘要
            key_points = []
            for msg in older_messages:
                if msg["role"] == "assistant":
                    key_points.append(f"AI回应: {msg['content'][:50]}...")
            
            self.summary = "\n".join(key_points[-5:])  # 保留最近5个关键点
            self.messages = recent_messages
    
    def get_messages(self, include_summary=True):
        """获取格式化的消息列表（包含历史摘要）"""
        result = []
        if include_summary and self.summary:
            result.append({
                "role": "system", 
                "content": f"【对话历史摘要】\n{self.summary}"
            })
        result.extend(self.messages)
        return result
```

#### 2.3.2 会话数据持久化 (Session Model)

```python
@dataclass
class Session:
    """用户会话 - 完整的状态持久化"""
    
    # 基础信息
    id: str                           # 会话唯一ID
    created_at: str                   # 创建时间
    status: SessionStatus             # 当前状态
    
    # 用户信息
    age_group: Optional[str]          # 年龄段
    gender: Optional[str]             # 性别
    
    # 多媒体数据
    drawing_image: Optional[str]      # 绘画成品路径
    webcam_video: Optional[str]       # 摄像头录像路径
    screen_video: Optional[str]       # 屏幕录制路径
    
    # 分析结果（记忆继承的关键数据）
    initial_analysis: Optional[Dict]  # 初步分析结果
    questions_asked: List[Dict]       # 提出的问题列表
    user_answers: List[str]           # 用户回答列表
    hypotheses: List[Dict]            # 心理假设列表
    
    # 图像生成与选择
    generated_images: List[Dict]      # 生成的图像变体
    selected_image_id: Optional[str]  # 选择的图像ID
    selection_behavior: Optional[Dict]# 选择行为数据
    
    # 最终阶段
    final_questions: List[str]        # 最终深入问题
    final_answers: List[str]          # 最终回答
    final_analysis: Optional[Dict]    # 最终分析报告
    
    def save(self, sessions_dir):
        """保存会话到本地JSON文件"""
        session_file = sessions_dir / f"{self.id}.json"
        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load(cls, session_id, sessions_dir):
        """从本地JSON文件加载会话"""
        session_file = sessions_dir / f"{session_id}.json"
        if session_file.exists():
            with open(session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls.from_dict(data)
        return None
```

#### 2.3.3 记忆继承流程图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          记忆继承机制                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  会话创建                                                                │
│     │                                                                   │
│     ▼                                                                   │
│  ┌─────────────┐                                                        │
│  │ 初始分析阶段 │ ──▶ 保存到 session.initial_analysis                    │
│  │ (LLM分析)   │     保存到 llm.conversation                           │
│  └─────────────┘                                                        │
│     │                                                                   │
│     ▼                                                                   │
│  ┌─────────────┐                                                        │
│  │ 深度访谈阶段 │ ──▶ 追加到 llm.conversation                           │
│  │ (用户回答)  │     保存到 session.user_answers                        │
│  └─────────────┘                                                        │
│     │                                                                   │
│     ▼                                                                   │
│  ┌─────────────┐                                                        │
│  │ 图像生成阶段 │ ──▶ 使用 session.initial_analysis 生成自适应编辑指令   │
│  │ (FLUX.2)   │     保存到 session.generated_images                    │
│  └─────────────┘                                                        │
│     │                                                                   │
│     ▼                                                                   │
│  ┌─────────────┐                                                        │
│  │ 投射选择阶段 │ ──▶ 保存到 session.selected_image_id                  │
│  │ (用户选择)  │     保存到 session.selection_behavior                  │
│  └─────────────┘                                                        │
│     │                                                                   │
│     ▼                                                                   │
│  ┌─────────────┐                                                        │
│  │ 最终分析阶段 │ ──▶ 使用 llm.conversation.get_messages() 获取完整历史 │
│  │ (综合报告)  │     整合所有历史数据生成最终报告                        │
│  └─────────────┘     保存到 session.final_analysis                      │
│     │                                                                   │
│     ▼                                                                   │
│  会话完成                                                                │
│     │                                                                   │
│     ▼                                                                   │
│  历史会话复用 ──▶ 可加载历史会话数据，重新分析或创建新会话                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 三、项目使用步骤

### 3.1 环境准备

#### 3.1.1 系统要求

| 项目 | 要求 |
|------|------|
| **操作系统** | Windows 10/11 或 Linux（推荐） |
| **Python** | 3.12 |
| **GPU** | NVIDIA GPU，显存 ≥ 8GB（RTX 3060/4060/5060 等） |
| **内存** | 建议16GB以上 |
| **存储空间** | 建议10GB以上（模型权重约 7.5GB + 会话数据） |

#### 3.1.2 获取Kimi API Key

1. 访问 [Moonshot AI官网](https://www.moonshot.cn/)
2. 注册账号并登录
3. 进入控制台获取API Key
4. 在终端设置环境变量：

```bash
export MOONSHOT_API_KEY='your-kimi-api-key'
export DAPR_ENCRYPTION_KEY='your-32-byte-base64-key'  # 本地数据加密密钥
# 生成密钥：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3.2 安装步骤

#### 步骤1：克隆项目仓库

```bash
git clone https://github.com/Lmy271828/DAPR-Analysis-System.git
cd DAPR-Analysis-System/DAPR-agent
```

#### 步骤2：创建Python虚拟环境

```bash
conda create -n dapr-agent python=3.12
conda activate dapr-agent
```

#### 步骤3：安装依赖

```bash
pip install -r requirements.txt
```

#### 步骤4：安装并配置ComfyUI

```bash
# 克隆ComfyUI（项目已将其作为子目录包含，也可独立克隆）
cd ComfyUI
pip install -r requirements.txt
```

**下载模型权重并放置到对应目录：**

| 模型 | 文件名 | 大小 | 放置路径 | 下载地址 |
|------|--------|------|----------|----------|
| **扩散模型** (必选) | `flux-2-klein-4b-nvfp4.safetensors` | ~2.5GB | `ComfyUI/models/diffusion_models/` | [Hugging Face](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B/resolve/main/flux-2-klein-4b-nvfp4.safetensors) |
| **扩散模型** (备选) | `flux-2-klein-4b-fp8.safetensors` | ~3.8GB | `ComfyUI/models/diffusion_models/` | [Hugging Face](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B/resolve/main/flux-2-klein-4b-fp8.safetensors) |
| **Text Encoder** (必选) | `qwen_3_4b_fp4_flux2.safetensors` | ~3.8GB | `ComfyUI/models/text_encoders/` | [Hugging Face](https://huggingface.co/Comfy-Org/vae-text-encoder-for-flux-klein-4b/resolve/main/split_files/text_encoders/qwen_3_4b_fp4_flux2.safetensors) |
| **Text Encoder** (备选) | `qwen_3_4b.safetensors` | ~7.5GB | `ComfyUI/models/text_encoders/` | [Hugging Face](https://huggingface.co/Comfy-Org/vae-text-encoder-for-flux-klein-4b/resolve/main/split_files/text_encoders/qwen_3_4b.safetensors) |
| **VAE** (必选) | `flux2-vae.safetensors` | ~336MB | `ComfyUI/models/vae/` | [Hugging Face](https://huggingface.co/Comfy-Org/flux2-dev/resolve/main/split_files/vae/flux2-vae.safetensors) |

**快速下载命令（需安装 [huggingface-cli](https://huggingface.co/docs/huggingface_hub/guides/cli)）：**

```bash
# 扩散模型（NVFP4，8GB显存推荐）
huggingface-cli download black-forest-labs/FLUX.2-klein-4B \
  flux-2-klein-4b-nvfp4.safetensors \
  --local-dir ComfyUI/models/diffusion_models

# Text Encoder（FP4）
huggingface-cli download Comfy-Org/vae-text-encoder-for-flux-klein-4b \
  split_files/text_encoders/qwen_3_4b_fp4_flux2.safetensors \
  --local-dir ComfyUI/models/text_encoders

# VAE
huggingface-cli download Comfy-Org/flux2-dev \
  split_files/vae/flux2-vae.safetensors \
  --local-dir ComfyUI/models/vae
```

**国内镜像加速：**
```bash
export HF_ENDPOINT=https://hf-mirror.com
# 然后执行上述 huggingface-cli 命令
```

**启动ComfyUI（高显存模式，模型常驻显存）：**
```bash
bash DAPR-agent/scripts/comfyui_start.sh
```

#### 步骤5：验证工作流

工作流文件 `color_the_dapr_doodle_api.json` 已预置在项目根目录，后端会自动加载。无需手动导入 ComfyUI 界面。
确保 ComfyUI 服务运行在 `127.0.0.1:8188`。

### 3.3 启动服务

#### 步骤1：启动后端服务

```bash
# 一键启动（检查环境 → 启动ComfyUI → 等待就绪 → 启动后端）
cd DAPR-Analysis-System
bash start.sh

# 或手动启动
cd DAPR-Analysis-System/DAPR-agent/backend
python main.py
```

服务启动后，将显示以下信息：
```
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

#### 步骤2：访问界面

| 界面 | URL |
|------|-----|
| **受试者界面** | http://localhost:8000/ |
| **观察伙伴面板** | http://localhost:8000/therapist/ |

#### 步骤3：一键停止

```bash
bash stop.sh
```

### 3.4 使用流程

#### 3.4.1 受试者使用流程

```
┌─────────────┐
│  开始测试   │
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌─────────────────────────────────────┐
│  阅读引导词  │────▶│ "请你找一个舒服的姿势坐下...想象    │
│             │     │  一幅雨中人的画面..."               │
└─────────────┘     └─────────────────────────────────────┘
       │
       ▼
┌─────────────┐
│ 授权权限    │────▶ 允许使用摄像头和屏幕录制
└─────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────────────────────────────┐
│  绘画阶段   │────▶│ 在标准画布上绘制"雨中人"            │
│             │     │ (同时录制面部表情和绘画过程)          │
└─────────────┘     └─────────────────────────────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────────────────────────────┐
│  回答问题   │────▶│ 回答AI提出的3个开放式问题            │
│             │     │ (关于绘画的感受、压力应对等)          │
└─────────────┘     └─────────────────────────────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────────────────────────────┐
│  选择图像   │────▶│ 从3个生成的图像变体中选择最贴合       │
│             │     │ 心境的一幅                           │
└─────────────┘     └─────────────────────────────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────────────────────────────┐
│  最终问题   │────▶│ 回答1-2个关于选择动机的深入问题       │
└─────────────┘     └─────────────────────────────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────────────────────────────┐
│  查看报告   │────▶│ 查看完整的艺术创作反馈报告            │
│             │     │ (画面氛围观察、创作洞察、探索建议等)   │
└─────────────┘     └─────────────────────────────────────┘
```

#### 3.4.2 观察伙伴使用流程

```
┌─────────────┐
│ 打开监控面板 │────▶ 访问 http://localhost:8000/therapist/
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ 监控会话    │────▶ 实时查看所有进行中的会话状态
└─────────────┘
       │
       ▼
┌─────────────┐
│ 查看日志    │────▶ 查看LLM输入输出、FLUX2生成参数
└─────────────┘
       │
       ▼
┌─────────────┐
│ 查看详情    │────▶ 点击会话查看完整的分析详情
└─────────────┘
       │
       ▼
┌─────────────┐
│ 历史会话    │────▶ 查看历史会话列表，支持复用分析
└─────────────┘
```

### 3.5 API接口文档

#### 3.5.1 REST API

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/session/create` | POST | 创建新会话 |
| `/api/session/{id}` | GET | 获取会话信息 |
| `/api/session/{id}/drawing` | POST | 提交绘画和视频 |
| `/api/session/{id}/analyze` | POST | 启动分析 |
| `/api/session/{id}/answers` | POST | 提交回答 |
| `/api/session/{id}/select` | POST | 选择图像 |
| `/api/image/{session_id}/{filename}` | GET | 获取图像 |
| `/api/history/sessions` | GET | 列出历史会话 |
| `/api/history/analyze` | POST | 分析历史会话 |

#### 3.5.2 WebSocket

| 端点 | 描述 |
|------|------|
| `/ws/subject/{session_id}` | 受试者连接 |
| `/ws/therapist` | 观察伙伴连接 |

### 3.6 配置说明

#### 3.6.1 后端配置 (backend/config.py)

```python
# LLM 配置
LLM_CONFIG = {
    "api_key": os.environ.get("MOONSHOT_API_KEY", ""),  # 从环境变量读取
    "base_url": "https://api.moonshot.cn/v1",
    "model": "kimi-k2.5",
    "temperature": 1,
    "max_tokens": 4096,
    "max_context": 32000,
}

# ComfyUI 配置
COMFYUI_CONFIG = {
    "server_address": "127.0.0.1:8188",
    "workflow_path": "工作流文件路径",
}

# 画布配置
CANVAS_CONFIG = {
    "width": 850,      # 8.5 inches * 100 DPI
    "height": 1100,    # 11 inches * 100 DPI
}
```

#### 3.6.2 自定义系统提示词

编辑 `backend/prompts/DAPR_ANALYSIS_PROMPT.txt` 文件，可以自定义LLM的系统提示词。

### 3.7 故障排除

| 问题 | 解决方案 |
|------|----------|
| **内容生成失败** | 确认 MOONSHOT_API_KEY 已正确设置 |
| **本地VLM加载失败** | 确认 model/ 目录下存在 Qwen3.5 AWQ INT4 权重文件 |
| **ComfyUI连接失败** | 确认ComfyUI服务已启动（`bash DAPR-agent/scripts/comfyui_start.sh`），检查 `config.py` 中的地址配置 |
| **显存OOM** | 当前默认配置已为 8GB 显存优化：扩散模型使用 NVFP4 (`flux-2-klein-4b-nvfp4.safetensors`, 2.5GB) + Text Encoder 使用 FP4 (`qwen_3_4b_fp4_flux2.safetensors`, 3.8GB)。如需进一步降低显存，可关闭本地VLM改用云端分析 |
| **密钥未设置** | 确认 `DAPR_ENCRYPTION_KEY` 环境变量已正确设置，否则会话数据无法保存 |
| **视频录制失败** | 确保使用HTTPS或localhost，检查浏览器权限设置 |
| **JSON解析失败** | 检查 Qwen3.5 是否按指定 Schema 输出；lm-format-enforcer 约束解码会自动保障合法 JSON |

---

## 四、隐私说明

- 所有用户数据仅存储于本地 SQLite 数据库，敏感字段（回答、视频路径）经 Fernet 对称加密
- 原始绘画/视频仅由本地 Qwen3.5 VLM 处理，云端 Kimi 只接收文字分析摘要，实现隐私零泄露
- 编辑后的图片存储在 `ComfyUI/outputs/`
- 数据仅用于当前会话分析，不用于模型训练或外部共享
- 建议在使用前获取用户知情同意，并在引导页勾选确认

---

## 五、许可证

MIT License

---

## 六、致谢

- **kimi-k2.5** by Moonshot AI
- **FLUX.2** by Black Forest Labs
- **ComfyUI** by comfyanonymous

---

*文档版本: 1.2*  
*最后更新: 2026-05-17*
