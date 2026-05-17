# Phase 2 重构计划（务实版）

> **编制日期**: 2026-05-15  
> **前置状态**: Phase 1 ✅ 已完成 | 图像并行化 ✅ 已提前完成  
> **目标**: 从「可用 demo」升级为「可演示产品」

---

## 一、现状评估

### 1.1 已完成工作

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 1 | 伦理合规、数据加密、知情同意、会话隔离 | ✅ 已完成 |
| Phase 3（提前） | 图像生成异步化、FP4量化、批量提交、并行轮询、模型预热 | ✅ 已完成 |

### 1.2 当前技术债务

| 问题 | 影响 | 优先级 |
|------|------|--------|
| 本地 JSON 文件存储 | 并发写入冲突、查询慢、无事务 | 🔴 高 |
| therapist.html 单文件 1700+ 行 | 维护困难、无法复用组件 | 🟡 中 |
| 流式分析每 5 字符推送 | 前端卡顿、网络开销大 | 🟡 中 |
| 无 HTTPS 支持 | 摄像头权限受限（非 localhost） | 🟡 中 |
| 硬编码后台任务 | 无法优雅处理失败重试 | 🟢 低 |

### 1.3 不做的事（明确边界）

- ❌ **ReAct Agent 重构**: 工作量大、风险高，当前状态机已够用
- ❌ **语义记忆/ChromaDB**: 过度工程，当前 ConversationManager 足够
- ❌ **情感向量/ControlNet**: 需要训练数据，大赛时间不足
- ❌ **笔触轨迹记录**: 前端改动大，收益不明确

---

## 二、Phase 2 任务清单

### Task 1: SQLite 替换本地 JSON（Week 1）

**目标**: 解决并发安全、支持查询、建立数据关系。

**新增文件**:
```
DAPR-agent/backend/database.py      # SQLAlchemy 初始化 + ORM 模型
DAPR-agent/backend/db_models.py     # Session ORM + Message ORM
```

**修改文件**:
| 文件 | 变更 |
|------|------|
| `models.py` | `Session.save()` → `db_session.commit()`；`Session.load()` → `db_session.query()` |
| `main.py` | `@app.on_event("startup")` 增加 `init_db()`；所有 `session.save()` 改为数据库写入 |
| `requirements.txt` | +`sqlalchemy>=2.0.0`, +`alembic>=1.13.0` |

**验收标准**:
- [ ] 100 个并发会话创建不丢失数据
- [ ] 历史会话列表查询 < 100ms
- [ ] 数据库文件自动迁移（alembic）

---

### Task 2: therapist.html 组件化拆分（Week 1-2）

**目标**: 从 1700 行单文件拆分为可维护的模块。

**新增目录结构**:
```
DAPR-agent/static/
├── components/
│   ├── SessionList.js       # 会话列表组件
│   ├── LogViewer.js         # 日志查看组件
│   ├── SessionDetail.js     # 会话详情渲染
│   └── StreamMonitor.js     # 实时流监控
├── services/
│   ├── api.js               # REST API 封装
│   └── websocket.js         # WebSocket 管理
├── utils/
│   └── formatters.js        # 时间/状态格式化
└── therapist.js             # 入口文件（原 therapist.html 内联脚本）
```

**修改文件**:
| 文件 | 变更 |
|------|------|
| `therapist.html` | 删除全部 `<script>`，引入 `<script src="/static/therapist.js">` |
| `app.py` (或新增) | 可选：如果引入 Vite 构建，需要配置静态文件路由 |

**验收标准**:
- [ ] therapist.html < 200 行
- [ ] 每个组件文件 < 300 行
- [ ] 功能与拆分前完全一致

> **简化策略**: 不引入 Vite/Webpack，直接用原生 ES Module (`type="module"`) 导入。避免构建工具链复杂度。

---

### Task 3: 流式输出节流优化（Week 2）

**目标**: 减少前端卡顿和网络开销。

**修改文件**:
| 文件 | 变更 |
|------|------|
| `main.py:538` | `token_count - last_update >= 5` → `>= 30`（每 30 字符推送一次） |
| `main.py:224-238` | `send_to_subject()` 增加节流：同类型消息 200ms 内不重复推送 |
| `main.py:252-273` | `_heartbeat_loop()` 补充：3 次无 pong 主动清理死连接 |

**验收标准**:
- [ ] 流式分析期间浏览器不卡顿
- [ ] 网络请求数减少 50%+

---

### Task 4: HTTPS 支持（Week 2）

**目标**: 非 localhost 环境可获取摄像头权限。

**新增文件**:
```
DAPR-agent/backend/cert/.gitkeep     # 证书目录占位
```

**修改文件**:
| 文件 | 变更 |
|------|------|
| `main.py:1237-1238` | 检测 `ENABLE_HTTPS=true`，加载 `cert.pem`/`key.pem` |
| `README.md` | 增加自签名证书生成命令 |

**验收标准**:
- [ ] `https://localhost:8000` 可正常访问
- [ ] 摄像头权限弹窗正常出现

---

### Task 5: 图像生成云端 Provider 适配（~~Week 2-3，保底方案~~ → **冻结**）

**决策**: 本地 ComfyUI 生成作为核心壁垒与差异化优势，不执行云端降级。本地推理零成本、低延迟、绘画数据隐私不外流，是产品核心卖点。

**说明**: 以下设计文档保留供未来扩展参考，但大赛前不实现。

~~**新增文件**~~:
```
DAPR-agent/backend/image_providers/
├── __init__.py
├── base.py                  # ImageProvider 抽象基类
├── comfyui_local.py         # 本地 ComfyUI（当前逻辑）
└── replicate_provider.py    # Replicate API fallback
```

~~**修改文件**~~:
| 文件 | 变更 |
|------|------|
| ~~`image_service.py`~~ | ~~`ComfyUIService` 改为 `ImageGenerationService`~~ |
| ~~`config.py`~~ | ~~`COMFYUI_CONFIG` → `IMAGE_GEN_CONFIG`~~ |
| ~~`requirements.txt`~~ | ~~+`replicate>=0.20.0`~~ |

---

## 三、排期与里程碑

```
Week 1 (5/15-5/22):
  ├─ Task 1: SQLite 数据库替换
  └─ Task 2: therapist.html 组件化拆分（前半）

Week 2 (5/22-5/29):
  ├─ Task 2: therapist.html 组件化拆分（后半）
  ├─ Task 3: 流式输出节流
  └─ Task 4: HTTPS 支持

Week 3 (5/29-6/05):
  └─ ~~Task 5: 云端 Provider 适配~~ → **冻结，本地 ComfyUI 作为核心优势**
```

**最终交付物**:
- 数据库持久化 + 查询
- 前端组件化
- 流式优化
- HTTPS
- ~~云端 fallback~~ → **冻结，本地 ComfyUI 作为核心优势**

---

## 四、不做的事（Phase 3/4 冻结）

以下内容大赛前不执行，但保留设计文档供未来扩展：

| 内容 | 原因 |
|------|------|
| ReAct Agent | 当前状态机足够，重构风险高 |
| 语义记忆/ChromaDB | SQLite + 简单查询已够用 |
| 情感向量/ControlNet | 需要训练数据，时间不足 |
| 笔触轨迹记录 | 前端改动大，收益不明确 |
| 多模态视频分析 | 当前 LLM 视频理解已可用 |

---

*文档版本: 1.0*  
*最后更新: 2026-05-15*
