"""
Re-export từ shared.abstractions.llm để đảm bảo tính nhất quán trên toàn hệ thống
và giữ tương thích ngược (backward compatibility) cho các file cũ.
"""
from shared.abstractions.llm import BaseLLM as LLM, LLMRequest, LLMResponse, BaseLLM

__all__ = ["LLM", "BaseLLM", "LLMRequest", "LLMResponse"]