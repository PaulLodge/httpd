import os
import re

import pytest

from pyhttpd.conf import HttpdConf


class TestRewriteLogSpecialChars:

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        # Create a subdirectory under the test1 document root for the rewrite
        rewrite_dir = os.path.join(env.server_docs_dir, "test1", "rewrite")
        os.makedirs(rewrite_dir, exist_ok=True)
        rewrite_dir_escaped = rewrite_dir.replace('\\', '/')
        conf = HttpdConf(env, extras={
            'base': f"""
        <Directory "{rewrite_dir_escaped}">
            AllowOverride None
            Require all granted
            RewriteEngine On
            RewriteRule "^path(.*)" "http://test1.{env.http_tld}:{env.http_port}/\ttest/"
        </Directory>

        LogLevel debug rewrite:trace8
        """,
        })
        conf.add_vhost_test1()
        conf.install()
        assert env.apache_restart() == 0

    # Verify that mod_rewrite escapes special characters (such as terminal
    # escape sequences) when writing redirect URLs to the log.  A RewriteRule
    # whose target contains a literal tab should appear in the error log with
    # the tab escaped as \\t, not as a raw control character.
    def test_rewrite_003_01_special_chars_escaped(self, env):
        url = env.mkurl("http", "test1", "/rewrite/path")
        r = env.curl_get(url)
        # The request triggers a rewrite redirect (302). The response
        # status depends on whether the redirect target exists, but
        # what matters is the log output.
        assert r.exit_code == 0

        # Check that the error log contains the escaped tab (\t) in
        # the rewrite trace, not a raw tab character.
        host_port = f"test1.{env.http_tld}:{env.http_port}"
        re_escaped = re.compile(
            r'.*implicitly forcing redirect.*with '
            r'http://' + re.escape(host_port) + r'/\\ttest/.*'
        )
        assert env.httpd_error_log.scan_recent(re_escaped, timeout=5), \
            "Rewrite log should contain escaped tab (\\t) in redirect URL"

        # Also verify the escaping message itself is present
        re_escaping = re.compile(
            r'.*escaping http://' + re.escape(host_port) + r'/\\ttest/ for redirect.*'
        )
        assert env.httpd_error_log.scan_recent(re_escaping, timeout=5), \
            "Rewrite log should contain escaping message with escaped tab"

        env.httpd_error_log.ignore_recent(
            matches=[r'.*rewrite:trace.*', r'.*:debug\].*']
        )
