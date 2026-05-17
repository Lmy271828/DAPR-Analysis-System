# DAPR-Analysis-System 分阶段重构计划（精确到行号）

> **编制角色**：资深项目架构师  
> **依据**：产品经理批判性建议 + 逐行代码扫描  
> **总工期**：8-10 周（4 个 Phase，串行执行）  

---

## 重构总览

| Phase | 主题 | 工期 | 核心目标 |
|-------|------|------|----------|
| Phase 1 | 伦理合规与数据隔离止损 | 1-2 周 | 删除临床诊断术语，修复会话污染，建立知情同意 |
| Phase 2 | Agent 架构重构 | 3-4 周 | 状态机→ReAct+Function Calling，会话级LLM隔离，语义记忆 |
| Phase 3 | 并发性能与工程化改造 | 2-3 周 | 异步图像生成、数据库存储、前端组件化、HTTPS |
| Phase 4 | 情感图像生成核心能力建设 | 2-3 周 | 情感条件扩散、笔触ControlNet、云端推理、反馈闭环 |

---

## Phase 1：伦理合规与数据隔离止损（Week 1-2）

> **目标**：在最短时间内消除法律风险和数据污染bug，让系统从「非法心理诊断工具」变成「情绪表达艺术伙伴」。

### 1.1 删除临床诊断术语（Prompt层）

**文件**：`DAPR-agent/backend/prompts/DAPR_ANALYSIS_PROMPT.txt`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 1-2 | **修改** | 将「你是一位专业的心理分析专家」改为「你是一位艺术表达引导伙伴，帮助用户通过绘画探索情绪」。删除所有「精神分析投射理论」「心理动力学」等学术包装。 |
| 15-27 | **删除** | 删除整个「压力相关元素评估」表格（雨量强度评分 0-3、乌云密度评分、闪电存在评分）。这些评分系统模拟临床量表，是法律红线。 |
| 28-36 | **删除** | 删除「应对资源元素评估」表格（防护装备存在性评分、防护有效性评分、人物完整性评分）。 |
| 38-62 | **删除** | 删除「人物特征详细分析」中的临床解读表格（画面占比<10% = 自卑感、偏左放置=被动性等）。 |
| 64-92 | **删除** | 删除「特殊意象深度解读」全部小节（乌云与闪电、积水与水坑、防护装备象征意义）。 |
| 105-147 | **删除** | 删除「特殊人群分析指导」全部内容（儿童发展性考虑、青少年高风险指标、老年期特殊意象）。 |
| 150-176 | **删除** | 删除「临床人群特征」全部表格（抑郁症典型特征、焦虑症典型特征、PTSD典型特征）。**这是最危险的部分。** |
| 178-184 | **删除** | 删除「危险/自伤意象处理」表格（血迹/伤口→立即评估自伤风险、坠落/悬崖→评估自杀意念）。 |
| 186-192 | **删除** | 删除「创伤相关意象」表格。 |
| 194-201 | **修改** | 保留「积极转化意象」但改名为「画面中的积极元素」，删除「强化策略」列，改为纯粹的艺术观察描述。 |
| 全文 | **新增** | 在文件顶部新增系统级约束：「禁止输出任何医学诊断、精神疾病标签、风险等级或治疗建议。只允许描述画面中可见的艺术元素和用户的情绪感受。」 |

**文件**：`DAPR-agent/backend/llm_service.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 1508-1518 | **修改** | `generate_final_report()` 的 prompt 中，删除「你是一位资深临床心理专家」「DAPR投射测验」等定位，改为「你是一位创意艺术伙伴」。 |
| 1544-1562 | **删除** | 删除 prompt 中的「压力-资源动态分析」「自我概念评估」「应对风格识别」表格，以及「低/中/高/危机」分级体系。 |
| 1573-1608 | **重写** | 最终报告的 JSON schema 改为非临床字段：`mood_observation`（情绪观察）、`creative_insights`（创作洞察）、`artistic_elements`（艺术元素分析）、`suggested_explorations`（建议探索方向）。删除 `risk_assessment`、`psychological_profile`、`intervention_priorities`。 |
| 1611-1616 | **新增** | 在 prompt 末尾增加硬约束：「严禁使用以下词汇：抑郁、焦虑、PTSD、自杀、自伤、风险等级、诊断、病理、障碍、治疗、干预。」 |

### 1.2 修复单例LLM服务导致的会话污染（致命Bug）

**文件**：`DAPR-agent/backend/llm_service.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 386-397 | **修改** | `KimiService` 类注释改为「每会话独立的LLM服务实例」。 |
| 399-414 | **修改** | `__init__` 增加 `session_id: str` 参数。`self.session_id = session_id`。`ConversationManager` 保留，但只属于本实例。 |
| 410-414 | **修改** | `ConversationManager` 的初始化从 `__init__` 中独立出来，改为按需初始化（lazy init），避免空会话占用内存。 |
| 1629-1636 | **删除** | 删除全局单例 `_llm_service` 和 `get_llm_service()`。 |
| 新增位置 | **新增** | 在 `llm_service.py` 末尾新增工厂函数：`def create_llm_service(session_id: str) -> KimiService:`，每次调用创建新实例。 |

**文件**：`DAPR-agent/backend/main.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 32-33 | **修改** | 删除 `from llm_service import get_llm_service`，改为 `from llm_service import create_llm_service`。 |
| 494-618 | **修改** | `analyze_drawing_task_stream()` 第503行：`llm = get_llm_service()` → `llm = create_llm_service(session_id)`。 |
| 635-676 | **修改** | `submit_answers()` 第650行：`llm = get_llm_service()` → `llm = create_llm_service(request.session_id)`。同时，第652行的 `llm.conversation.add_message` 改为通过**数据库存储**问答记录，不再依赖内存中的 conversation。 |
| 679-746 | **修改** | `generate_images_task()` 第685行：`llm = get_llm_service()` → `llm = create_llm_service(session_id)`。 |
| 797-855 | **修改** | `final_analysis_task()` 第804行：`llm = get_llm_service()` → `llm = create_llm_service(session_id)`。 |
| 858-919 | **修改** | `generate_final_report_task()` 第865行：`llm = get_llm_service()` → `llm = create_llm_service(session_id)`。第875行的 `conversation_history` 改为从数据库读取该会话的问答记录，而非 `llm.conversation.get_messages()`。 |
| 922-951 | **修改** | `submit_final_answers()` 第936行：`llm = get_llm_service()` → `llm = create_llm_service(request.session_id)`。第938行的 `llm.conversation.add_message` 改为数据库存储。 |

### 1.3 前端报告界面去临床化

**文件**：`DAPR-agent/static/therapist.html`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 823-839 | **修改** | `renderSessionDetail()` 中「初步分析」区块，删除「猜想」列表中的 `confidence` 字段显示（不再存在置信度概念）。 |
| 867-887 | **重写** | 「最终分析」区块，删除 `stress_level`、`coping_style`、`emotional_state` 等临床字段的渲染逻辑。改为渲染 `mood_observation`、`creative_insights`、`artistic_elements`。 |
| 1286-1375 | **重写** | `formatLogContent()` 中 `case 'final_report'` 的全部渲染逻辑，适配新的非临床 JSON schema。删除压力水平/应对方式/情绪状态的彩色卡片渲染。 |

**文件**：`DAPR-agent/static/js/app.js`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 新增 | **新增** | 在 `index.html` 的引导页（`guidance-page`）新增知情同意弹窗，用户必须勾选「我了解这只是一个艺术创作探索工具，不提供医疗或心理诊断」才能进入。该状态通过 API 发送到后端存储。 |

### 1.4 数据存储加密与合规

**文件**：`DAPR-agent/backend/models.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 66-70 | **修改** | `Session.save()` 中，在 `json.dump()` 之前，增加敏感字段的加密逻辑（如用户回答、视频路径）。引入 ` cryptography.fernet` 对本地 JSON 中的 `user_answers`、`final_answers`、`webcam_video`、`screen_video` 字段进行对称加密。密钥从环境变量 `DAPR_ENCRYPTION_KEY` 读取。 |
| 72-100 | **修改** | `Session.load()` 中，在 `json.load()` 之后，增加对应的解密逻辑。如果密钥不存在，抛出 `RuntimeError` 阻止启动，强制要求配置加密。 |

---

## Phase 2：Agent 架构重构（Week 3-6）

> **目标**：把硬编码状态机升级为真正的 ReAct Agent，引入 Function Calling、每会话隔离、语义记忆。

### 2.1 引入 ReAct Agent 核心引擎

**新增文件**：`DAPR-agent/backend/agent_core.py`（全新，约 400 行）

```python
# 核心设计：
# 1. ReActLoop: 规划(Plan) → 行动(Act) → 观察(Observe) → 反思(Reflect)
# 2. ToolRegistry: 注册可用工具（analyze_drawing, ask_user, generate_image, finalize）
# 3. SessionAgent: 每会话一个实例，持有自己的 LLM client、记忆、工具状态
```

**文件**：`DAPR-agent/backend/main.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 12-34 | **修改** | 导入区删除 `BackgroundTasks` 的滥用模式。新增 `from agent_core import SessionAgent, ToolRegistry`。 |
| 357-368 | **重写** | `create_session()` 不再只是创建 Session 对象，而是初始化 `SessionAgent(session_id)` 并存入新的 `agent_registry: dict[str, SessionAgent]`。 |
| 481-491 | **重写** | `start_analysis()` 不再直接 `background_tasks.add_task(analyze_drawing_task_stream)`，而是调用 `agent = agent_registry[session_id]; await agent.run("analyze_drawing")`。由 Agent 自己决定下一步。 |
| 494-618 | **删除** | 删除 `analyze_drawing_task_stream()` 函数。其逻辑被拆分为 `agent_core.py` 中的 `DrawingAnalysisTool` 和 `StreamEmitter`。 |
| 679-746 | **删除** | 删除 `generate_images_task()`。改为 Agent 的 `GenerateImageTool`。 |
| 797-855 | **删除** | 删除 `final_analysis_task()`。改为 Agent 的 `AskUserTool` 和 `FollowUpQuestionTool`。 |
| 858-919 | **删除** | 删除 `generate_final_report_task()`。改为 Agent 的 `FinalizeTool`。 |

### 2.2 Function Calling 工具定义

**新增文件**：`DAPR-agent/backend/tools.py`（全新，约 300 行）

| 工具类 | 对应原代码位置 | 职责 |
|--------|---------------|------|
| `AnalyzeDrawingTool` | 原 `llm_service.py:658-771` | 分析绘画，返回情绪观察（非诊断） |
| `AskUserTool` | 原 `main.py:621-632` | 向用户提问，收集回答 |
| `GenerateImageTool` | 原 `image_service.py:175-266` | 调用 ComfyUI 生成情感图像变体 |
| `SelectImageTool` | 原 `main.py:759-794` | 处理用户图像选择 |
| `FinalizeTool` | 原 `llm_service.py:1449-1621` | 生成艺术探索总结报告 |
| `EscalateTool` | 新增 | 当检测到用户表达严重痛苦时，提供心理援助热线（如北京24小时热线），**不诊断，只提供资源** |

**文件**：`DAPR-agent/backend/llm_service.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 493-581 | **重写** | `generate()` 方法增加 `tools: List[Dict]` 参数，支持传入 OpenAI 格式的 function definitions。调用 `client.chat.completions.create(tools=tools, tool_choice="auto")`。 |
| 583-657 | **重写** | `generate_stream()` 同样增加 `tools` 支持，流式输出中检测 `finish_reason="tool_calls"`。 |
| 386-428 | **修改** | `KimiService` 增加 `available_tools: List[BaseTool]` 属性，Agent 在初始化时注入。 |

### 2.3 语义记忆替换截断日志

**新增文件**：`DAPR-agent/backend/memory.py`（全新，约 200 行）

```python
# 核心组件：
# 1. SemanticMemory: 使用 sentence-transformers (all-MiniLM-L6-v2) 对对话做 embedding
# 2. ChromaMemoryStore: 基于 ChromaDB 的向量存储，按 session_id 隔离 collection
# 3. MemoryRetriever: 支持语义检索（similarity_search）和时间线检索（get_recent）
```

**文件**：`DAPR-agent/backend/llm_service.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 328-384 | **删除** | 删除原有的 `ConversationManager` 类（截断式记忆）。 |
| 新增 | **新增** | 在 `KimiService.__init__` 中注入 `SemanticMemory session_memory`。所有 `add_message` 改为 `session_memory.add(session_id, role, content)`。 |
| 576-580 | **修改** | `generate()` 中的历史保存逻辑改为向量存储写入。 |
| 653-656 | **修改** | `generate_stream()` 中的历史保存同样改为向量存储。 |

**文件**：`DAPR-agent/backend/config.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 新增 | **新增** | 增加 `MEMORY_CONFIG = {"embedding_model": "all-MiniLM-L6-v2", "chroma_persist_dir": "./chroma_db", "top_k": 5}`。 |

### 2.4 状态机解耦

**文件**：`DAPR-agent/backend/models.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 12-24 | **保留但弱化** | `SessionStatus` 保留用于前端展示和数据库记录，但**不再驱动业务逻辑**。业务逻辑由 Agent 的决策决定。 |
| 26-100 | **修改** | `Session` 增加 `agent_state: Dict` 字段，存储 Agent 的当前 plan、已执行的工具列表、待观察的结果。这是 Agent 的「工作记忆」。 |

---

## Phase 3：并发性能与工程化改造（Week 5-8，与Phase 2部分并行）

### 3.1 图像生成并行化与异步化

**文件**：`DAPR-agent/backend/image_service.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 1-17 | **修改** | 导入区删除 `urllib.request`，改为 `import aiohttp` 和 `import asyncio`。 |
| 19-31 | **修改** | `ComfyUIService.__init__` 增加 `self.session: aiohttp.ClientSession = aiohttp.ClientSession()`。 |
| 33-68 | **重写** | `upload_image()` 改为 `async def upload_image()`，使用 `aiohttp.MultipartWriter` 替代手写 boundary。 |
| 70-88 | **重写** | `queue_prompt()` 改为 `async def queue_prompt()`，使用 `aiohttp.ClientSession.post()`。 |
| 90-97 | **重写** | `get_history()` 改为 `async def get_history()`。 |
| 98-110 | **重写** | `get_image()` 改为 `async def get_image()`。 |
| 112-122 | **重写** | `wait_for_prompt()` 改为 `async def wait_for_prompt()`，使用 `asyncio.sleep(0.5)` 替代 `time.sleep(0.5)`。 |
| 175-266 | **重写** | `generate_variations()` 核心重构：<br>1. 改为 `async def generate_variations()`<br>2. 第213-264行的 `for` 串行循环改为 `asyncio.gather()` 并行执行：<br>```python<br>tasks = [self._generate_one(input_name, v, output_dir) for v in variations]<br>results = await asyncio.gather(*tasks, return_exceptions=True)<br>```<br>3. 提取 `_generate_one()` 为独立 async 方法，处理单张图的完整流程（modify_workflow → queue_prompt → wait_for_prompt → get_image → save）。 |
| 272-277 | **修改** | `get_image_service()` 保留单例（ComfyUIService 是无状态的，可以共享），但确保内部使用 aiohttp session。 |

### 3.2 数据库替换本地JSON

**新增文件**：`DAPR-agent/backend/database.py`（全新，约 150 行）

使用 SQLAlchemy + SQLite（开发）/ PostgreSQL（生产）替换本地 JSON 文件存储。

```python
# 核心表结构：
# sessions: id, created_at, status, age_group, gender, drawing_image, 
#           agent_state(json), consent_given(bool), encrypted_answers(text)
# messages: id, session_id, role, content, embedding(vector), created_at
# generated_images: id, session_id, variation_id, filename, prompt, user_feedback
```

**文件**：`DAPR-agent/backend/models.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 1-10 | **修改** | 导入区增加 `from sqlalchemy import Column, String, DateTime, JSON, Boolean, create_engine` 等。 |
| 26-100 | **重写** | `Session` dataclass 改为 SQLAlchemy declarative base 的 ORM 类。`save()` 和 `load()` 改为 `db_session.commit()` 和 `db_session.query(Session).get()`。 |
| 102-125 | **修改** | `AnalysisResult`、`GeneratedImage` 同样改为 ORM 模型或内嵌 JSON 字段。 |

**文件**：`DAPR-agent/backend/main.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 36-41 | **修改** | FastAPI 启动事件增加数据库初始化：`@app.on_event("startup")` 中调用 `init_db()` 创建表。 |
| 357-368 | **修改** | `create_session()` 使用 SQLAlchemy session 写入数据库，而非 `session.save(SESSIONS_DIR)`。 |
| 371-378 | **修改** | `get_session()` 使用 `db.query(Session).filter(...).first()`。 |
| 381-478 | **修改** | `submit_drawing()` 中，绘画和视频文件改为存入对象存储路径（或本地文件系统但路径存在数据库），元数据写入数据库。 |

### 3.3 前端工程化：拆分 therapist.html

**新增目录结构**：
```
DAPR-agent/static/
├── src/                    # 新增：源码目录
│   ├── components/
│   │   ├── SessionList.js
│   │   ├── LogViewer.js
│   │   ├── StreamMonitor.js
│   │   └── SessionDetail.js
│   ├── services/
│   │   ├── websocket.js
│   │   └── api.js
│   ├── utils/
│   │   └── formatters.js
│   └── therapist/
│       └── main.js
├── dist/                   # 构建输出（Vite/Rollup）
└── therapist.html          # 精简为入口文件
```

**文件**：`DAPR-agent/static/therapist.html`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 469-1746 | **删除** | 删除全部内联 `<script>`。 |
| 新增 | **新增** | 在 `</body>` 前引入 `<script type="module" src="/static/dist/therapist.js"></script>`。 |

**新增文件**：`DAPR-agent/static/package.json`

```json
{
  "name": "dapr-frontend",
  "scripts": { "build": "vite build", "dev": "vite" },
  "devDependencies": { "vite": "^5.0.0" }
}
```

### 3.4 流式输出节流与WebSocket优化

**文件**：`DAPR-agent/backend/main.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 538 | **修改** | `token_count - last_update >= 5` 改为 `>= 50`（或基于时间节流：每 300ms 最多推送一次）。 |
| 252-273 | **修改** | `_heartbeat_loop()` 中，死连接检测逻辑补充：超过 3 次心跳无 pong，调用 `disconnect_subject()` 清理。 |
| 224-238 | **修改** | `send_to_subject()` 中，增加消息队列背压检测：如果 Redis 缓存队列超过 100 条，丢弃非关键消息（如 chunk）。 |

### 3.5 HTTPS 与摄像头权限

**新增文件**：`DAPR-agent/backend/cert/.gitkeep`

**文件**：`DAPR-agent/backend/main.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 36-41 | **新增** | 启动时检测环境变量 `ENABLE_HTTPS=true`，若启用则加载 `cert.pem` 和 `key.pem`，使用 `uvicorn.run(app, ssl_keyfile=..., ssl_certfile=...)`。 |
| 新增文档 | **新增** | `README.md` 增加本地 HTTPS 自签名证书生成命令：`openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes`。 |

---

## Phase 4：情感图像生成核心能力建设（Week 7-10）

> **目标**：让「情感图像生成」从配角变主角，建立技术壁垒。

### 4.1 情感语义嵌入驱动生成

**新增文件**：`DAPR-agent/backend/emotion_embedding.py`（全新，约 250 行）

```python
# 核心 pipeline：
# 1. 绘画 → 视觉编码器（CLIP ViT-L/14）→ image embedding
# 2. 用户回答 → 文本编码器（sentence-transformers）→ text embedding
# 3. 情感标签（PAD模型：Pleasure-Arousal-Dominance）→ emotion embedding
# 4. 三者融合 → 条件向量 → 输入 ComfyUI 的 Conditioning
```

**文件**：`DAPR-agent/backend/llm_service.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 1217-1286 | **重写** | `generate_edit_instructions()` 不再只是生成英文 prompt 字符串，而是返回包含 `emotion_vector: List[float]` 的结构。该向量由 `emotion_embedding.py` 根据绘画分析和用户回答计算得出。 |

### 4.2 ComfyUI 工作流升级：情感条件注入

**新增文件**：`DAPR-agent/comfy_workflows/emotion_conditioned_workflow.json`

使用 ComfyUI 的 `CLIPTextEncode` + 自定义节点（或 ` ConditioningConcat`）将情感向量注入扩散过程。

**文件**：`DAPR-agent/backend/image_service.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 124-173 | **重写** | `modify_workflow()` 不再硬编码节点 ID（`"76"`, `"75:74"` 等）。改为基于节点类型的智能查找：<br>```python<br>load_image_node = next(n for n in wf.values() if n.get("class_type") == "LoadImage")<br>load_image_node["inputs"]["image"] = input_image<br>```<br>同时，如果传入 `emotion_vector`，查找 `CLIPTextEncode` 节点并在其 `inputs` 中增加 `emotion_conditioning`。 |
| 新增 | **新增** | 增加 `modify_workflow_with_emotion(wf, emotion_vector: List[float])` 方法，将情感向量通过 ComfyUI 的 `unet` 条件注入。 |

### 4.3 笔触轨迹 ControlNet

**新增文件**：`DAPR-agent/backend/stroke_processor.py`（全新，约 300 行）

```python
# 从 canvas 录制数据中提取：
# 1. 笔触时序（stroke timeline）: [(x, y, pressure, timestamp), ...]
# 2. 笔触密度热图（heatmap）
# 3. 绘画速度曲线（velocity profile）
# 输出：ControlNet 可用的条件图（如 scribble + depth + 时序mask）
```

**文件**：`DAPR-agent/static/js/app.js`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 414-442 | **修改** | `initCanvas()` 中，除了初始化 canvas 2D context，增加 `strokeRecorder` 实例，记录每笔画的 `mousemove`/`touchmove` 坐标序列和时间戳。 |
| 548-580 | **修改** | `startDrawing()` 和 `draw()` 中，每笔触发生 `strokeRecorder.addPoint(x, y, timestamp)`。 |
| 679-755 | **修改** | `submitDrawing()` 中，除了提交 `drawingData`（PNG base64），额外提交 `strokeData: JSON.stringify(state.strokeRecorder.getStrokes())`。 |

**文件**：`DAPR-agent/backend/main.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 381-478 | **修改** | `submit_drawing()` 的 `DrawingRequest` 增加 `stroke_data: Optional[str]` 字段。后端保存 `stroke.json` 到会话目录。 |
| 新增 | **新增** | 在图像生成前，调用 `stroke_processor.py` 将笔触数据转换为 ControlNet 条件图，传递给 `image_service.py`。 |

### 4.4 用户反馈闭环：情感迭代生成

**新增文件**：`DAPR-agent/backend/feedback_loop.py`（全新，约 150 行）

```python
# 当用户对生成图像进行反馈（喜欢/无感/不喜欢）时：
# 1. 更新该图像的情感向量（向用户偏好方向移动）
# 2. 若用户选择「再试一次」，使用更新后的向量重新生成
# 3. 记录用户的情感偏好 profile（长期向量），用于未来会话
```

**文件**：`DAPR-agent/static/js/app.js`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 836-876 | **修改** | `showGeneratedImages()` 中，每张图像卡片增加 thumbs-up / thumbs-down 按钮。点击后通过 WebSocket 发送 `{"type": "image_feedback", "image_id": ..., "feedback": "like|dislike"}`。 |
| 新增 | **新增** | 新增 `requestRegenerate(image_id)` 功能，允许用户对某张图要求「再生成一张类似的但更有希望感」。 |

**文件**：`DAPR-agent/backend/main.py`

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| 954-976 | **新增** | 新增 WebSocket handler：`elif msg_type == "image_feedback":`，调用 `feedback_loop.py` 更新情感向量。 |

### 4.5 ~~云端推理适配（脱离本地GPU依赖）~~ → **冻结**

**决策**: 本地 ComfyUI 生成作为核心壁垒与差异化优势，不执行云端降级。本地推理零成本、低延迟、绘画数据隐私不外流，是产品核心卖点。

以下设计文档保留供未来扩展参考，但大赛前不实现：

~~**新增文件**：`DAPR-agent/backend/image_providers/`（全新目录）~~

```
image_providers/
├── __init__.py
├── base.py              # 抽象基类 ImageProvider
├── comfyui_local.py     # 本地 ComfyUI（现有逻辑）
├── replicate_provider.py # Replicate API (FLUX.1-schnell)
├── runpod_provider.py   # RunPod Serverless
└── fal_provider.py      # fal.ai
```

~~**文件**：`DAPR-agent/backend/config.py`~~

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| ~~33-38~~ | ~~**修改**~~ | ~~`COMFYUI_CONFIG` 改为 `IMAGE_GEN_CONFIG`~~ |

~~**文件**：`DAPR-agent/backend/image_service.py`~~

| 行号 | 动作 | 具体内容 |
|------|------|----------|
| ~~19-31~~ | ~~**修改**~~ | ~~`ComfyUIService` 改名为 `ImageGenerationService`~~ |
| ~~175-266~~ | ~~**修改**~~ | ~~`generate_variations()` 改为调用 `self.provider.generate_batch()`~~ |

---

## 附录：重构检查清单（Checklist）

### 启动前必须完成（Phase 1 底线）
- [ ] `DAPR_ANALYSIS_PROMPT.txt` 中已无任何临床诊断术语
- [ ] `llm_service.py:1629-1636` 全局单例已删除，每次请求创建独立 `KimiService`
- [ ] `models.py:66-70` 本地 JSON 已加密
- [ ] `index.html` 已增加知情同意弹窗
- [ ] `therapist.html` 不再渲染压力等级/风险等级

### 架构验收标准（Phase 2 底线）
- [ ] `main.py` 中所有 `BackgroundTasks.add_task(硬编码函数)` 已删除
- [ ] Agent 可以通过 Function Calling 自主决定调用哪个工具
- [ ] 多并发测试：10个用户同时会话，对话历史互不污染
- [ ] `memory.py` 的语义检索可以找回3轮之前的关键信息

### 性能验收标准（Phase 3 底线）
- [ ] 3张图像生成总耗时 < 15秒（并行化后）
- [ ] `therapist.html` 已拆分为组件，通过 Vite 构建
- [ ] 数据库可承载 1000+ 会话查询不卡顿
- [ ] HTTPS 环境下摄像头权限可正常获取

### 核心能力验收标准（Phase 4 底线）
- [ ] 用户绘画的笔触数据被记录并用于 ControlNet 条件
- [ ] 情感向量可以影响生成图像的色调/氛围（非随机）
- [ ] 用户可以对图像点赞/点踩，系统能基于反馈生成更贴合偏好的变体
- ~~[ ] 系统可在无本地 GPU 环境下运行~~ → **本地 ComfyUI 作为核心壁垒，不追求无 GPU 运行**

---

**架构师备注**：

这份计划的本质是**把项目从「一个危险的 demo」改造成「一个可参赛、可演示、可扩展的工程产品」**。Phase 1 是生存问题，不做等于违法；Phase 2 是产品定义问题，不做等于伪Agent；Phase 3 是工程质量，不做等于不能看；Phase 4 是大赛竞争力，不做等于跑题。

如果资源极度有限（只剩1周），**只做 Phase 1 + Phase 3 中的数据库替换**。本地 ComfyUI 生成是产品的核心壁垒与差异化优势——零成本、低延迟、绘画数据隐私不外流，无需追求无 GPU 降级方案。
