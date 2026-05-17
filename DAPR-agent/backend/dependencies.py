"""
共享依赖模块
解决 main.py 与 routers 之间的循环导入问题
"""
import os
import json
import asyncio
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import WebSocket
from redis.asyncio import Redis

from models import TherapistLog
from agent import AgentOrchestrator
from agent.interview_agent import InterviewAgent


class ConnectionManager:
    """连接管理器"""

    def __init__(self):
        # 受试者连接
        self.subject_connections: dict[str, WebSocket] = {}
        # 咨询师连接
        self.therapist_connections: dict[str, WebSocket] = {}
        # 心跳时间戳
        self.subject_last_pong: dict[str, float] = {}
        self.therapist_last_pong: dict[str, float] = {}
        # Redis
        self.redis: Optional[Redis] = None
        self.redis_enabled = False
        self.redis_prefix = os.environ.get("WS_REDIS_PREFIX", "dapr:ws")
        self.session_ttl_seconds = int(os.environ.get("WS_SESSION_TTL_SECONDS", "86400"))
        self.max_cached_events = int(os.environ.get("WS_MAX_CACHED_EVENTS", "50"))
        self.redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        # 心跳配置
        self.heartbeat_interval = int(os.environ.get("WS_HEARTBEAT_INTERVAL", "15"))
        self.heartbeat_task: Optional[asyncio.Task] = None

    async def init_redis(self):
        """初始化 Redis 连接"""
        try:
            self.redis = Redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
            await self.redis.ping()
            self.redis_enabled = True
            print(f"[WebSocket] Redis 已连接: {self.redis_url}")
        except Exception as e:
            self.redis_enabled = False
            self.redis = None
            print(f"[WebSocket] Redis 连接失败，将无法恢复上下文: {e}")

    async def close_redis(self):
        """关闭 Redis 连接"""
        if self.redis:
            await self.redis.aclose()
            self.redis = None
            self.redis_enabled = False

    async def start(self):
        """启动连接管理器后台任务"""
        await self.init_redis()
        if self.heartbeat_task is None or self.heartbeat_task.done():
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop(self):
        """停止连接管理器后台任务"""
        if self.heartbeat_task and not self.heartbeat_task.done():
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass
        self.heartbeat_task = None
        await self.close_redis()

    def _subject_latest_key(self, session_id: str) -> str:
        return f"{self.redis_prefix}:subject:{session_id}:latest"

    def _subject_events_key(self, session_id: str) -> str:
        return f"{self.redis_prefix}:subject:{session_id}:events"

    # 不缓存这些瞬态流式消息，避免填满队列并干扰恢复
    _NON_CACHEABLE = frozenset({"ping", "connection_status"})
    # analysis_stream 只缓存 started/complete，跳过 chunk
    _STREAM_SKIP_STATUSES = frozenset({"chunk"})

    async def _cache_subject_message(self, session_id: str, message: dict):
        """缓存发给受试者的消息，用于断线重连恢复"""
        if not self.redis_enabled or not self.redis:
            return

        msg_type = message.get("type", "unknown")

        # 跳过不需要恢复的消息类型
        if msg_type in self._NON_CACHEABLE:
            return

        # analysis_stream chunk 数量极大，不缓存，只缓存 started/complete
        if msg_type == "analysis_stream":
            status = (message.get("data") or {}).get("status", "")
            if status in self._STREAM_SKIP_STATUSES:
                return

        payload = json.dumps({
            "stored_at": datetime.now().isoformat(),
            "message": message
        }, ensure_ascii=False)

        latest_key = self._subject_latest_key(session_id)
        events_key = self._subject_events_key(session_id)

        try:
            # 使用事务流水线保证写入顺序
            async with self.redis.pipeline(transaction=True) as pipe:
                pipe.hset(latest_key, message.get("type", "unknown"), payload)
                pipe.expire(latest_key, self.session_ttl_seconds)
                pipe.lpush(events_key, payload)
                pipe.ltrim(events_key, 0, self.max_cached_events - 1)
                pipe.expire(events_key, self.session_ttl_seconds)
                await pipe.execute()
        except Exception as e:
            print(f"[WebSocket] 缓存会话上下文失败: session={session_id[:8]}..., err={e}")

    async def _load_subject_context(self, session_id: str) -> list[dict]:
        """读取受试者最近消息，用于重连恢复"""
        if not self.redis_enabled or not self.redis:
            return []

        events_key = self._subject_events_key(session_id)
        try:
            raw_events = await self.redis.lrange(events_key, 0, self.max_cached_events - 1)
            # LPUSH 导致顺序为新->旧，恢复时反转为旧->新
            restored_messages = []
            for item in reversed(raw_events):
                try:
                    parsed = json.loads(item)
                    msg = parsed.get("message")
                    if isinstance(msg, dict):
                        restored_messages.append(msg)
                except json.JSONDecodeError:
                    continue
            return restored_messages
        except Exception as e:
            print(f"[WebSocket] 读取会话上下文失败: session={session_id[:8]}..., err={e}")
            return []

    async def connect_subject(self, session_id: str, websocket: WebSocket):
        await websocket.accept()

        # 若同一会话已有旧连接，先关闭旧连接
        old_ws = self.subject_connections.get(session_id)
        if old_ws:
            try:
                await old_ws.close(code=1000)
            except Exception:
                pass

        self.subject_connections[session_id] = websocket
        self.subject_last_pong[session_id] = time.time()

        # 通知连接建立并尝试恢复上下文
        await websocket.send_json({
            "type": "connection_status",
            "data": {"status": "connected", "session_id": session_id}
        })

        context_messages = await self._load_subject_context(session_id)
        if context_messages:
            await websocket.send_json({
                "type": "restore_context",
                "data": {
                    "session_id": session_id,
                    "messages": context_messages
                }
            })

    async def connect_therapist(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self.therapist_connections[client_id] = websocket
        self.therapist_last_pong[client_id] = time.time()

    def disconnect_subject(self, session_id: str):
        if session_id in self.subject_connections:
            del self.subject_connections[session_id]
        self.subject_last_pong.pop(session_id, None)

    def disconnect_therapist(self, client_id: str):
        if client_id in self.therapist_connections:
            del self.therapist_connections[client_id]
        self.therapist_last_pong.pop(client_id, None)

    def mark_subject_pong(self, session_id: str):
        self.subject_last_pong[session_id] = time.time()

    def mark_therapist_pong(self, client_id: str):
        self.therapist_last_pong[client_id] = time.time()

    async def send_to_subject(self, session_id: str, message: dict):
        # 附加消息ID用于前端去重
        payload = dict(message)
        payload.setdefault("_message_id", uuid.uuid4().hex)
        payload.setdefault("_sent_at", datetime.now().isoformat())

        # 无论当前是否在线都先缓存，确保重连可恢复
        await self._cache_subject_message(session_id, payload)

        if session_id in self.subject_connections:
            try:
                ws = self.subject_connections[session_id]
                await ws.send_json(payload)
            except Exception:
                self.disconnect_subject(session_id)

    async def send_to_therapist(self, message: dict):
        """发送给所有咨询师"""
        disconnected = []
        for client_id, ws in self.therapist_connections.items():
            try:
                await ws.send_json(message)
            except:
                disconnected.append(client_id)

        # 清理断开的连接
        for client_id in disconnected:
            self.disconnect_therapist(client_id)

    async def _heartbeat_loop(self):
        """服务端心跳循环：发送 ping 并清理超时连接"""
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval)
                ping_message = {"type": "ping", "data": {"ts": datetime.now().isoformat()}}
                now = time.time()

                # 清理超时受试者连接（3次心跳无pong）
                timeout_threshold = self.heartbeat_interval * 3
                for session_id, ws in list(self.subject_connections.items()):
                    try:
                        last_pong = self.subject_last_pong.get(session_id, 0)
                        if now - last_pong > timeout_threshold:
                            try:
                                await ws.close(code=1001)
                            except Exception:
                                pass
                            self.disconnect_subject(session_id)
                            continue
                        await ws.send_json(ping_message)
                    except Exception:
                        self.disconnect_subject(session_id)

                # 清理超时咨询师连接
                for client_id, ws in list(self.therapist_connections.items()):
                    try:
                        last_pong = self.therapist_last_pong.get(client_id, 0)
                        if now - last_pong > timeout_threshold:
                            try:
                                await ws.close(code=1001)
                            except Exception:
                                pass
                            self.disconnect_therapist(client_id)
                            continue
                        await ws.send_json(ping_message)
                    except Exception:
                        self.disconnect_therapist(client_id)
        except asyncio.CancelledError:
            pass

    async def broadcast_log(self, log: TherapistLog):
        """广播日志给所有咨询师"""
        await self.send_to_therapist({
            "type": "log",
            "data": {
                "timestamp": log.timestamp,
                "session_id": log.session_id,
                "stage": log.stage,
                "llm_input": log.llm_input,
                "llm_output": log.llm_output,
                "flux2_input": log.flux2_input,
                "flux2_output": log.flux2_output,
            }
        })


manager = ConnectionManager()

# Agent Orchestrator（全局单例）
orchestrator = AgentOrchestrator()

# InterviewAgent 注册表（session_id -> InterviewAgent）
interview_agents: dict[str, InterviewAgent] = {}


def log_to_therapist(log: TherapistLog):
    """异步发送日志给咨询师"""
    print(f"[Log] 广播日志: stage={log.stage}, session={log.session_id[:8]}...")
    asyncio.create_task(manager.broadcast_log(log))
