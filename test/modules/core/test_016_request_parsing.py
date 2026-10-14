import re
import socket
from typing import Optional

import pytest

from pyhttpd.conf import HttpdConf


class TestRequestParsing:
    """Verify that HTTP request parsing enforces proper whitespace
    rules under both Strict and Unsafe HttpProtocolOptions."""

    SP = ' '
    HT = '\t'
    CR = '\r'
    LF = '\n'
    FF = '\f'
    VT = chr(11)    # vertical tab
    CRLF = '\r\n'

    def _send_raw(self, env, request_text):
        """Send a raw request and return the first response line or body."""
        with socket.create_connection(('localhost', int(env.http_port))) as sock:
            sock.sendall(request_text.encode('latin-1'))
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

    def _assert_response_matches(self, response, expected, description):
        """Assert that the response contains the expected status or content."""
        if not response:
            assert False, f"{description}: no response from server"
        if expected in ("200 OK", "400 Bad Request"):
            first_line = response.splitlines()[0] if response.splitlines() else ""
            assert expected in first_line, \
                f"{description}: expected '{expected}' in response, got: {first_line}"
        else:
            # For body content matching (e.g. "Hello world")
            assert expected in response, \
                f"{description}: expected '{expected}' in response body"

    # -- Strict mode tests -----------------------------------------------

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        # We configure with Strict mode and install; individual unsafe
        # tests will reconfigure as needed.
        conf = HttpdConf(env, extras={
            'base': "HttpProtocolOptions Strict",
        })
        conf.add_vhost_test1()
        conf.install()
        assert env.apache_restart() == 0

    def test_core_016_01_valid_request_strict(self, env):
        """Valid request must succeed under Strict mode."""
        req = (f"GET /index.html HTTP/1.1{self.CRLF}"
               f"Host: test1.{env.http_tld}{self.CRLF}{self.CRLF}")
        response = self._send_raw(env, req)
        self._assert_response_matches(response, "200 OK",
                                      "valid request under Strict")

    def test_core_016_02_bare_lf_rejected_strict(self, env):
        """Request with bare LF line endings (no CR) must be rejected
        under Strict mode."""
        req = (f"GET /index.html HTTP/1.1{self.LF}"
               f"Host: test1.{env.http_tld}{self.LF}{self.LF}")
        response = self._send_raw(env, req)
        self._assert_response_matches(response, "400 Bad Request",
                                      "bare LF line endings under Strict")

    @pytest.mark.parametrize("ws", ['\r', '\f', chr(11), '\t'])
    def test_core_016_03_bad_ws_after_method(self, env, ws):
        """Non-SP whitespace between method and URI must be rejected."""
        req = (f"GET{ws}/index.html HTTP/1.1{self.CRLF}"
               f"Host: test1.{env.http_tld}{self.CRLF}{self.CRLF}")
        response = self._send_raw(env, req)
        self._assert_response_matches(response, "400 Bad Request",
                                      f"ws {ord(ws):#x} after method")

    @pytest.mark.parametrize("ws", ['\r', '\f', chr(11), '\t'])
    def test_core_016_04_bad_ws_before_protocol(self, env, ws):
        """Non-SP whitespace between URI and protocol must be rejected."""
        req = (f"GET /index.html{ws}HTTP/1.1{self.CRLF}"
               f"Host: test1.{env.http_tld}{self.CRLF}{self.CRLF}")
        response = self._send_raw(env, req)
        self._assert_response_matches(response, "400 Bad Request",
                                      f"ws {ord(ws):#x} before protocol")

    def test_core_016_05_double_sp_after_method(self, env):
        """Double SP between method and URI must be rejected under Strict."""
        req = (f"GET  /index.html HTTP/1.1{self.CRLF}"
               f"Host: test1.{env.http_tld}{self.CRLF}{self.CRLF}")
        response = self._send_raw(env, req)
        self._assert_response_matches(response, "400 Bad Request",
                                      "double SP after method")

    def test_core_016_06_double_sp_before_protocol(self, env):
        """Double SP between URI and protocol must be rejected under Strict."""
        req = (f"GET /index.html  HTTP/1.1{self.CRLF}"
               f"Host: test1.{env.http_tld}{self.CRLF}{self.CRLF}")
        response = self._send_raw(env, req)
        self._assert_response_matches(response, "400 Bad Request",
                                      "double SP before protocol")

    @pytest.mark.parametrize("ws", ['\r', '\n', '\f', chr(11), ' ', '\t'])
    def test_core_016_07_ws_before_header_colon(self, env, ws):
        """Whitespace between header field-name and colon must be rejected."""
        req = (f"GET /index.html HTTP/1.1{self.CRLF}"
               f"Host{ws}: test1.{env.http_tld}{self.CRLF}{self.CRLF}")
        response = self._send_raw(env, req)
        self._assert_response_matches(response, "400 Bad Request",
                                      f"ws {ord(ws):#x} between field-name and colon")

    @pytest.mark.parametrize("ws", ['\r', chr(11), '\f', '\n'])
    def test_core_016_08_ctrl_char_after_colon(self, env, ws):
        """Control characters in header field separator position
        (after colon) must be rejected."""
        req = (f"GET /index.html HTTP/1.1{self.CRLF}"
               f"Host:{ws}test1.{env.http_tld}{self.CRLF}{self.CRLF}")
        response = self._send_raw(env, req)
        self._assert_response_matches(response, "400 Bad Request",
                                      f"ws {ord(ws):#x} as header field separator")

    def test_core_016_09_sp_after_colon_allowed(self, env):
        """SP after colon in header field is allowed."""
        req = (f"GET /index.html HTTP/1.1{self.CRLF}"
               f"Host: test1.{env.http_tld}{self.CRLF}{self.CRLF}")
        response = self._send_raw(env, req)
        self._assert_response_matches(response, "200 OK",
                                      "SP as header field separator")

    def test_core_016_10_ht_after_colon_allowed(self, env):
        """HT after colon in header field is allowed."""
        req = (f"GET /index.html HTTP/1.1{self.CRLF}"
               f"Host:\ttest1.{env.http_tld}{self.CRLF}{self.CRLF}")
        response = self._send_raw(env, req)
        self._assert_response_matches(response, "200 OK",
                                      "HT as header field separator")
