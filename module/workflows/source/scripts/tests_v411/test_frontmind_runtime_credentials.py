"""Hosted integration tests; no real API calls or credentials."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared import runtime_credentials as credentials, model_runtime


class RuntimeCredentialsTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True); self.env.start()
        self.addCleanup(self.env.stop)
        credentials.proxy_configuration.cache_clear()
        self.addCleanup(credentials.proxy_configuration.cache_clear)

    def test_private_local_environment_without_changing_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root/'config').mkdir()
            config = root/'config/xty.json'; config.write_text('{"api_key":""}')
            before = config.read_bytes()
            self.assertFalse(model_runtime.load_configuration(root, 'xty', required=False)['configured'])
            with patch.dict(os.environ, {'FRONTMIND_CONTENT_XTY_API_KEY': 'synthetic-private-token'}):
                result = model_runtime.load_configuration(root, 'xty')
                self.assertTrue(result['configured'])
                self.assertEqual(result['api_key'], 'synthetic-private-token')
            self.assertEqual(config.read_bytes(), before)

    def test_gateway_reports_actual_configuration_without_exposing_key(self):
        with patch.dict(os.environ, {'FRONTMIND_CONTENT_PROVIDER_PROXY': credentials.PROXY_BASE}), patch.object(credentials, 'proxy_configuration', return_value={'xty': True, 'deepseek': False, 'zhipu': True}):
            self.assertEqual(credentials.runtime_credential('xty'), ('frontmind-content-proxy', 'private_task_gateway'))
            self.assertEqual(credentials.runtime_credential('deepseek'), ('', 'private_task_gateway'))
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(model_runtime.ProviderActionError):
                    model_runtime.load_configuration(Path(tmp), 'deepseek')

    def test_exact_routes_only_and_external_gateway_rejected(self):
        routes = {
            ('xty', 'https://api.xty.app/v1'): '/xty/v1',
            ('deepseek', 'https://api.deepseek.com/chat/completions'): '/deepseek/chat/completions',
            **{('zhipu', 'https://open.bigmodel.cn/api/paas/v4/'+name): '/zhipu/'+name for name in ('web_search','reader','layout_parsing')},
        }
        with patch.dict(os.environ, {'FRONTMIND_CONTENT_PROVIDER_PROXY': credentials.PROXY_BASE}):
            for (provider, source), destination in routes.items():
                self.assertEqual(credentials.transport_url(provider, source), credentials.PROXY_BASE+destination)
            with self.assertRaises(ValueError):
                credentials.transport_url('zhipu', 'https://open.bigmodel.cn/api/paas/v4/other')
        with patch.dict(os.environ, {'FRONTMIND_CONTENT_PROVIDER_PROXY': 'https://untrusted.invalid'}):
            with self.assertRaises(ValueError): credentials.runtime_credential('xty')
        self.assertEqual(credentials.transport_url('deepseek', 'https://api.deepseek.com/chat/completions'), 'https://api.deepseek.com/chat/completions')
