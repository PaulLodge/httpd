import re

import pytest

from pyhttpd.conf import HttpdConf
from .env import TCPFaker


class _NoContinueBackend(TCPFaker):
    """Backend that responds with 200 OK without sending 100 Continue.

    If the received data includes a request body (after the blank line),
    the body is echoed back.  Otherwise the response body is NOBODY.
    This mimics a backend that does not implement Expect: 100-continue.
    """

    def _make_response(self, data):
        parts = data.split(b"\r\n\r\n", 1)
        body = (parts[1]
                if len(parts) > 1 and len(parts[1]) > 0
                else None)

        if body:
            return (
                f"HTTP/1.1 200 OK\r\n"
                f"Content-Length: {len(body)}\r\n"
                f"\r\n"
            ).encode() + body
        return (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Length: 6\r\n"
            b"\r\n"
            b"NOBODY"
        )


class TestProxy100Continue:

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        faker = _NoContinueBackend("127.0.0.1", env.http_port2)
        faker.start()

        conf = HttpdConf(env)
        conf.start_vhost(domains=[f"test1.{env.http_tld}"],
                         port=env.http_port,
                         doc_root="htdocs", with_ssl=False)
        conf.add([
            f"ProxyPass /app http://127.0.0.1:{env.http_port2} ping=2",
            f"ProxyPassReverse /app http://127.0.0.1:{env.http_port2}",
        ])
        conf.end_vhost()
        conf.install()
        assert env.apache_restart() == 0
        yield
        faker.stop()

    def test_proxy_10_01_no_body_without_continue(self, env):
        # POST through the proxy.  The backend does not send 100
        # Continue, so httpd should not forward the request body.
        # The backend therefore sees no body and responds with NOBODY.
        url = env.mkurl("http", "test1", "/app/test")
        r = env.curl_post_data(url, data="TEST-PARAM=SOMETHING",
                               options=[
                                   "-H", "Expect: 100-continue",
                               ])
        assert r.exit_code == 0
        assert r.response["status"] == 200
        assert r.response["body"] == b"NOBODY"

        # The error log should note the missing 100-continue
        try:
            found = env.httpd_error_log.scan_recent(
                re.compile(r'.*no 100 continue.*'),
                timeout=5)
        except TimeoutError:
            found = False
        assert found, \
            "Expected 'no 100 continue' message in error log"

        env.httpd_error_log.ignore_recent(
            matches=[r'.*no 100 continue.*'],
            lognos=["AH01106", "AH01114"]
        )
