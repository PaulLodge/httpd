import os
import stat

import pytest

from pyhttpd.conf import HttpdConf


class TestCacheSocache:
    """Verify that mod_cache_socache handles shared object caching with
    edge-case content headers without crashing.  A CGI script produces a
    response with specific cache-related headers; two successive requests
    (one to populate the cache, one to retrieve) must both return 200 and
    the server must remain stable."""

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        # Write a CGI script that emits cache-friendly headers.
        cgi_dir = os.path.join(env.server_dir, "htdocs", "test1",
                               "socache")
        os.makedirs(cgi_dir, exist_ok=True)
        cgi_path = os.path.join(cgi_dir, "test.py")
        with open(cgi_path, "w") as f:
            f.write("#!/usr/bin/env python3\n")
            f.write("import datetime\n")
            f.write("body = datetime.datetime.now().isoformat() + '\\n'\n")
            f.write("print('Content-Type: text/plain')\n")
            f.write("print('Cache-Control: must-revalidate, max-age=10')\n")
            f.write("print('Vary: Accept-Encoding')\n")
            f.write("print(f'Content-Length: {len(body)}')\n")
            f.write("print()\n")
            f.write("print(body, end='')\n")
        st = os.stat(cgi_path)
        os.chmod(cgi_path, st.st_mode | stat.S_IEXEC)

    def _configure(self, env):
        domain = f"test1.{env.http_tld}"
        conf = HttpdConf(env, extras={
            domain: """
            CacheSocache shmcb
            CacheSocacheMaxSize 102400
            CacheEnable socache /
            AddHandler cgi-script .py
            Options +ExecCGI
            """,
        })
        conf.add_vhost(domains=[domain], port=env.http_port,
                       doc_root="htdocs/test1", with_ssl=False)
        conf.install()
        assert env.apache_restart() == 0

    # First request: populate the socache with a response whose headers
    # include Cache-Control, Vary, and Content-Length.  Send with an empty
    # Cache-Control header in the request, an edge case that formerly
    # triggered out-of-bounds reads.
    def test_cache_003_01_socache_populate(self, env):
        self._configure(env)
        url = env.mkurl("http", "test1", "/socache/test.py")
        r = env.curl_get(url, options=["-H", "Cache-Control:"])
        assert r.exit_code == 0, f"curl failed: {r.exit_code}"
        assert env.is_live(), "server is not running after first request"
        assert r.response, "no response received"
        assert r.response["status"] == 200, \
            f"unexpected status: {r.response['status']}"

    # Second request: retrieve from cache with the same edge-case header.
    def test_cache_003_02_socache_retrieve(self, env):
        url = env.mkurl("http", "test1", "/socache/test.py")
        r = env.curl_get(url, options=["-H", "Cache-Control:"])
        assert r.exit_code == 0, f"curl failed: {r.exit_code}"
        assert env.is_live(), "server is not running after cached request"
        assert r.response, "no response received"
        assert r.response["status"] == 200, \
            f"unexpected status: {r.response['status']}"
        # Acknowledge any expected warnings from the cache modules.
        env.httpd_error_log.ignore_recent()
