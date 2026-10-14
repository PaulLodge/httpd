import re
import socket
import time

import pytest

from pyhttpd.depends import needs_dependency

from pyhttpd.conf import HttpdConf
from .env import MetadataTestEnv


@needs_dependency("mod_remoteip", MetadataTestEnv.has_shared_module("remoteip"),
                  reason="mod_remoteip not available")
class TestRemoteipProxyProtoParsing:
    """Tests that mod_remoteip handles malformed PROXY protocol headers
    without crashing."""

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        # Configure a VirtualHost on http_port2 with RemoteIPProxyProtocol
        conf = HttpdConf(env, extras={
            'base': [
                f"Listen {env.http_port2}",
            ]
        })
        conf.start_vhost(domains=[f"test1.{env.http_tld}"],
                         port=env.http_port2, doc_root="htdocs/test1")
        conf.add([
            "RemoteIPProxyProtocol On",
            "<Directory />",
            "    Require all granted",
            "</Directory>",
        ])
        conf.end_vhost()
        conf.install()
        assert env.apache_restart() == 0

    def _send_raw(self, env, data):
        """Send raw bytes to the PROXY protocol port and close."""
        if isinstance(data, str):
            data = data.encode()
        sock = socket.create_connection(
            ("127.0.0.1", env.http_port2), timeout=5
        )
        try:
            sock.sendall(data)
        finally:
            sock.close()

    def test_metadata_005_01_oversized_proxy_v1(self, env):
        """An oversized PROXY v1 line (well past the 108-byte limit)
        must not crash the server."""
        proxy_long = "PROXY" + ("a" * 262) + "\r\n"
        self._send_raw(env, proxy_long)
        time.sleep(0.5)

        # Verify httpd is still alive
        url = env.mkurl("http", "test1", "/")
        r = env.curl_get(url)
        assert r.exit_code == 0, \
            "httpd is not responding after oversized PROXY v1 header"

        env.httpd_error_log.ignore_recent(
            matches=[r".*remoteip.*", r".*proxy.protocol.*"]
        )

    def test_metadata_005_02_short_oversized_proxy_v1(self, env):
        """A shorter but still oversized PROXY v1 line must not crash
        the server."""
        proxy_short = "PROXY" + ("a" * 131) + "\r\n"
        self._send_raw(env, proxy_short)
        time.sleep(0.5)

        url = env.mkurl("http", "test1", "/")
        r = env.curl_get(url)
        assert r.exit_code == 0, \
            "httpd is not responding after shorter PROXY v1 header"

        env.httpd_error_log.ignore_recent(
            matches=[r".*remoteip.*", r".*proxy.protocol.*"]
        )

    def test_metadata_005_03_proxy_v2_local_zero_addr(self, env):
        """A PROXY v2 header with LOCAL command and TCP4 family but a
        zero-length address block must not crash the server."""
        v2_local = bytes([
            0x0D, 0x0A, 0x0D, 0x0A, 0x00, 0x0D, 0x0A, 0x51,
            0x55, 0x49, 0x54, 0x0A, 0x20, 0x11, 0x00, 0x00
        ])
        self._send_raw(env, v2_local)
        time.sleep(0.5)

        url = env.mkurl("http", "test1", "/")
        r = env.curl_get(url)
        assert r.exit_code == 0, \
            "httpd is not responding after PROXY v2 LOCAL header"

        env.httpd_error_log.ignore_recent(
            matches=[r".*remoteip.*", r".*proxy.protocol.*"]
        )

    def test_metadata_005_04_proxy_v2_unspec_zero_addr(self, env):
        """A PROXY v2 header with PROXY command and UNSPEC family
        (zero-length address block) must not crash the server."""
        v2_unspec = bytes([
            0x0D, 0x0A, 0x0D, 0x0A, 0x00, 0x0D, 0x0A, 0x51,
            0x55, 0x49, 0x54, 0x0A, 0x21, 0x00, 0x00, 0x00
        ])
        self._send_raw(env, v2_unspec)
        time.sleep(0.5)

        url = env.mkurl("http", "test1", "/")
        r = env.curl_get(url)
        assert r.exit_code == 0, \
            "httpd is not responding after PROXY v2 UNSPEC header"

        env.httpd_error_log.ignore_recent(
            matches=[r".*remoteip.*", r".*proxy.protocol.*"]
        )

    def test_metadata_005_05_no_segfault_in_log(self, env):
        """After all the malformed headers, verify that the error log
        does not contain a segfault."""
        re_segfault = re.compile(r".*Segmentation.*fault.*")
        segfaulted = env.httpd_error_log.wait_for(re_segfault, 0,
                                                  timeout=2)
        assert not segfaulted, \
            "httpd segfaulted during PROXY protocol parsing tests"

        env.httpd_error_log.ignore_recent(
            matches=[r".*remoteip.*", r".*proxy.protocol.*"]
        )
