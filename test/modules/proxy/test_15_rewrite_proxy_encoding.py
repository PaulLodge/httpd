import pytest

from pyhttpd.conf import HttpdConf
from .env import TCPFaker


class _RequestCapture(TCPFaker):
    """Backend that captures the raw bytes of every request it receives."""

    def __init__(self, host, port):
        super().__init__(host, port)
        self._all_requests = []

    @property
    def all_requests(self):
        return list(self._all_requests)

    def clear(self):
        self._all_requests.clear()

    def _make_response(self, data):
        self._all_requests.append(data)
        body = b"OK"
        return (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain\r\n"
            b"Content-Length: 2\r\n"
            b"\r\n"
            + body
        )


class TestRewriteProxyEncoding:

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        faker = _RequestCapture("127.0.0.1", env.http_port2)
        faker.start()

        conf = HttpdConf(env)
        conf.start_vhost(domains=[f"test1.{env.http_tld}"],
                         port=env.http_port,
                         doc_root="htdocs", with_ssl=False)
        conf.add([
            "RewriteEngine on",
            f'RewriteRule "^/here/(.*)$"'
            f' "http://127.0.0.1:{env.http_port2}'
            f'/elsewhere?$1" [P]',
            f"ProxyPassReverse /here/"
            f" http://127.0.0.1:{env.http_port2}/",
            "",
            f'ProxyPassMatch "^/here2/(.*)$"'
            f' "http://127.0.0.1:{env.http_port2}'
            f'/elsewhere2?$1" nocanon',
            f"ProxyPassReverse /here2/"
            f" http://127.0.0.1:{env.http_port2}/",
            "",
            f'<LocationMatch "^/here3/(.*)$">',
            f'    ProxyPassMatch'
            f' "http://127.0.0.1:{env.http_port2}'
            f'/elsewhere3?$1" nocanon',
            f'    ProxyPassReverse'
            f' "http://127.0.0.1:{env.http_port2}/"',
            f'</LocationMatch>',
        ])
        conf.end_vhost()
        conf.install()
        assert env.apache_restart() == 0
        yield faker
        faker.stop()

    def _assert_no_extra_request(self, faker, label):
        """Check that no backend request contains a second GET line
        that would indicate a separate request was constructed from
        encoded control characters in the URL."""
        for req in faker.all_requests:
            # A legitimate request has exactly one request line.
            # A second "GET /secret" proves the encoded CRLF created
            # a separate request.
            assert b"GET /secret" not in req, \
                f"Backend received a separate request via {label}"

    def test_proxy_15_01_rewrite_crlf_no_smuggle(self, env, _class_scope):
        # Test RewriteRule with [P] flag.
        # The URL contains encoded CRLF sequences that, if decoded
        # before proxying, would create a second request line.
        faker = _class_scope
        faker.clear()

        url = env.mkurl(
            "http", "test1",
            "/here/a%20HTTP/1.1%0d%0aHost:%20localhost"
            "%0d%0a%0d%0aGET%20/secret")
        env.curl_get(url)

        self._assert_no_extra_request(faker, "RewriteRule")

        env.httpd_error_log.ignore_recent(
            lognos=["AH01106", "AH01114", "AH00957", "AH01144",
                    "AH00898", "AH10410"]
        )

    def test_proxy_15_02_passmatch_crlf_no_smuggle(self, env, _class_scope):
        # Test ProxyPassMatch with nocanon.
        faker = _class_scope
        faker.clear()

        url = env.mkurl(
            "http", "test1",
            "/here2/a%20HTTP/1.1%0d%0aHost:%20localhost"
            "%0d%0a%0d%0aGET%20/secret")
        env.curl_get(url)

        self._assert_no_extra_request(faker, "ProxyPassMatch")

        env.httpd_error_log.ignore_recent(
            lognos=["AH01106", "AH01114", "AH00957", "AH01144",
                    "AH00898", "AH10410"]
        )

    def test_proxy_15_03_locmatch_crlf_no_smuggle(self, env, _class_scope):
        # Test LocationMatch with ProxyPassMatch and nocanon.
        faker = _class_scope
        faker.clear()

        url = env.mkurl(
            "http", "test1",
            "/here3/a%20HTTP/1.1%0d%0aHost:%20localhost"
            "%0d%0a%0d%0aGET%20/secret")
        env.curl_get(url)

        self._assert_no_extra_request(faker, "LocationMatch")

        env.httpd_error_log.ignore_recent(
            lognos=["AH01106", "AH01114", "AH00957", "AH01144",
                    "AH00898", "AH10410"]
        )
