import re
import socket

import pytest

from pyhttpd.conf import HttpdConf


class TestChunkParsing:
    """Verify that the chunked transfer-encoding parser correctly
    handles malformed chunk sizes, extraneous data, and overflow."""

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        conf = HttpdConf(env, extras={
            'base': "LogLevel debug",
        })
        conf.add_vhost_cgi()
        conf.install()
        assert env.apache_restart() == 0

    def _send_raw(self, env, request_bytes):
        """Send raw bytes to the server and return the first response line."""
        with socket.create_connection(('localhost', int(env.http_port))) as sock:
            sock.sendall(request_bytes)
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
        return buff.decode('utf-8', errors='replace')

    def test_core_014_01_oversized_chunk_data(self, env):
        """A chunk whose actual data exceeds the declared size must not
        result in a 404; the server should reject it or truncate."""
        url_path = "/echo_env.py"
        host = f"cgi.{env.http_tld}"
        request = (
            f"POST {url_path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Accept: */*\r\n"
            "Content-Type: application/x-www-form-urlencoded\r\n"
            "Connection: close\r\n"
            "Transfer-Encoding: chunked\r\n"
            "\r\n"
            "9\r\n"
            "data=abcd This part is ignored by httpd\r\n"
            "0\r\n"
            "\r\n"
        )
        response = self._send_raw(env, request.encode())
        assert len(response) > 0, "no response from server"
        first_line = response.splitlines()[0]
        assert "404" not in first_line, \
            f"server returned 404 instead of handling exceeding chunk: {first_line}"

        env.httpd_error_log.ignore_recent(
            matches=[".*[Ee]rror reading.*", ".*chunk.*"]
        )

    def test_core_014_02_bare_cr_in_chunk_ext(self, env):
        """Chunk extension with bare CR characters must be rejected
        or handled without passing through corrupted data."""
        url_path = "/echo_env.py"
        host = f"cgi.{env.http_tld}"
        # The chunk-size line contains bare CR characters before the CRLF
        request_bytes = (
            f"POST {url_path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Accept: */*\r\n"
            "Content-Type: application/x-www-form-urlencoded\r\n"
            "Connection: close\r\n"
            "Transfer-Encoding: chunked\r\n"
            "\r\n"
        ).encode()
        request_bytes += b"9;\r\r\r\r\r\r\r\r\r\r\r\n"
        request_bytes += b"data=abcd\r\n"
        request_bytes += b"0\r\n"
        request_bytes += b"\r\n"

        response = self._send_raw(env, request_bytes)
        assert len(response) > 0, "no response from server"
        first_line = response.splitlines()[0]
        assert "404" not in first_line, \
            f"server returned 404 for request with malformed chunk extension: {first_line}"

        env.httpd_error_log.ignore_recent(
            matches=[".*[Ee]rror reading.*", ".*chunk.*"]
        )

    def test_core_014_03_overflow_chunk_size_rejected(self, env):
        """An absurdly large chunk size (overflow) must be rejected
        with 413 Request Entity Too Large."""
        url_path = "/echo_env.py"
        host = f"cgi.{env.http_tld}"
        request = (
            f"POST {url_path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Accept: */*\r\n"
            "Content-Type: application/x-www-form-urlencoded\r\n"
            "Connection: close\r\n"
            "Transfer-Encoding: chunked\r\n"
            "\r\n"
            "fffffffffffffff0\r\n"
            "data=foo\r\n"
            "0\r\n"
            "\r\n"
        )
        response = self._send_raw(env, request.encode())
        assert len(response) > 0, "no response from server"
        first_line = response.splitlines()[0]
        assert "413" in first_line, \
            f"expected 413 for overflow chunk size, got: {first_line}"

        env.httpd_error_log.ignore_recent(
            matches=[".*[Ee]rror reading.*", ".*chunk.*"]
        )
