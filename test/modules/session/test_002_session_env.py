import pytest

from pyhttpd.conf import HttpdConf


class TestSessionEnv:
    """Verify that mod_session does not let a request header named after the
    session cookie override the real cookie-based session data when
    SessionEnv is enabled."""

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        conf = HttpdConf(env, extras={
            'base': [
                "Session On",
                "SessionEnv On",
                "SessionCookieName session path=/",
                "SessionHeader X-Replace-Session",
            ],
        })
        conf.add_vhost_cgi()
        conf.install()
        assert env.apache_restart() == 0

    def test_session_002_01_env_header_not_overridden(self, env):
        """A request header with the same name as the session cookie must
        not override the real session data exposed via SessionEnv."""
        hacked_string = "hacked_key=hacked_val"
        session_string = "original_key=original_value"

        url = env.mkurl("http", "cgi", "/session_env.py")
        r = env.curl_get(url, options=[
            "-H", f"session: {hacked_string}",
            "-b", f"session={session_string}",
        ])
        assert r.exit_code == 0, r.stderr
        assert r.response["status"] == 200

        body = r.response["body"].decode()
        hacked_var = f"HTTP_SESSION={hacked_string}"
        unhacked_var = f"HTTP_SESSION={session_string}"
        assert hacked_var not in body, \
            f"Injected header value should not appear in environment: {hacked_var}"
        assert unhacked_var in body, \
            f"Cookie-based session value should appear in environment: {unhacked_var}"
