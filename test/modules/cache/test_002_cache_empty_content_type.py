import os
import shutil
import stat
import sys

import pytest

from pyhttpd.conf import HttpdConf


class TestCacheEmptyContentType:
    """Verify that mod_cache_disk handles responses with an empty or missing
    Content-Type header without crashing.  A CGI script produces a response
    whose Content-Type header value is empty; the cache must store and serve
    it normally."""

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        # Write a CGI script that emits an empty Content-Type header.
        cgi_dir = os.path.join(env.server_dir, "htdocs", "test1", "cache")
        os.makedirs(cgi_dir, exist_ok=True)
        cgi_path = os.path.join(cgi_dir, "empty_ct.py")
        with open(cgi_path, "w") as f:
            f.write("#!/usr/bin/env python3\n")
            f.write("import datetime\n")
            f.write("print('Content-Type:')\n")
            f.write("print()\n")
            f.write("print(datetime.datetime.now().isoformat())\n")
        st = os.stat(cgi_path)
        os.chmod(cgi_path, st.st_mode | stat.S_IEXEC)

        # Prepare a fresh cache directory.
        cache_dir = os.path.join(env.server_dir, "cache-test")
        if os.path.isdir(cache_dir):
            shutil.rmtree(cache_dir)
        os.makedirs(cache_dir, exist_ok=True)
        self._cache_dir = cache_dir

    def _configure(self, env):
        cache_dir = os.path.join(env.server_dir,
                                 "cache-test").replace('\\', '/')
        domain = f"test1.{env.http_tld}"
        conf = HttpdConf(env, extras={
            domain: f"""
            CacheRoot "{cache_dir}"
            CacheEnable disk /
            CacheIgnoreNoLastMod On
            AddHandler cgi-script .py
            Options +ExecCGI
            """,
        })
        conf.add_vhost(domains=[domain], port=env.http_port,
                       doc_root="htdocs/test1", with_ssl=False)
        conf.install()
        assert env.apache_restart() == 0

    # First request caches the response; verify no crash.
    def test_cache_002_01_empty_ct_cached(self, env):
        self._configure(env)
        url = env.mkurl("http", "test1", "/cache/empty_ct.py")
        r = env.curl_get(url)
        assert r.exit_code == 0, f"curl failed: {r.exit_code}"
        # The server must not have crashed.
        assert env.is_live(), "server is not running after first request"
        if r.response:
            assert r.response["status"] == 200, \
                f"unexpected status: {r.response['status']}"

    # Second request retrieves the cached entry; the cache must serve it
    # without crashing.
    def test_cache_002_02_empty_ct_served_from_cache(self, env):
        url = env.mkurl("http", "test1", "/cache/empty_ct.py")
        r = env.curl_get(url)
        assert r.exit_code == 0, f"curl failed: {r.exit_code}"
        assert env.is_live(), "server is not running after cached request"
        if r.response:
            assert r.response["status"] == 200, \
                f"unexpected status: {r.response['status']}"
        # Check for segfaults in the error log.
        env.httpd_error_log.ignore_recent()
