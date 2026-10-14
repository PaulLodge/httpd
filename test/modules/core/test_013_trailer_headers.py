import re
import socket

import pytest

from pyhttpd.conf import HttpdConf


class TestTrailerHeaders:
    """Verify that RequestHeader unset directives apply to headers
    placed in the trailer section of chunked transfer-encoded requests."""

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        log_file = "removeme_log"
        conf = HttpdConf(env, extras={
            'base': f"""
        RequestHeader unset Removeme
        LogFormat "%{{Removeme}}i" removeme
        CustomLog logs/{log_file} removeme
        """,
        })
        conf.add_vhost_test1()
        conf.install()
        assert env.apache_restart() == 0

    def test_core_013_01_trailer_header_unset(self, env):
        """A header present in the initial request and again in the
        chunked trailer must both be unset by RequestHeader unset."""
        with socket.create_connection(('localhost', int(env.http_port))) as sock:
            request = (
                "POST / HTTP/1.1\r\n"
                "Host: localhost\r\n"
                "Content-Type: application/x-www-form-urlencoded\r\n"
                "Transfer-Encoding: chunked\r\n"
                "Removeme: willbegone\r\n"
                "\r\n"
                "3\r\n"
                "x=a\r\n"
                "0\r\n"
                "Removeme: noyouwont\r\n"
                "\r\n"
            )
            sock.sendall(request.encode())
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

            msg = buff.decode('utf-8', errors='replace')
            assert len(msg) > 0, "no response from server"

            # The custom log should record "-" when the header was
            # successfully removed.  Check the log file directly.
            import os
            import time
            log_path = os.path.join(env.server_logs_dir, "removeme_log")
            # allow a moment for the log to flush
            for _ in range(10):
                if os.path.isfile(log_path):
                    with open(log_path) as f:
                        content = f.read()
                    if content.strip():
                        break
                time.sleep(0.5)

            assert os.path.isfile(log_path), \
                "custom log file was not created"
            with open(log_path) as f:
                content = f.read()
            assert "-" in content, \
                f"header was not unset; log contains: {content!r}"
