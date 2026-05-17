# Changelog

> 本日志遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范。  
> 版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)（当前处于 0.x 快速迭代期）。

---

## [Unreleased] — 重构进行中

### 🎙️ 自主访谈 Agent（已完成）

#### 已完成

- **InterviewAgent — 替换固定问卷的对话式智能访谈**
  - 新增 `agent/interview_agent.py`：`InterviewAgent` 类实现自主访谈主循环
    - `MAX_TURNS=8` / `MIN_TURNS=2` 轮次控制，防止无限追问与过早结束
    - `asyncio.Event` 阻塞等待用户回答，非轮询、低 CPU 占用
    - `_is_sufficient()` → LLM 评估信息是否足够生图
    - `_generate_next_question()` → LLM 根据对话历史动态生成追问
    - `_enter_image_generation()` → 从完整对话提取生图 prompt，提交 `GenerateImageTool` Plan
    - `to_dict()` / `from_dict()` → 状态持久化，页面刷新后可恢复
    - 5 个状态：`idle` / `evaluating` / `asking` / `waiting` / `complete`
  - `llm_service.py`：InterviewAgent 直接复用 `KimiService.generate()` 方法，通过 `asyncio.to_thread()` 异步调用，无需新增专用接口
  - `models.py`：`Session` 新增 `interview_state`（InterviewAgent 序列化状态）和 `conversation_history`（聊天历史数组）
  - `models.py`：`SessionStatus` 新增 `conversing` 状态，标识访谈进行中
  - `main.py`：
    - `interview_agents: Dict[str, InterviewAgent]` 注册表，会话级单例
    - `POST /api/session/{id}/chat-answer` 新端点，接收用户回答并驱动 Agent 继续
    - 分析流完成后自动启动 InterviewAgent（替代旧固定问卷）
    - 页面刷新时自动恢复 InterviewAgent 状态
  - **前端：聊天式访谈 UI**
    - `index.html`：`questioning-page` 从表单改造为聊天界面
    - `app.js`：
      - `handleChatQuestion(msg)` → 渲染 Agent 消息气泡
      - `handleInterviewComplete(msg)` → 显示「准备生成」过渡页
      - `sendChatAnswer()` → 发送用户回答到 `/chat-answer`
      - `showGeneratingPage()` → 从 `generating` 状态恢复时显示进度
    - 新增 WebSocket 消息类型：`chat_question`、`interview_complete`、`agent_state` 进度、`agent_error` 错误
  - **咨询师面板：对话历史展示**
    - `therapist.html`：新增 `.interview-chat-history` / `.interview-msg` 等 CSS 气泡样式
    - `session-detail.js`：`renderConversationHistory()` 渲染完整对话记录
    - 新增「自主访谈记录」区块，在会话详情页显示 Agent 与用户的全部问答
  - **向后兼容**：旧 `/answers` REST API 仍然保留，历史会话可正常查看

---

### 🏛️ Agent 架构重构（已完成）

#### 已完成

- **轻量级 Agent 编排器 — Tool + Plan 模式**
  - 新增 `agent/tools.py`：`BaseTool` 抽象基类 + `ToolWrapper` 零改动包装器 + `NotifyUserTool`
  - 新增 `agent/plan.py`：`Plan` / `Step` / `StepStatus` 执行引擎 + 4 个预定义 Plan 模板（绘画后/回答后/选择后/最终回答后）
  - 新增 `agent/orchestrator.py`：`AgentOrchestrator` 顺序执行 Plan，支持指数退避重试、关键 Tool 失败终止、非关键 Tool 跳过、状态持久化到数据库、WebSocket 实时推送
  - `models.py`：`Session` 增加 `agent_state` 字段，存储 Plan 执行进度
  - `main.py`：startup 注册 5 个 Tools，5 处 `background_tasks.add_task` 全部替换为 `orchestrator.submit_plan`
  - **向后兼容**：所有现有 REST API 和 WebSocket 消息格式不变，前端无需修改

---

### ⚡ Phase 2: 并发性能与工程化改造（已完成）

#### 已完成

- **数据库替换：SQLite + SQLAlchemy**
  - 新增 `db_models.py`：SQLAlchemy ORM 模型（`SessionModel` + `TherapistLogModel`），敏感字段加密存储
  - 新增 `database.py`：数据库初始化 + 自动 JSON-to-DB 迁移
  - `models.py`：`save()` / `load()` 改为 SQLite 优先，失败自动回退到本地 JSON
  - `main.py`：启动时调用 `setup_database()` 初始化表结构
  - 新增依赖：`sqlalchemy>=2.0.0`, `alembic>=1.13.0`

- **前端工程化：therapist.html 组件化拆分**
  - `therapist.html`：1709 行 → 471 行，删除全部内联脚本
  - 新增 `therapist.js`：ES Module 入口，绑定事件与初始化
  - 新增 `state.js`：全局状态管理
  - 新增 `components/session-list.js`：会话列表组件
  - 新增 `components/session-detail.js`：会话详情渲染
  - 新增 `components/log-viewer.js`：日志查看与流监控
  - 新增 `services/websocket.js`：WebSocket 连接与消息分发
  - 新增 `services/api.js`：REST API 封装
  - 新增 `utils/formatters.js`：时间/状态/日志格式化工具

- **FLUX 模型后台预热（分析阶段并行加载）**
  - `image_service.py`：新增 `warmup_with_image(image_path)` 方法，使用用户真实绘画替代 dummy 图像预热
  - `main.py`：`analyze_drawing_task_stream()` 开始时后台并发启动预热任务，利用 LLM 分析期间的 GPU 空闲窗口加载 FLUX 权重
  - 消除用户等待：用户回答完问题时模型已在显存，直接开始生成

- **流式输出节流优化**
  - `main.py`：流式推送阈值从每 5 字符提升到每 30 字符，减少前端卡顿和网络开销
  - `send_to_subject()` 增加同类型消息 200ms 节流
  - `_heartbeat_loop()`：补充 3 次无 pong 主动清理死连接

- **HTTPS 支持**
  - `main.py`：检测 `ENABLE_HTTPS=true`，自动加载 `SSL_CERT_FILE` / `SSL_KEY_FILE`
  - 证书缺失时自动回退到 HTTP 并打印警告
  - `README.md` 增加自签名证书生成命令

#### 待完成

- ~~[ ] 图像生成云端 Provider 适配（Replicate API fallback）~~ → **冻结**：本地 ComfyUI 生成作为核心壁垒与差异化优势，不降级到云端

---

### 🚨 Phase 1: 伦理合规与数据隔离止损（已完成）

#### 已完成

- **合规整改 — 删除全部临床诊断术语**
  - 重写 `DAPR_ANALYSIS_PROMPT.txt`（208行 → 约130行），删除抑郁症/焦虑症/PTSD典型特征、0-3评分系统、自伤/自杀风险评估、病理化解读表格
  - 重写 `README.md` 与 `DAPR-agent/README.md`，替换「心理分析」→「情绪探索」，「咨询师」→「观察伙伴」，添加系统免责声明
  - 简化 `llm_service.py` 中 `generate_final_report()` 的 prompt schema，从 8 层嵌套临床报告（40+字段）改为 3 个扁平字段：`summary` / `creative_insights` / `suggested_explorations`
  - 删除 `scoring_data` 中的「风险等级」字段
  - 简化 `_validate_final_report_contract` 与 `_normalize_final_report_result`，移除所有临床字段扁平化逻辑

- **Bug 修复 — 会话隔离（致命安全漏洞）**
  - 删除 `llm_service.py` 全局单例 `_llm_service` 与 `get_llm_service()`
  - `KimiService.__init__` 增加 `session_id` 参数，实现每会话独立实例
  - 新增 `create_llm_service(session_id)` 工厂函数
  - `main.py` 中 6 处调用全部改为按会话创建独立实例，彻底杜绝多用户间的对话历史泄漏

- **稳定性增强 — JSON 输出强制化**
  - `generate()` / `generate_stream()` 新增 `force_json` 参数，启用 `response_format={"type": "json_object"}`
  - 删除 `_request_json_repair` 与 `_request_final_report_repair` 方法（约 50 行死代码）
  - 简化 `_parse_analysis_response_with_contract` 与 `_parse_final_report_with_contract` 的重试逻辑

- **数据存储加密**
  - `models.py` 引入 `cryptography.fernet`，敏感字段（`user_answers`, `final_answers`, `webcam_video`, `screen_video`）自动加密
  - `db_models.py` 复用相同加密逻辑，SQLite 中敏感字段以 `enc:` 前缀存储
  - 加密密钥从环境变量 `DAPR_ENCRYPTION_KEY` 读取，未设置时保留明文回退（便于开发调试）

- **知情同意弹窗**
  - `index.html` / `app.js` 新增「知情同意」页面，用户必须勾选「我了解这只是一个艺术创作探索工具，不提供医疗或心理诊断」方可进入
  - 同意状态通过 `POST /api/session/{id}/consent` 持久化到数据库
  - 刷新页面后通过 `sessionStorage` 恢复同意状态，无需重复确认

#### 已完成

- **`app.js` 最终报告渲染去临床化**
  - 移除 `stress_level` / `coping_style` / `emotional_state` 临床三卡片
  - 移除 `deep_analysis` 深度心理分析区块（self_concept / interpersonal / stress_response / underlying_needs）
  - 移除 `recommendations` 专业建议、`follow_up` 后续关注要点等临床表述
  - 新增 `creative_insights` →「创作发现」、`suggested_explorations` →「建议探索方向」
  - 保留 `summary` → 创作回顾总结、`selection_interpretation` →「选择背后的感受」
  - 更新底部免责声明：删除「心理咨询师」提法，明确「不构成医疗或心理诊断」
  - 向后兼容：旧字段（`key_insights` / `recommendations` / `follow_up`）作为兜底显示

---

## [0.2.0] — 2025-03-14

### Added

- **Redis 会话持久化与 WebSocket 高可用**
  - `ConnectionManager` 将受试者消息写入 Redis，断线重连后可恢复上下文
  - 启动 ping/pong 心跳，超时自动清理死连接
  - 受试者/咨询师 WebSocket 实现指数退避重连策略（`WS_RECONNECT_BASE_MS` ~ `WS_RECONNECT_MAX_MS`）
  - 新增依赖 `redis>=5.0.0`

- **流式分析实时推送**
  - `analyze_drawing_task_stream()` 流式返回 LLM 生成内容，通过 WebSocket 实时推送给受试者界面
  - 咨询师面板支持流式分析日志的实时渲染（`analysis_stream_chunk` / `analysis_stream_complete`）

- **会话状态恢复**
  - 浏览器刷新（Ctrl+R）后自动检测未完成会话，通过 Redis 缓存恢复上下文和页面状态
  - `sessionStorage` 持久化 `dapr_session_id`

- **结构化输出契约与修复链路**
  - 新增 `_parse_analysis_response_with_contract`：严格 JSON 契约校验 + 有界修复重试
  - 新增 `_validate_analysis_contract` / `_validate_final_report_contract`：字段类型与层级校验
  - 新增 `_request_json_repair` / `_request_final_report_repair`：模型自修复兜底

### Fixed

- 分析结果到达后前端 UI 不更新的问题（WebSocket `questions` 消息处理）
- 浏览器刷新后会话丢失、需重新创建的问题

---

## [0.1.0] — 2025-03-13

### Added

- **MVP 完整流程跑通**
  - 受试者界面：引导 → 权限申请 → 绘画（Canvas + MediaRecorder） → 问答 → 图像选择 → 最终报告
  - 咨询师监控面板：实时 WebSocket 日志、会话列表、流式分析监控、历史会话导入
  - FastAPI 后端：REST API + WebSocket 双通道，`/api/session/*` 全生命周期管理
  - 本地文件存储：会话数据以 JSON 形式持久化到 `DAPR-agent/sessions/`

- **多模态分析**
  - 绘画成品图像分析（Kimi-K2.5 多模态）
  - 摄像头视频关键帧提取（ffmpeg `fps=0.5`，最多 150 帧）
  - 画布录制视频分析（`canvas.captureStream`）

- **图像生成**
  - ComfyUI 本地集成，`color_the_dapr_doodle_api.json` 工作流
  - FLUX.2 Klein 4B Distill 模型支持
  - 3 个固定艺术方向变体：温暖庇护 / 雨中希望 / 宁静平衡

- **选择行为追踪**
  - 记录查看顺序（`viewOrder`）、悬停时长、犹豫指标（`hesitationIndicators`）
  - 3 秒防误触机制（预览页按钮渐显）

---

## Roadmap — 重构计划概览

> 详见 [`REFACTOR_PLAN.md`](./REFACTOR_PLAN.md)（四阶段原始计划）  
> 详见 [`PHASE2_PLAN.md`](./PHASE2_PLAN.md)（Phase 2 务实版计划）  
> 详见 [`AGENT_PLAN.md`](./AGENT_PLAN.md)（Agent 架构务实版计划）

### Phase 1: 伦理合规与数据隔离（✅ 已完成）
- [x] Prompt 层去临床化
- [x] 修复单例会话语污染
- [x] `response_format` 强制 JSON
- [x] 本地 JSON / SQLite 加密存储
- [x] 知情同意弹窗
- [x] 前端报告界面去临床化渲染

### Phase 2: 工程化改造（✅ 核心已完成）
- [x] SQLite 数据库替换本地 JSON
- [x] therapist.html 组件化拆分（ES Module）
- [x] 流式输出节流（5字符 → 30字符）
- [x] HTTPS 自签名证书支持
- ~~[ ] 图像生成云端 Provider 适配（Replicate fallback）~~ → **冻结**：本地 ComfyUI 生成作为核心壁垒与差异化优势，不降级到云端
- **生产环境优化 — 图像分辨率降级**
  - 工作流 `color_the_dapr_doodle_api.json`：`ImageScaleToTotalPixels.megapixels` 从 `1.0` 降为 **`0.5`**
  - 生成分辨率从 ~100 万像素降至 ~50 万像素（估算 ~638×826）
  - 效果：RTX 5060 8GB 上 3 张图批量生成从 300s+OOM 优化到 **36s 全部成功**
  - 图像文件大小从 ~946KB 降至 ~400KB
- **环境配置固化与一键启动**
  - `requirements.txt`：所有依赖版本号完全固定（含精确版本 + CUDA 索引修正为 cu128）
  - `conda-environment.yml`：导出完整 conda 环境配置（channels + dependencies）
  - `start.sh`：一键启动脚本（检查环境 → 启动 ComfyUI → 等待就绪 → 启动后端）
  - `stop.sh`：一键停止脚本（清理 ComfyUI + 后端 + 临时文件）

### Agent 架构重构（✅ 核心已完成）
- [x] Tool Registry（`BaseTool` + `ToolWrapper`）
- [x] Plan Engine（`Plan` / `Step` / 4 个预定义模板）
- [x] Agent Orchestrator（顺序执行 + 重试 + 失败恢复 + 状态持久化）
- [x] `main.py` 去除所有 `background_tasks.add_task` 硬编码
- [ ] 前端 Stepper UI 执行状态可视化（待完成）
- [ ] 历史 Plan 重放 API（待完成）

### 冻结 / 大赛后扩展（不做）
- ReAct Loop（LLM 自主决策）：当前状态机已足够
- 语义记忆 / ChromaDB：SQLite + ConversationManager 已够用
- 情感向量 / ControlNet / 笔触轨迹：需要训练数据，时间不足

---

## 验收标准速查

| 维度 | 当前状态 | 目标 |
|------|----------|------|
| 合规安全 | ✅ 已完成 | 零临床术语、知情同意、数据加密 |
| 架构 Agentic | ✅ 已完成 | Tool + Plan + Orchestrator，失败可重试 |
| 会话隔离 | ✅ 已修复 | 多并发零污染 |
| 并发性能 | ✅ 已完成 | 异步批处理 + 并行轮询 + FP4 量化 |
| 前端工程 | ✅ 已完成 | ES Module 组件化，therapist.html < 500 行 |
| 数据持久化 | ✅ 已完成 | SQLite + 加密 + JSON 回退 |
| 核心壁垒 | ✅ 已完成 | 本地 ComfyUI + FP4 量化 + 后台预热，零成本、低延迟、隐私不外流 |

---

## 备注

- **版本 0.x 期间**：API 和 schema 可能在不升级主版本号的情况下发生破坏性变更
- **下一步优先级**：
  1. `app.js` 最终报告渲染去临床化（1 小时）
  2. ~~云端 Provider 适配~~ → **冻结**，本地 ComfyUI 生成作为差异化优势
  3. 前端 Stepper UI + 历史 Plan 重放（2-3 天，可选）
