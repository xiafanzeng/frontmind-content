"""Private runtime credentials and task-scoped transport; never part of Job state.

Public workflow source contains no keys. Local operators may use environment
variables or private config files. FrontMind sandboxes receive only a loopback
gateway address; the host injects credentials outside the container.
"""
from __future__ import annotations

import functools
import json
import os
import urllib.request

PROXY_BASE = "http://127.0.0.1:8173/content-providers"
PROVIDERS = frozenset({"xty", "deepseek", "zhipu"})
PROXY_TOKEN = "frontmind-content-proxy"


def proxy_enabled() -> bool:
    value = os.environ.get("FRONTMIND_CONTENT_PROVIDER_PROXY", "")
    if value and value != PROXY_BASE:
        raise ValueError("Invalid content task gateway address")
    return bool(value)


@functools.lru_cache(maxsize=1)
def proxy_configuration() -> dict[str, bool]:
    if not proxy_enabled():
        return {}
    # Bypass HTTP_PROXY for the private loopback bridge. Never follow redirects.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(PROXY_BASE + "/status", timeout=10) as response:
        value = json.loads(response.read(16_384))
    providers = value.get("providers") if isinstance(value, dict) else None
    if not isinstance(providers, dict):
        raise ValueError("Invalid content task gateway status")
    return {name: providers.get(name) is True for name in PROVIDERS}


def runtime_credential(provider: str) -> tuple[str | None, str | None]:
    if provider not in PROVIDERS:
        raise ValueError("Unknown content provider")
    if proxy_enabled():
        configured = proxy_configuration().get(provider, False)
        return (PROXY_TOKEN if configured else ""), "private_task_gateway"
    name = "FRONTMIND_CONTENT_" + provider.upper() + "_API_KEY"
    value = os.environ.get(name, "").strip()
    return (value, name) if value else (None, None)


def transport_url(provider: str, original: str) -> str:
    if not proxy_enabled():
        return original
    if provider == "xty" and original == "https://api.xty.app/v1":
        return PROXY_BASE + "/xty/v1"
    if provider == "deepseek" and original == "https://api.deepseek.com/chat/completions":
        return PROXY_BASE + "/deepseek/chat/completions"
    if provider == "zhipu":
        for endpoint in ("web_search", "reader", "layout_parsing"):
            if original == "https://open.bigmodel.cn/api/paas/v4/" + endpoint:
                return PROXY_BASE + "/zhipu/" + endpoint
    raise ValueError("Content task gateway does not support this provider endpoint")
