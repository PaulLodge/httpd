import os
import re
import socket

import pytest

from pyhttpd.conf import HttpdConf


class TestUrlNormalization:
    """Verify that URL path normalization (slash merging) works correctly
    with LocationMatch directives, including MergeSlashes on/off."""

    APP_DIR = "urlnorm"

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        # Create the directory structure for the test
        doc_root = os.path.join(env.server_dir, "htdocs", "test1")
        test_dir = os.path.join(doc_root, self.APP_DIR, "a", "b", "c")
        os.makedirs(test_dir, exist_ok=True)
        index_path = os.path.join(test_dir, "index.html")
        with open(index_path, 'w') as f:
            f.write("<html><body>My voice is my passport</body></html>")

        directory = doc_root.replace('\\', '/')

        conf = HttpdConf(env, extras={
            'base': f"""
        <Directory "{directory}">
            AllowOverride None
            Require all granted
        </Directory>
        """,
            f"test1.{env.http_tld}": f"""
        <LocationMatch ^/{self.APP_DIR}/a/b/c/index.html>
            Require all denied
        </LocationMatch>
        """,
        })
        conf.add_vhost_test1()
        conf.install()
        assert env.apache_restart() == 0

    def _send_raw_request(self, env, request_text):
        """Send a raw HTTP request and return the full response."""
        with socket.create_connection(('localhost', int(env.http_port))) as sock:
            sock.sendall(request_text.encode())
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

    def _get_status(self, response):
        """Extract the HTTP status code from a raw response."""
        m = re.match(r'HTTP/1\.\d (\d+)', response)
        return int(m.group(1)) if m else None

    @pytest.mark.parametrize(["path", "expected_status", "description"], [
        # Exact match -- must be denied
        [f"/urlnorm/a/b/c/index.html", 403,
         "exact match must be denied"],
        # Double slash at front -- merged, so still matches denied location
        [f"//urlnorm/a/b/c/index.html", 403,
         "leading double slash merged"],
        # Triple slash at front -- merged
        [f"///urlnorm/a/b/c/index.html", 403,
         "leading triple slash merged"],
        # Double slash inside path -- merged
        [f"/urlnorm/a/b/c//index.html", 403,
         "trailing double slash merged"],
        # Double slash after a/ -- merged
        [f"/urlnorm/a//b/c/index.html", 403,
         "internal double slash merged"],
        # Double slash after b/ -- merged (default MergeSlashes on)
        [f"/urlnorm/a/b//c/index.html", 403,
         "internal double slash after b/ merged"],
    ])
    def test_core_018_01_merge_slashes_on(self, env, path, expected_status, description):
        """With default MergeSlashes (on), duplicate slashes are merged
        before LocationMatch is evaluated."""
        host = f"test1.{env.http_tld}"
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        response = self._send_raw_request(env, request)
        status = self._get_status(response)
        assert status == expected_status, \
            f"{description}: expected {expected_status}, got {status}"
        if expected_status == 403:
            env.httpd_error_log.ignore_recent(lognos=["AH01630"])


class TestUrlNormalizationMergeOff:
    """Verify URL normalization when MergeSlashes is OFF."""

    APP_DIR = "urlnorm"

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        doc_root = os.path.join(env.server_dir, "htdocs", "test1")
        test_dir = os.path.join(doc_root, self.APP_DIR, "a", "b", "c")
        os.makedirs(test_dir, exist_ok=True)
        index_path = os.path.join(test_dir, "index.html")
        with open(index_path, 'w') as f:
            f.write("<html><body>My voice is my passport</body></html>")

        directory = doc_root.replace('\\', '/')

        conf = HttpdConf(env, extras={
            'base': f"""
        <Directory "{directory}">
            AllowOverride None
            Require all granted
        </Directory>
        """,
            f"test1.{env.http_tld}": f"""
        MergeSlashes OFF
        <LocationMatch ^/{self.APP_DIR}/a/b/c/index.html>
            Require all denied
        </LocationMatch>
        <LocationMatch ^/{self.APP_DIR}/a//b/c/index.html>
            Require all denied
        </LocationMatch>
        <LocationMatch /{self.APP_DIR}/a/b/c/index.html>
            Require all denied
        </LocationMatch>
        """,
        })
        conf.add_vhost_test1()
        conf.install()
        assert env.apache_restart() == 0

    def _send_raw_request(self, env, request_text):
        """Send a raw HTTP request and return the full response."""
        with socket.create_connection(('localhost', int(env.http_port))) as sock:
            sock.sendall(request_text.encode())
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

    def _get_status(self, response):
        m = re.match(r'HTTP/1\.\d (\d+)', response)
        return int(m.group(1)) if m else None

    @pytest.mark.parametrize(["path", "expected_status", "description"], [
        # a//b matches the dedicated LocationMatch for a//b
        [f"/urlnorm/a//b/c/index.html", 403,
         "a// matches dedicated location"],
        # b//c does NOT match any LocationMatch (no merge, no specific rule)
        [f"/urlnorm/a/b//c/index.html", 200,
         "b// does not match any location without merging"],
        # c// does NOT match any LocationMatch
        [f"/urlnorm/a/b/c//index.html", 200,
         "c// does not match location without merging"],
    ])
    def test_core_018_02_merge_slashes_off(self, env, path, expected_status, description):
        """With MergeSlashes OFF, duplicate slashes are NOT merged;
        only exact LocationMatch patterns apply."""
        host = f"test1.{env.http_tld}"
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Connection: close\r\n"
            "\r\n"
        )
        response = self._send_raw_request(env, request)
        status = self._get_status(response)
        assert status == expected_status, \
            f"{description}: expected {expected_status}, got {status}"
        if expected_status == 403:
            env.httpd_error_log.ignore_recent(lognos=["AH01630"])
