import os
import sys

import pytest

from pyhttpd.conf import HttpdConf


class TestFilenameParsing:
    """Verify that FilesMatch regex anchors work correctly and do not
    match filenames containing trailing newline characters."""

    SCRIPT_NAME = "testOK.pl"

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        if sys.platform == "win32":
            pytest.skip("Windows does not support newlines in filenames")

        doc_root = os.path.join(env.server_dir, "htdocs", "test1")
        os.makedirs(doc_root, exist_ok=True)

        # Create a simple Perl-like CGI script
        script_path = os.path.join(doc_root, self.SCRIPT_NAME)
        with open(script_path, 'w') as f:
            f.write("#!/usr/bin/env python3\n")
            f.write("print('Content-Type: text/plain')\n")
            f.write("print()\n")
            f.write("print('EXECUTED OK')\n")
        os.chmod(script_path, 0o755)

        conf = HttpdConf(env, extras={
            'base': f"""
        <Directory "{doc_root.replace(chr(92), '/')}">
            AllowOverride None
            Options +ExecCGI +FollowSymLinks
            Require all granted
            <FilesMatch ".+\\.py$">
                SetHandler cgi-script
            </FilesMatch>
        </Directory>
        """,
        })
        conf.add_vhost_test1()
        conf.install()
        assert env.apache_restart() == 0

    def test_core_017_01_valid_extension_executed(self, env):
        """A script with a proper .py extension must be executed."""
        url = env.mkurl("http", "test1", f"/{self.SCRIPT_NAME}")
        r = env.curl_get(url)
        assert r.response["status"] == 200
        body = r.response["body"].decode() if isinstance(
            r.response["body"], bytes) else r.response["body"]
        assert "EXECUTED OK" in body, \
            f"script was not executed: {body}"

    def test_core_017_02_trailing_newline_not_matched(self, env):
        """A file with a trailing newline in its name (accessed via
        percent-encoded %0a) must NOT be executed as a CGI script.
        The FilesMatch '.+\\.py$' must not match the newline."""
        if sys.platform == "win32":
            pytest.skip("Windows does not support newlines in filenames")

        doc_root = os.path.join(env.server_dir, "htdocs", "test1")
        src = os.path.join(doc_root, self.SCRIPT_NAME)
        dst = os.path.join(doc_root, f"{self.SCRIPT_NAME}\n")

        # Copy the script with a trailing newline in its filename
        if os.path.exists(dst):
            os.remove(dst)
        import shutil
        shutil.copy2(src, dst)

        url = env.mkurl("http", "test1", f"/{self.SCRIPT_NAME}%0a")
        r = env.curl_get(url)

        # If the server is patched correctly, the script should NOT
        # be evaluated -- it should either be served as plain text
        # (containing the script source) or return a 404/403.
        body = r.response["body"].decode() if isinstance(
            r.response["body"], bytes) else r.response["body"]

        if r.response["status"] == 200:
            # If served, the raw script text must be visible
            # (not executed), meaning we see the source code.
            assert "EXECUTED OK" not in body or "print" in body, \
                "script with newline in filename was executed"
        else:
            # 404 or 403 is also acceptable
            assert r.response["status"] in (403, 404), \
                f"unexpected status: {r.response['status']}"

        # Clean up the newline-named file
        if os.path.exists(dst):
            os.remove(dst)
