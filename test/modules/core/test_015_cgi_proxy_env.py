import pytest

from pyhttpd.conf import HttpdConf


class TestCgiProxyEnv:
    """Verify that a client-supplied Proxy request header is NOT
    propagated to CGI scripts as the HTTP_PROXY environment variable."""

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        conf = HttpdConf(env)
        conf.add_vhost_cgi()
        conf.install()
        assert env.apache_restart() == 0

    def test_core_015_01_proxy_header_not_propagated(self, env):
        """Sending a Proxy: header must not set HTTP_PROXY in CGI env."""
        url = env.mkurl("http", "cgi", "/echo_env.py")
        r = env.curl_get(url, options=[
            "-H", "Proxy: http://attacker.example.com",
        ])
        assert r.response["status"] == 200
        body = r.response["json"]
        # HTTP_PROXY must either be absent or empty -- never the
        # attacker-supplied value.
        http_proxy = body.get("HTTP_PROXY", "")
        assert http_proxy == "", \
            f"Proxy header was propagated to HTTP_PROXY: {http_proxy!r}"
