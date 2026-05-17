"""
LLM 服务兼容包装层

保留此文件以确保现有导入继续工作：
  from llm_service import create_llm_service, KimiService
"""
from services.llm import KimiService, create_llm_service

__all__ = ["KimiService", "create_llm_service"]
