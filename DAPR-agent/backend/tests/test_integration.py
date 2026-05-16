"""
DAPR Agent 集成测试
覆盖 Phase 1 + Phase 2 + Agent 重构的全部历史变更
"""
import os
import sys
import json
import asyncio
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# 设置测试环境
os.environ["DAPR_ENCRYPTION_KEY"] = "h1prbCxioYeewc82T3u5xi4PJHwl8436FgvRoPxLXHs="
os.environ["DAPR_DB_PATH"] = ":memory:"

sys.path.insert(0, str(Path(__file__).parent.parent))

# pytest is optional, only needed for IDE test discovery
# import pytest

print("=" * 70)
print("DAPR Agent 集成测试")
print("=" * 70)
print()

passed = 0
failed = 0
errors = []


def test_section(name):
    """打印测试章节标题"""
    print(f"\n{'─' * 70}")
    print(f"▶ {name}")
    print("─" * 70)


def run_test(name, func):
    """运行单个测试并记录结果"""
    global passed, failed
    try:
        func()
        print(f"  ✅ {name}")
        passed += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        failed += 1
        errors.append((name, str(e)))


async def run_async_test(name, func):
    """运行异步测试"""
    global passed, failed
    try:
        await func()
        print(f"  ✅ {name}")
        passed += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        failed += 1
        errors.append((name, str(e)))


# ═══════════════════════════════════════════════════════════════════
# Test 1: 数据库模块
# ═══════════════════════════════════════════════════════════════════

def test_database_init():
    from db_models import init_db, get_engine, get_session_local, SessionModel
    init_db()
    db = get_session_local()()
    count = db.query(SessionModel).count()
    db.close()
    assert count == 0, "新数据库应为空"


def test_database_crud():
    from db_models import get_session_local, SessionModel, _encrypt_field, _decrypt_field
    db = get_session_local()()
    
    # Create
    row = SessionModel(id="test-001", status="guidance", age_group="青年")
    db.add(row)
    db.commit()
    
    # Read
    found = db.query(SessionModel).filter(SessionModel.id == "test-001").first()
    assert found is not None
    assert found.age_group == "青年"
    
    # Update
    found.status = "analyzing"
    db.commit()
    
    # Delete
    db.delete(found)
    db.commit()
    assert db.query(SessionModel).filter(SessionModel.id == "test-001").first() is None
    db.close()


def test_database_encryption():
    from db_models import _encrypt_field, _decrypt_field
    original = ["answer1", "answer2", "answer3"]
    encrypted = _encrypt_field(original)
    assert encrypted.startswith("enc:")
    decrypted = _decrypt_field(encrypted)
    assert decrypted == original


# ═══════════════════════════════════════════════════════════════════
# Test 2: models.py 数据库兼容层
# ═══════════════════════════════════════════════════════════════════

def test_session_save_load_db():
    from models import Session, SessionStatus
    from db_models import get_session_local, SessionModel
    
    session = Session()
    session.status = SessionStatus.ANALYZING
    session.age_group = "青年"
    session.user_answers = ["I feel calm", "The rain is heavy"]
    
    # Save to DB
    session.save()
    
    # Load from DB
    loaded = Session.load(session.id)
    assert loaded is not None
    assert loaded.status == SessionStatus.ANALYZING
    assert loaded.age_group == "青年"
    assert loaded.user_answers == ["I feel calm", "The rain is heavy"]


def test_session_json_fallback():
    """测试 JSON 回退机制"""
    from models import Session, SessionStatus
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        session = Session()
        session.status = SessionStatus.COMPLETED
        session.age_group = "老年"
        
        # 通过 fallback 保存到 JSON
        session._save_fallback(tmpdir)
        
        # 通过 fallback 从 JSON 加载
        loaded = Session._load_fallback(session.id, tmpdir)
        assert loaded is not None
        assert loaded.status == SessionStatus.COMPLETED
        assert loaded.age_group == "老年"


def test_session_agent_state():
    from models import Session
    session = Session()
    session.agent_state = {"plan": {"steps": []}, "progress": 0.5}
    assert session.agent_state["progress"] == 0.5


# ═══════════════════════════════════════════════════════════════════
# Test 3: Agent 模块
# ═══════════════════════════════════════════════════════════════════

async def test_tool_wrapper():
    from agent import ToolWrapper, ToolResult
    
    async def mock_success(session_id, **ctx):
        return {"result": "ok"}
    
    async def mock_fail(session_id, **ctx):
        raise TimeoutError("API timeout")
    
    tool_ok = ToolWrapper("MockSuccess", mock_success, max_retries=1)
    result = await tool_ok.execute("test-id", {})
    assert result.success is True
    
    tool_fail = ToolWrapper("MockFail", mock_fail, max_retries=1)
    result = await tool_fail.execute("test-id", {})
    assert result.success is False
    assert result.retryable is True


async def test_tool_retry():
    from agent import ToolWrapper
    
    call_count = 0
    async def flaky(session_id, **ctx):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("Transient error")
        return {"ok": True}
    
    tool = ToolWrapper("Flaky", flaky, max_retries=3)
    result = await tool.run_with_retry("test-id", {})
    assert result.success is True
    assert call_count == 3


async def test_plan_execution():
    from agent import AgentOrchestrator, ToolWrapper
    from agent.plan import Plan, Step
    
    results = []
    async def record_tool(session_id, **ctx):
        results.append(ctx.get("name"))
    
    orch = AgentOrchestrator()
    orch.register_tool(ToolWrapper("ToolA", record_tool))
    orch.register_tool(ToolWrapper("ToolB", record_tool))
    
    plan = Plan(session_id="test-plan", steps=[
        Step(tool_name="ToolA", input_context={"name": "step1"}),
        Step(tool_name="ToolB", input_context={"name": "step2"}),
    ])
    
    await orch.submit_plan("test-plan", plan)
    # 等待执行完成
    await asyncio.sleep(0.5)
    
    assert results == ["step1", "step2"], f"Expected ordered execution, got {results}"
    assert plan.is_complete is True


async def test_plan_failure_recovery():
    from agent import AgentOrchestrator, ToolWrapper
    from agent.plan import Plan, Step
    
    async def fail_tool(session_id, **ctx):
        raise Exception("Always fails")
    
    async def ok_tool(session_id, **ctx):
        return {"ok": True}
    
    orch = AgentOrchestrator()
    orch.register_tool(ToolWrapper("FailTool", fail_tool, max_retries=1))
    orch.register_tool(ToolWrapper("OkTool", ok_tool))
    
    plan = Plan(session_id="test-fail", steps=[
        Step(tool_name="FailTool"),  # 非关键 Tool，失败后跳过
        Step(tool_name="OkTool"),
    ])
    
    await orch.submit_plan("test-fail", plan)
    await asyncio.sleep(0.5)
    
    assert plan.steps[0].status.value == "failed"
    assert plan.steps[1].status.value == "completed"


async def test_plan_critical_failure():
    from agent import AgentOrchestrator, ToolWrapper
    from agent.plan import Plan, Step
    
    async def critical_fail(session_id, **ctx):
        raise Exception("Critical failure")
    
    orch = AgentOrchestrator()
    orch.register_tool(ToolWrapper("AnalyzeDrawingTool", critical_fail, max_retries=1))
    orch.register_tool(ToolWrapper("OtherTool", lambda s, **c: None))
    
    plan = Plan(session_id="test-critical", steps=[
        Step(tool_name="AnalyzeDrawingTool"),  # 关键 Tool
        Step(tool_name="OtherTool"),
    ])
    
    await orch.submit_plan("test-critical", plan)
    await asyncio.sleep(0.5)
    
    assert plan.steps[0].status.value == "failed"
    # 关键 Tool 失败后，后续步骤不会执行
    assert plan.steps[1].status.value == "pending"


# ═══════════════════════════════════════════════════════════════════
# Test 4: 图像服务（mock 测试）
# ═══════════════════════════════════════════════════════════════════

async def test_image_service_async():
    from aiohttp import web
    from image_service import ComfyUIService
    
    # Mock ComfyUI server
    async def mock_prompt(request):
        data = await request.json()
        return web.json_response({"prompt_id": "mock-prompt-123"})
    
    async def mock_history(request):
        prompt_id = request.match_info["prompt_id"]
        if prompt_id == "mock-prompt-123":
            return web.json_response({
                prompt_id: {
                    "outputs": {
                        "9": {"images": [{"filename": "test.png", "subfolder": ""}]}
                    }
                }
            })
        return web.json_response({})
    
    async def mock_view(request):
        return web.Response(body=b"PNG\x89fake", content_type="image/png")
    
    app = web.Application()
    app.router.add_post("/prompt", mock_prompt)
    app.router.add_get("/history/{prompt_id}", mock_history)
    app.router.add_get("/view", mock_view)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 18222)
    await site.start()
    
    try:
        service = ComfyUIService()
        service.server_address = "127.0.0.1:18222"
        service.timeout = 10
        
        # Test queue_prompt_async
        wf = service.modify_workflow("test.png", "a test prompt")
        result = await service.queue_prompt_async(wf)
        assert "prompt_id" in result
        
        # Test get_history_async
        history = await service.get_history_async("mock-prompt-123")
        assert "mock-prompt-123" in history
        
        # Test get_image_async
        img = await service.get_image_async("test.png")
        assert len(img) > 0
        
        await service.close()
    finally:
        await runner.cleanup()


# ═══════════════════════════════════════════════════════════════════
# Test 5: 导入验证
# ═══════════════════════════════════════════════════════════════════

def test_imports():
    """验证所有模块可正常导入"""
    modules = [
        "config",
        "models",
        "db_models",
        "database",
        "llm_service",
        "image_service",
        "agent",
        "agent.tools",
        "agent.plan",
        "agent.orchestrator",
    ]
    for mod in modules:
        __import__(mod)
        print(f"    import {mod} OK")


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

async def main():
    global passed, failed
    
    # ── 数据库 ──
    test_section("1. 数据库模块")
    run_test("数据库初始化", test_database_init)
    run_test("CRUD 操作", test_database_crud)
    run_test("字段加密解密", test_database_encryption)
    
    # ── models.py ──
    test_section("2. Session 数据库兼容层")
    run_test("save/load 数据库", test_session_save_load_db)
    run_test("JSON 回退机制", test_session_json_fallback)
    run_test("agent_state 字段", test_session_agent_state)
    
    # ── Agent ──
    test_section("3. Agent 模块")
    await run_async_test("ToolWrapper 包装", test_tool_wrapper)
    await run_async_test("Tool 重试机制", test_tool_retry)
    await run_async_test("Plan 顺序执行", test_plan_execution)
    await run_async_test("Plan 失败恢复", test_plan_failure_recovery)
    await run_async_test("Plan 关键失败终止", test_plan_critical_failure)
    
    # ── 图像服务 ──
    test_section("4. 图像服务 (async)")
    await run_async_test("异步 API 调用", test_image_service_async)
    
    # ── 导入 ──
    test_section("5. 模块导入验证")
    run_test("全部模块导入", test_imports)
    
    # ── 汇总 ──
    print("\n" + "=" * 70)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 70)
    
    if errors:
        print("\n失败详情:")
        for name, err in errors:
            print(f"  - {name}: {err}")
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
