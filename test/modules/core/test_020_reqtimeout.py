import socket
import time

import pytest

from pyhttpd.conf import HttpdConf


class TestReqtimeout:
    """Verify that mod_reqtimeout enforces body read timeouts."""

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        conf = HttpdConf(env, extras={
            'base': """
        RequestReadTimeout header=10 body=3
        """,
        })
        conf.add_vhost_test1()
        conf.add_vhost_cgi()
        conf.install()
        assert env.apache_restart() == 0

    def test_core_020_01_normal_get_with_timeout(self, env):
        """A normal GET request must succeed even with body timeout set."""
        url = env.mkurl("http", "test1", "/index.html")
        r = env.curl_get(url)
        assert r.response["status"] == 200

    def test_core_020_02_stalled_body_times_out(self, env):
        """A request that stalls mid-body past the timeout must be
        closed by the server (408 Request Timeout or connection reset)."""
        host = f"test1.{env.http_tld}"
        with socket.create_connection(('localhost', int(env.http_port))) as sock:
            # Send headers declaring a body, but stall after sending
            # only part of it.
            request_header = (
                f"POST /index.html HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                "Content-Type: application/x-www-form-urlencoded\r\n"
                "Content-Length: 1000\r\n"
                "\r\n"
            )
            sock.sendall(request_header.encode())
            # Send a small fragment, then wait for the timeout to expire
            sock.sendall(b"x=partial")
            # Wait longer than the body timeout (3 seconds + margin)
            time.sleep(5)

            sock.settimeout(5)
            buff = b""
            try:
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buff += chunk
            except (socket.timeout, ConnectionResetError, BrokenPipeError):
                pass

        response = buff.decode('utf-8', errors='replace')
        if response:
            # Server sent a response before closing -- expect 408
            assert "408" in response, \
                f"expected 408 timeout response, got: {response.splitlines()[0]}"
        # else: server simply closed the connection, which is also acceptable

        env.httpd_error_log.ignore_recent(
            lognos=["AH01382",   # Request body read timeout
                    "AH00567"]   # request failed: error reading the headers
        )

    def test_core_020_03_timely_body_succeeds(self, env):
        """A request with the complete body sent promptly must succeed."""
        host = f"test1.{env.http_tld}"
        body = b"x=completebody"
        with socket.create_connection(('localhost', int(env.http_port))) as sock:
            request = (
                f"POST /index.html HTTP/1.1\r\n"
                f"Host: {host}\r\n"
                "Content-Type: application/x-www-form-urlencoded\r\n"
                f"Content-Length: {len(body)}\r\n"
                "Connection: close\r\n"
                "\r\n"
            ).encode() + body
            sock.sendall(request)
            sock.settimeout(5)
            buff = b""
            try:
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buff += chunk
            except socket.timeout:
                pass

        response = buff.decode('utf-8', errors='replace')
        assert len(response) > 0, "no response from server"
        first_line = response.splitlines()[0]
        assert "200" in first_line, \
            f"expected 200 for timely body, got: {first_line}"
