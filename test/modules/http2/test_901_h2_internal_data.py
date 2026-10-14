import pytest

from .env import H2Conf, H2TestEnv


@pytest.mark.skipif(condition=H2TestEnv.is_unsupported(), reason="mod_http2 not supported here")
class TestH2InternalData:
    """Verify that HTTP/2 handles large response bodies without resource
    exhaustion when a client is slow to consume data."""

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        H2Conf(env).add_vhost_cgi().add_vhost_test1().install()
        assert env.apache_restart() == 0

    # request a large response over h2 and verify it completes
    def test_h2_901_01_large_static_response(self, env):
        url = env.mkurl("https", "test1", "/data-1m")
        r = env.curl_get(url)
        assert r.exit_code == 0
        assert r.response["status"] == 200
        assert len(r.response["body"]) == 1000000

    # request a large response via CGI over h2
    def test_h2_901_02_large_cgi_response(self, env):
        url = env.mkurl("https", "cgi", "/mnot164.py?count=100000&text=X")
        r = env.curl_get(url)
        assert r.exit_code == 0
        assert r.response["status"] == 200
        assert len(r.response["body"]) == 100000

    # multiple large responses on the same connection
    def test_h2_901_03_multiple_large_responses(self, env):
        url = env.mkurl("https", "test1", "/data-100k")
        r = env.curl_raw([url, url, url], options=['--http2'])
        assert r.exit_code == 0

    # request large response while limiting receive speed to stress
    # internal buffering (--limit-rate throttles download speed)
    def test_h2_901_04_throttled_large_download(self, env):
        url = env.mkurl("https", "test1", "/data-1m")
        r = env.curl_get(url, options=[
            '--limit-rate', '64k',
        ])
        assert r.exit_code == 0
        assert r.response["status"] == 200
        assert len(r.response["body"]) == 1000000

    # verify server stays responsive after serving large responses
    def test_h2_901_05_responsive_after_large(self, env):
        # first, request a large resource
        url = env.mkurl("https", "test1", "/data-1m")
        r = env.curl_get(url)
        assert r.exit_code == 0
        assert r.response["status"] == 200
        # then verify a small request still works
        url = env.mkurl("https", "cgi", "/hello.py")
        r = env.curl_get(url)
        assert r.exit_code == 0
        assert r.response["status"] == 200

    # use h2load for concurrent large-response requests to stress buffering
    @H2TestEnv.needs_h2load("1.41.0", reason="h2load misses --connect-to option")
    def test_h2_901_06_h2load_concurrent_large(self, env):
        url = env.mkurl("https", "test1", "/data-100k")
        n = 20
        args = [
            env.h2load, "-n", str(n), "-c", "2", "-m", "5",
            f"--connect-to=localhost:{env.https_port}",
            f"--base-uri={env.mkurl('https', 'test1', '/')}",
            "/data-100k",
        ]
        r = env.run(args)
        assert r.exit_code == 0
        r = env.h2load_status(r)
        assert n == r.results["h2load"]["requests"]["total"]
        assert n == r.results["h2load"]["requests"]["succeeded"]
        assert 0 == r.results["h2load"]["status"]["5xx"]
