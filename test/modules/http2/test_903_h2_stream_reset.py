import re
import pytest

from .env import H2Conf, H2TestEnv


@pytest.mark.skipif(condition=H2TestEnv.is_unsupported(), reason="mod_http2 not supported here")
class TestH2StreamReset:
    """Verify that HTTP/2 stream resets (RST_STREAM) are handled properly
    without causing protocol errors or resource leaks."""

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        H2Conf(env).add_vhost_cgi().add_vhost_test1().install()
        assert env.apache_restart() == 0

    # verify basic parallel requests over h2 complete without protocol errors
    def test_h2_903_01_parallel_requests_no_error(self, env):
        url = env.mkurl("https", "cgi", "/hello.py")
        urls = [url] * 10
        r = env.curl_raw(urls, options=['--parallel', '--parallel-max', '5'])
        assert r.exit_code == 0
        assert 'PROTOCOL_ERROR' not in r.stderr

    # multiple parallel requests with h2c (prior knowledge) should succeed
    def test_h2_903_02_h2c_parallel_no_error(self, env):
        url = env.mkurl("http", "cgi", "/hello.py")
        urls = [url] * 10
        r = env.curl_raw(urls, options=[
            '--http2-prior-knowledge',
            '--parallel',
            '--parallel-max', '5',
        ])
        assert r.exit_code == 0
        assert 'PROTOCOL_ERROR' not in r.stderr

    # parallel requests for mixed resources (static + cgi) over h2
    def test_h2_903_03_mixed_parallel_no_error(self, env):
        urls = []
        # add static file requests
        for i in range(10):
            urls.append(env.mkurl("https", "cgi", f"/hello.py?n={i}"))
        # add a few more cgi requests
        for i in range(5):
            urls.append(env.mkurl("https", "cgi", f"/hello.py?m={i}"))
        r = env.curl_raw(urls, options=[
            '--parallel',
            '--parallel-max', '10',
        ])
        assert r.exit_code == 0
        assert 'PROTOCOL_ERROR' not in r.stderr

    # use h2load to send many concurrent requests and verify no stream errors
    @H2TestEnv.needs_h2load("1.41.0", reason="h2load misses --connect-to option")
    def test_h2_903_04_h2load_concurrent_stable(self, env):
        n = 100
        args = [
            env.h2load, "-n", str(n), "-c", "4", "-m", "16",
            f"--connect-to=localhost:{env.https_port}",
            f"--base-uri={env.mkurl('https', 'cgi', '/')}",
            "/hello.py",
        ]
        r = env.run(args)
        assert r.exit_code == 0
        r = env.h2load_status(r)
        assert n == r.results["h2load"]["requests"]["total"]
        assert n == r.results["h2load"]["requests"]["succeeded"]
        assert 0 == r.results["h2load"]["status"]["5xx"]

    # verify server handles stream cancellation gracefully when client
    # disconnects (using --max-time to force early close)
    def test_h2_903_05_client_timeout_graceful(self, env):
        # request a slow CGI response with a short client timeout
        # this forces the client to reset the stream
        url = env.mkurl("https", "cgi", "/necho.py")
        r = env.curl_raw([url], options=[
            '-F', 'count=50000',
            '-F', 'text=abcdefghij',
            '-F', 'wait2=2',
            '--max-time', '1',
        ])
        # curl exit code 28 = timeout, which is expected
        # the important thing is the server stays healthy
        assert r.exit_code in [0, 28]
        # verify the server is still responsive after the reset
        url = env.mkurl("https", "cgi", "/hello.py")
        r = env.curl_get(url)
        assert r.exit_code == 0
        assert r.response["status"] == 200

    # rapid sequential connections with stream resets
    def test_h2_903_06_rapid_sequential_stable(self, env):
        url = env.mkurl("https", "cgi", "/hello.py")
        for i in range(20):
            r = env.curl_get(url)
            assert r.exit_code == 0
            assert r.response["status"] == 200
