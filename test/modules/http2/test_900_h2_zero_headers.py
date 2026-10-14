import pytest

from .env import H2Conf, H2TestEnv


@pytest.mark.skipif(condition=H2TestEnv.is_unsupported(), reason="mod_http2 not supported here")
class TestH2ZeroHeaders:
    """Verify that HTTP/2 handles zero-length header values without issues."""

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        H2Conf(env).add_vhost_cgi().add_vhost_test1().install()
        assert env.apache_restart() == 0

    # send a request with an empty header value over h2
    def test_h2_900_01_single_empty_header(self, env):
        url = env.mkurl("https", "cgi", "/hello.py")
        r = env.curl_get(url, options=[
            '-H', 'X-Empty-Value:',
        ])
        assert r.exit_code == 0
        assert r.response["status"] == 200

    # send a request with multiple empty header values over h2
    def test_h2_900_02_multiple_empty_headers(self, env):
        url = env.mkurl("https", "cgi", "/hello.py")
        r = env.curl_get(url, options=[
            '-H', 'X-Empty-One:',
            '-H', 'X-Empty-Two:',
            '-H', 'X-Empty-Three:',
        ])
        assert r.exit_code == 0
        assert r.response["status"] == 200

    # send a request with a mix of empty and non-empty header values
    def test_h2_900_03_mixed_empty_nonempty_headers(self, env):
        url = env.mkurl("https", "cgi", "/hello.py")
        r = env.curl_get(url, options=[
            '-H', 'X-Has-Value: something',
            '-H', 'X-Empty-Value:',
            '-H', 'X-Also-Has-Value: else',
        ])
        assert r.exit_code == 0
        assert r.response["status"] == 200

    # send many requests with zero-length headers to verify server stability
    def test_h2_900_04_repeated_empty_headers_stable(self, env):
        url = env.mkurl("https", "cgi", "/hello.py")
        for i in range(10):
            r = env.curl_get(url, options=[
                '-H', f'X-Empty-{i}:',
            ])
            assert r.exit_code == 0
            assert r.response["status"] == 200

    # verify the server stays responsive after processing zero-length headers
    def test_h2_900_05_responsive_after_empty_headers(self, env):
        url = env.mkurl("https", "cgi", "/hello.py")
        # first send the request with zero-length header
        r = env.curl_get(url, options=[
            '-H', 'X-Empty:',
        ])
        assert r.exit_code == 0
        assert r.response["status"] == 200
        # then verify a normal request still works
        r = env.curl_get(url)
        assert r.exit_code == 0
        assert r.response["status"] == 200
