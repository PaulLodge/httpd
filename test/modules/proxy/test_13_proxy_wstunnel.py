import socket
import time

import pytest

from pyhttpd.conf import HttpdConf
from .env import TCPFaker


class _WstunnelBackend(TCPFaker):
    """Backend for wstunnel tests that tracks incoming connections."""

    def __init__(self, host, port, name="backend"):
        super().__init__(host, port)
        self._name = name
        self._connection_count = 0

    @property
    def connection_count(self):
        return self._connection_count

    def _make_response(self, data):
        self._connection_count += 1
        body = f"Response from {self._name}".encode()
        return (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain\r\n"
            + f"Content-Length: {len(body)}\r\n".encode()
            + b"\r\n"
            + body
        )


class TestProxyWstunnel:

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        env.require(env.has_shared_module("proxy_wstunnel"),
                    "need mod_proxy_wstunnel for this",
                    dep="mod_proxy_wstunnel",
                    detected=f"no mod_proxy_wstunnel.so in "
                             f"{env.libexec_dir}")

        faker1 = _WstunnelBackend("127.0.0.1", env.http_port2,
                                  name="backend1")
        faker1.start()
        faker2 = _WstunnelBackend("127.0.0.1", env.ws_port,
                                  name="backend2")
        faker2.start()

        mod_path = (f"{env.libexec_dir}/mod_proxy_wstunnel.so"
                    .replace('\\', '/'))
        conf = HttpdConf(env)
        conf.add(f'LoadModule proxy_wstunnel_module "{mod_path}"')
        conf.start_vhost(domains=[f"test1.{env.http_tld}"],
                         port=env.http_port,
                         doc_root="htdocs", with_ssl=False)
        conf.add([
            "<Location /ws1>",
            f"    ProxyPass ws://127.0.0.1:{env.http_port2}/test/"
            f" upgrade=NONE",
            "</Location>",
            "",
            "<Location /ws2>",
            f"    ProxyPass ws://127.0.0.1:{env.ws_port}/test/"
            f" upgrade=NONE",
            "</Location>",
        ])
        conf.end_vhost()
        conf.install()
        assert env.apache_restart() == 0
        yield faker1, faker2
        faker1.stop()
        faker2.stop()

    def test_proxy_13_01_pipelined_upgrade_none(self, env, _class_scope):
        faker1, faker2 = _class_scope
        initial_count2 = faker2.connection_count

        # Send two pipelined HTTP/1.1 requests on a single TCP
        # connection.  Each carries "Upgrade: NONE" and is routed
        # through mod_proxy_wstunnel to a different backend.
        # The proxy must process both requests -- the tunnel for
        # request 1 must not swallow request 2.
        request = (
            f"GET /ws1 HTTP/1.1\r\n"
            f"Host: test1.{env.http_tld}\r\n"
            f"Connection: Keep-Alive\r\n"
            f"Upgrade: NONE\r\n"
            f"\r\n"
            f"GET /ws2 HTTP/1.1\r\n"
            f"Host: test1.{env.http_tld}\r\n"
            f"Connection: close\r\n"
            f"Upgrade: NONE\r\n"
            f"\r\n"
        )

        with socket.create_connection(
                ("127.0.0.1", int(env.http_port))) as sock:
            sock.sendall(request.encode())
            sock.settimeout(10)
            try:
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
            except socket.timeout:
                pass

        # Allow the proxy a moment to finish processing
        time.sleep(1)

        assert faker2.connection_count > initial_count2, \
            "Expected connection to 2nd backend through " \
            "wstunnel proxy"

        env.httpd_error_log.ignore_recent(
            matches=[r'.*proxy_wstunnel.*', r'.*proxy:.*',
                     r'.*ws:.*'],
            lognos=["AH01106", "AH01114", "AH02447", "AH00957",
                    "AH00959", "AH01144", "AH01149", "AH02450"]
        )
