"""Offline regressions for public URL validation in a network-disabled sandbox.

All DNS, sockets, CONNECTs and Reader responses are mocked. These tests make no
provider requests and use only temporary synthetic acquisition stores.
"""
from __future__ import annotations

from contextlib import ExitStack
import http.client
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import Mock, call, patch
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared import example_acquisition as acquisition
from shared import runtime_credentials as credentials


PUBLIC = "https://source.example.invalid/article"
OTHER_PUBLIC = "https://final.example.invalid/full-text"
TRUSTED_ENV = {
    "FRONTMIND_CONTENT_PROVIDER_PROXY": credentials.PROXY_BASE,
    "HTTP_PROXY": credentials.WEB_PROXY,
    "HTTPS_PROXY": credentials.WEB_PROXY,
    "http_proxy": credentials.WEB_PROXY,
    "https_proxy": credentials.WEB_PROXY,
    "NO_PROXY": "localhost,127.0.0.1",
}


def addresses(*values):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (value, 443)) for value in values]


class SandboxPublicWebTests(unittest.TestCase):
    def setUp(self):
        self.guards = ExitStack()
        self.addCleanup(self.guards.close)
        self.guards.enter_context(patch.dict(os.environ, TRUSTED_ENV, clear=True))
        self.dns = self.guards.enter_context(patch.object(
            socket, "getaddrinfo", side_effect=AssertionError("Unexpected real target DNS")))
        self.guards.enter_context(patch.object(
            socket, "socket", side_effect=AssertionError("Unexpected real socket")))
        self.guards.enter_context(patch.object(
            socket, "create_connection", side_effect=AssertionError("Unexpected real connection")))
        self.guards.enter_context(patch(
            "urllib.request.urlopen", side_effect=AssertionError("Unexpected real HTTP request")))
        self.connection_type = self.guards.enter_context(patch.object(
            http.client, "HTTPConnection", autospec=True))
        self.connection = self.connection_type.return_value

    def test_trusted_connect_accepts_public_https_without_target_dns_or_http_body(self):
        self.assertEqual(acquisition.public_url(PUBLIC), PUBLIC)
        self.connection_type.assert_called_once_with("127.0.0.1", 8173, timeout=10)
        self.connection.set_tunnel.assert_called_once_with("source.example.invalid", 443)
        self.connection.connect.assert_called_once_with()
        self.connection.close.assert_called_once_with()
        self.connection.request.assert_not_called()
        self.connection.send.assert_not_called()
        self.dns.assert_not_called()

    def test_trusted_connect_uses_http_destination_port(self):
        target = "http://source.example.invalid/article"
        self.assertTrue(credentials.validate_public_destination(target))
        self.connection.set_tunnel.assert_called_once_with("source.example.invalid", 80)
        self.dns.assert_not_called()

    def test_connect_denial_timeout_and_disconnect_fail_closed_and_close_connection(self):
        for error in (OSError("Tunnel connection failed: 403 Forbidden"),
                      TimeoutError("synthetic CONNECT timeout"),
                      http.client.RemoteDisconnected("synthetic proxy disconnect")):
            with self.subTest(error=type(error).__name__):
                self.connection.reset_mock()
                self.connection.connect.side_effect = error
                with self.assertRaises(acquisition.AcquisitionError):
                    acquisition.public_url(PUBLIC)
                self.connection.close.assert_called_once_with()
        self.dns.assert_not_called()

    def test_invalid_gateway_does_not_fall_back_to_dns(self):
        with patch.dict(os.environ, {"FRONTMIND_CONTENT_PROVIDER_PROXY": "http://127.0.0.1:8173/untrusted"}):
            with self.assertRaises(acquisition.AcquisitionError):
                acquisition.public_url(PUBLIC)
        self.connection_type.assert_not_called()
        self.dns.assert_not_called()

    def test_incomplete_or_untrusted_effective_proxy_is_rejected(self):
        for changes in ({"HTTP_PROXY": "", "http_proxy": ""},
                        {"HTTPS_PROXY": "", "https_proxy": ""},
                        {"HTTP_PROXY": "http://untrusted.invalid:8173", "http_proxy": "http://untrusted.invalid:8173"},
                        {"HTTPS_PROXY": "http://untrusted.invalid:8173", "https_proxy": "http://untrusted.invalid:8173"}):
            with self.subTest(changes=changes), patch.dict(os.environ, changes):
                with self.assertRaises(acquisition.AcquisitionError):
                    acquisition.public_url(PUBLIC)
        self.connection_type.assert_not_called()
        self.dns.assert_not_called()

    def test_conflicting_proxy_environment_cannot_be_hidden_by_lowercase_precedence(self):
        for changes in ({"HTTP_PROXY": "http://untrusted.invalid:8173"},
                        {"HTTPS_PROXY": "http://untrusted.invalid:8173"},
                        {"ALL_PROXY": "http://untrusted.invalid:8173"},
                        {"all_proxy": "http://untrusted.invalid:8173"}):
            with self.subTest(changes=changes), patch.dict(os.environ, changes):
                with self.assertRaises(acquisition.AcquisitionError):
                    acquisition.public_url(PUBLIC)
        self.connection_type.assert_not_called()
        self.dns.assert_not_called()

    def test_no_proxy_wildcard_hostname_suffix_and_explicit_port_cannot_bypass(self):
        cases = [("NO_PROXY", "*", PUBLIC),
                 ("NO_PROXY", "source.example.invalid", PUBLIC),
                 ("NO_PROXY", ".example.invalid", PUBLIC),
                 ("no_proxy", "source.example.invalid", PUBLIC),
                 ("NO_PROXY", "source.example.invalid:443", "https://source.example.invalid:443/article")]
        for key, value, target in cases:
            with self.subTest(key=key, value=value), patch.dict(os.environ, {key: value}):
                with self.assertRaises(acquisition.AcquisitionError):
                    acquisition.public_url(target)
        self.connection_type.assert_not_called()
        self.dns.assert_not_called()

    def test_unrelated_no_proxy_entries_do_not_disable_public_validation(self):
        with patch.dict(os.environ, {"NO_PROXY": "localhost,127.0.0.1,unrelated.invalid"}):
            self.assertEqual(acquisition.public_url(PUBLIC), PUBLIC)
        self.connection.connect.assert_called_once_with()

    def test_non_proxy_helper_returns_false_without_network(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(credentials.validate_public_destination(PUBLIC))
        self.connection_type.assert_not_called()
        self.dns.assert_not_called()

    def test_local_execution_retains_public_dns_validation(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
                socket, "getaddrinfo", return_value=addresses("93.184.216.34")) as dns:
            self.assertEqual(acquisition.public_url(PUBLIC), PUBLIC)
        dns.assert_called_once_with("source.example.invalid", 443)
        self.connection_type.assert_not_called()

    def test_local_execution_rejects_mixed_public_and_private_dns(self):
        for result in (addresses("93.184.216.34", "10.0.0.7"),
                       addresses("127.0.0.1", "93.184.216.34")):
            with self.subTest(result=result), patch.dict(os.environ, {}, clear=True), patch.object(
                    socket, "getaddrinfo", return_value=result):
                with self.assertRaises(acquisition.AcquisitionError):
                    acquisition.public_url(PUBLIC)
        self.connection_type.assert_not_called()

    def test_local_dns_failure_is_explicit(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
                socket, "getaddrinfo", side_effect=socket.gaierror("synthetic DNS failure")):
            with self.assertRaisesRegex(acquisition.AcquisitionError, "hostname could not be resolved"):
                acquisition.public_url(PUBLIC)
        self.connection_type.assert_not_called()

    def test_syntax_credentials_ports_and_control_characters_are_rejected_before_connect(self):
        targets = ["file:///etc/passwd", "ftp://source.example.invalid/file", "https:///missing-host",
                   "https://user:password@source.example.invalid/", "https://@source.example.invalid/",
                   "https://source.example.invalid:22/", "https://source.example.invalid:invalid/",
                   "https://[invalid/", "https://source.example.invalid/\r\nInjected: yes",
                   "https://source.example.invalid/\tfragment"]
        for target in targets:
            with self.subTest(target=target), self.assertRaises(acquisition.AcquisitionError):
                acquisition.public_url(target)
        self.connection_type.assert_not_called()
        self.dns.assert_not_called()

    def test_private_ip_literals_are_rejected_without_connect_or_dns(self):
        for target in ("http://127.0.0.1/", "http://10.0.0.1/", "http://169.254.169.254/",
                       "http://0.0.0.0/", "https://[::1]/", "https://[::ffff:127.0.0.1]/"):
            with self.subTest(target=target), self.assertRaises(acquisition.AcquisitionError):
                acquisition.public_url(target)
        self.connection_type.assert_not_called()
        self.dns.assert_not_called()

    def test_trusted_egress_denial_rejects_frontmind_and_local_hostnames(self):
        self.connection.connect.side_effect = OSError("Tunnel connection failed: 403 Forbidden")
        targets = ["https://dashboard.frontmind.cn/", "https://other.frontmind.net./",
                   "https://CONTENT.FrontMind.CN./", "http://localhost/", "http://host.local/",
                   "http://host.internal/"]
        for target in targets:
            with self.subTest(target=target), self.assertRaises(acquisition.AcquisitionError):
                acquisition.public_url(target)
        self.dns.assert_not_called()

    def test_redirect_revalidates_public_target_through_trusted_proxy(self):
        redirect = acquisition.SafeRedirect().redirect_request(
            Request(PUBLIC), None, 302, "Found", {}, OTHER_PUBLIC)
        self.assertEqual(redirect.full_url, OTHER_PUBLIC)
        self.connection.set_tunnel.assert_called_once_with("final.example.invalid", 443)
        self.dns.assert_not_called()

    def test_redirect_rejects_private_target_before_fetch(self):
        with self.assertRaises(acquisition.AcquisitionError):
            acquisition.SafeRedirect().redirect_request(
                Request(PUBLIC), None, 302, "Found", {}, "http://127.0.0.1/private")
        self.connection_type.assert_not_called()
        self.dns.assert_not_called()

    def test_http_acquisition_revalidates_final_url(self):
        response = Mock()
        response.read.return_value = b"<article>Synthetic public test article.</article>"
        response.status = 200
        response.geturl.return_value = "http://127.0.0.1/private"
        response.headers = {"Content-Type": "text/html; charset=utf-8"}
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with tempfile.TemporaryDirectory() as temporary, patch.object(
                acquisition, "build_opener", return_value=opener):
            store = acquisition.ExampleStore(temporary)
            with self.assertRaises(acquisition.AcquisitionError):
                store.acquire_http(PUBLIC)
            self.assertEqual(list(store.root.iterdir()), [])
        opener.open.assert_called_once()
        self.dns.assert_not_called()

    def test_reader_validates_initial_and_final_url_without_local_dns(self):
        api = Mock(return_value={"reader_result": {
            "content": "Synthetic complete public article for an offline regression.",
            "title": "Synthetic article", "url": OTHER_PUBLIC,
        }})
        with tempfile.TemporaryDirectory() as temporary:
            record = acquisition.ExampleStore(temporary).acquire_reader(PUBLIC, api)
        self.assertEqual(record["obtained_via"], "zhipu_reader")
        self.assertEqual(record["final_url"], OTHER_PUBLIC)
        api.assert_called_once_with("reader", {
            "url": PUBLIC, "return_format": "markdown", "retain_images": False,
            "with_links_summary": False, "with_images_summary": False,
        })
        self.assertEqual(self.connection.set_tunnel.call_args_list, [
            call("source.example.invalid", 443), call("final.example.invalid", 443)])
        self.connection.request.assert_not_called()
        self.dns.assert_not_called()

    def test_reader_rejects_private_final_url_without_saving_provenance(self):
        api = Mock(return_value={"reader_result": {
            "content": "Synthetic content", "url": "http://169.254.169.254/private",
        }})
        with tempfile.TemporaryDirectory() as temporary:
            store = acquisition.ExampleStore(temporary)
            with self.assertRaises(acquisition.AcquisitionError):
                store.acquire_reader(PUBLIC, api)
            self.assertEqual(list(store.root.iterdir()), [])
        api.assert_called_once()
        self.dns.assert_not_called()

    def test_reader_does_not_call_provider_when_connect_precheck_fails(self):
        self.connection.connect.side_effect = OSError("Tunnel connection failed: 403 Forbidden")
        api = Mock(side_effect=AssertionError("Reader must not be charged after rejected precheck"))
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(acquisition.AcquisitionError):
                acquisition.ExampleStore(temporary).acquire_reader(PUBLIC, api)
        api.assert_not_called()
        self.dns.assert_not_called()

    def test_reader_does_not_call_provider_for_private_input(self):
        api = Mock(side_effect=AssertionError("Private Reader target must not reach provider"))
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(acquisition.AcquisitionError):
                acquisition.ExampleStore(temporary).acquire_reader("http://10.0.0.1/", api)
        api.assert_not_called()
        self.connection_type.assert_not_called()
        self.dns.assert_not_called()


if __name__ == "__main__":
    unittest.main()
