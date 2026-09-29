"""Historical XTY routing for compatibility tests only; no production selection."""
from typing import Any
from shared.model_runtime import HOST_ACTIONS, GLM_ACTIONS, DEEPSEEK_ACTIONS, DEFAULT_TIMEOUT, ProviderActionError

def historical_profile(action: str) -> dict[str, Any]:
    if action in HOST_ACTIONS:
        return {"provider": "xty", "api_url": "https://codex-hk.xty.app/v1/responses",
            "wire_api": "responses", "model": "gpt-6-astra", "reasoning": {"effort": "high"},
            "max_output_tokens": 65536, "stream": True, "store": False,
            "include": ["reasoning.encrypted_content"], "timeout_seconds": DEFAULT_TIMEOUT}
    if action in DEEPSEEK_ACTIONS:
        return {"provider": "deepseek", "api_url": "https://api.deepseek.com/chat/completions", "model": "deepseek-v4-pro", "thinking": {"type": "enabled"}, "reasoning_effort": "max", "max_tokens": 65536, "stream": True, "response_format": {"type": "json_object"}, "timeout_seconds": DEFAULT_TIMEOUT}
    raise ProviderActionError("unsupported_action", "当前动作没有已批准的模型路由。", action=action)
