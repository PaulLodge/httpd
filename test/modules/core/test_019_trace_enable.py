import pytest

from pyhttpd.conf import HttpdConf


class TestTraceEnable:
    """Verify that TraceEnable Off blocks the TRACE HTTP method."""

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        conf = HttpdConf(env, extras={
            'base': """
        TraceEnable off
        """,
        })
        conf.add_vhost_test1()
        conf.install()
        assert env.apache_restart() == 0

    def test_core_019_01_trace_rejected_405(self, env):
        """A TRACE request must be rejected with 405 Method Not Allowed
        when TraceEnable is off."""
        url = env.mkurl("http", "test1", "/index.html")
        r = env.curl_get(url, options=["-X", "TRACE"])
        assert r.response["status"] == 405, \
            f"expected 405, got {r.response['status']}"

    def test_core_019_02_trace_405_body_mentions_trace(self, env):
        """The 405 response body should indicate that TRACE is not allowed."""
        url = env.mkurl("http", "test1", "/index.html")
        r = env.curl_get(url, options=["-X", "TRACE"])
        assert r.response["status"] == 405
        body = r.response["body"].decode() if isinstance(
            r.response["body"], bytes) else r.response["body"]
        assert "TRACE" in body, \
            f"response body does not mention TRACE: {body[:200]}"

    def test_core_019_03_get_still_works(self, env):
        """A normal GET request must still succeed when TraceEnable is off."""
        url = env.mkurl("http", "test1", "/index.html")
        r = env.curl_get(url)
        assert r.response["status"] == 200

        env.httpd_error_log.ignore_recent(
            lognos=["AH00135"]
        )
