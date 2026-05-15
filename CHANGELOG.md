# Changelog

> 本日志遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范。  
> 版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)（当前处于 0.x 快速迭代期）。

---

## [Unreleased] — 重构进行中

### 🚨 Phase 1: 伦理合规与数据隔离止损（进行中）

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

#### 待完成

- [ ] `models.py` 本地 JSON 存储加密（`cryptography.fernet`）
- [ ] `index.html` 知情同意弹窗（用户须勾选「不提供医疗诊断」方可进入）
- [ ] `therapist.html` 最终分析区块去临床化渲染（当前仍渲染 `stress_level` / `coping_style` 等旧字段）

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

> 详见 [`REFACTOR_PLAN.md`](./REFACTOR_PLAN.md)（精确到行号的四阶段重构计划）

### Phase 1: 伦理合规与数据隔离（Week 1-2）
- [x] Prompt 层去临床化
- [x] 修复单例会话语污染
- [x] `response_format` 强制 JSON
- [ ] 本地 JSON 加密存储
- [ ] 知情同意弹窗
- [ ] 前端报告界面去临床化渲染

### Phase 2: Agent 架构重构（Week 3-6）
- [ ] 硬编码状态机 → ReAct + Function Calling
- [ ] 新增 `agent_core.py`（ReActLoop + ToolRegistry + SessionAgent）
- [ ] 新增 `tools.py`（AnalyzeDrawingTool / GenerateImageTool / FinalizeTool / EscalateTool）
- [ ] 新增 `memory.py`（语义记忆 + ChromaDB 向量检索，替换截断式 ConversationManager）
- [ ] `Session` 增加 `agent_state` 字段，状态机不再驱动业务逻辑

### Phase 3: 并发性能与工程化（Week 5-8）
- [ ] `image_service.py` 全面异步化（urllib → aiohttp）
- [ ] 图像生成串行 → `asyncio.gather` 并行（目标 <15s）
- [ ] 本地 JSON → SQLAlchemy + SQLite/PostgreSQL
- [ ] 前端工程化：拆分 `therapist.html` 为 Vite 组件化项目
- [ ] HTTPS 自签名证书支持
- [ ] WebSocket 流式输出节流（5字符 → 50字符/300ms）

### Phase 4: 情感图像生成核心能力（Week 7-10）
- [ ] 新增 `emotion_embedding.py`（CLIP + sentence-transformers + PAD 情感向量）
- [ ] ComfyUI 工作流支持情感条件注入
- [ ] 新增 `stroke_processor.py`（笔触轨迹 → ControlNet 条件图）
- [ ] 新增 `feedback_loop.py`（用户点赞/点踩 → 情感向量迭代优化）
- [ ] 云端推理 provider 抽象（Replicate / RunPod / fal.ai，脱离本地 GPU 依赖）

---

## 验收标准速查

| 维度 | 当前状态 | 目标 |
|------|----------|------|
| 合规安全 | ⚠️ 部分完成 | 零临床术语、知情同意、数据加密 |
| 架构 Agentic | ❌ 硬编码状态机 | ReAct + Function Calling |
| 会话隔离 | ✅ 已修复 | 多并发零污染 |
| 并发性能 | ❌ 串行生成 | 3图并行 <15s |
| 前端工程 | ❌ 1700行内联HTML | Vite + 组件化 |
| 核心壁垒 | ❌ 仅调用 ComfyUI | 情感条件扩散 + 笔触 ControlNet |

---

## 备注

- **版本 0.x 期间**：API 和 schema 可能在不升级主版本号的情况下发生破坏性变更
- **大赛截止建议**：若资源极度有限，优先完成 Phase 1 全部 + Phase 3 数据库替换 + Phase 4 云端 provider，即可拿出「能用的产品」
