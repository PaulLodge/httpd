import pytest

from .env import H2Conf, H2TestEnv


@pytest.mark.skipif(condition=H2TestEnv.is_unsupported(), reason="mod_http2 not supported here")
@H2TestEnv.needs_nghttp()
class TestH2MethodHandling:
    """Verify that HTTP/2 method handling rejects invalid or smuggled
    method values in the :method pseudo-header."""

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        H2Conf(env).add_vhost_cgi(
            proxy_self=True,
        ).add_vhost_test1().install()
        assert env.apache_restart() == 0

    # a normal GET request over h2 should work
    def test_h2_902_01_normal_get(self, env):
        url = env.mkurl("https", "cgi", "/hello.py")
        r = env.curl_get(url)
        assert r.exit_code == 0
        assert r.response["status"] == 200

    # a :method with spaces should be rejected (request smuggling attempt)
    def test_h2_902_02_method_with_spaces_rejected(self, env):
        url = env.mkurl("https", "cgi", "/hello.py")
        opt = ["-H:method: GET /hello.py HTTP/1.1"]
        r = env.nghttp().get(url, options=opt)
        assert r.exit_code == 0
        # the server must reject this -- no valid response should come back
        assert r.response is None or r.response["status"] >= 400

    # a :method with embedded path should be rejected
    def test_h2_902_03_method_with_path_rejected(self, env):
        url = env.mkurl("https", "cgi", "/hello.py")
        opt = ["-H:method: GET /etc/passwd"]
        r = env.nghttp().get(url, options=opt)
        assert r.exit_code == 0
        assert r.response is None or r.response["status"] >= 400

    # a :method with embedded path via proxy should be rejected
    def test_h2_902_04_method_smuggle_via_proxy(self, env):
        url = env.mkurl("https", "cgi", "/proxy/hello.py")
        opt = ["-H:method: GET /proxy/hello.py HTTP/1.1"]
        r = env.nghttp().get(url, options=opt)
        assert r.exit_code == 0
        assert r.response is None or r.response["status"] >= 400

    # verify a standard GET still works after invalid method attempts
    def test_h2_902_05_get_after_invalid_method(self, env):
        url = env.mkurl("https", "cgi", "/hello.py")
        r = env.curl_get(url)
        assert r.exit_code == 0
        assert r.response["status"] == 200

    # verify h2c method handling works correctly via --http2-prior-knowledge
    def test_h2_902_06_h2c_method_valid(self, env):
        url = env.mkurl("http", "cgi", "/hello.py")
        r = env.curl_get(url, options=['--http2-prior-knowledge'])
        assert r.exit_code == 0
        assert r.response["status"] == 200

    # a :method with CRLF injection should be rejected
    def test_h2_902_07_method_crlf_injection_rejected(self, env):
        url = env.mkurl("https", "cgi", "/hello.py")
        opt = ["-H:method: GET\r\nX-Injected: true"]
        r = env.nghttp().get(url, options=opt)
        assert r.exit_code == 0
        assert r.response is None or r.response["status"] >= 400
