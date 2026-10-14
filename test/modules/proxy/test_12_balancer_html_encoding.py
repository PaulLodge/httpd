import pytest

from pyhttpd.conf import HttpdConf


class TestBalancerHtmlEncoding:

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        conf = HttpdConf(env)
        conf.add("HttpProtocolOptions Unsafe")
        conf.add([
            '<Proxy balancer://htmltest>',
            '    BalancerMember http://192.0.2.1:80',
            '    BalancerMember http://192.0.2.2:80',
            '</Proxy>',
        ])
        conf.start_vhost(domains=[f"test1.{env.http_tld}"],
                         port=env.http_port,
                         doc_root="htdocs", with_ssl=False)
        conf.add([
            "ProxyPass /cluster balancer://htmltest",
            "<Location /balancer-manager>",
            "    SetHandler balancer-manager",
            "</Location>",
        ])
        conf.end_vhost()
        conf.install()
        assert env.apache_restart() == 0
        yield

    def test_proxy_12_01_balancer_mgr_host_escaped(self, env):
        # Request the balancer-manager page with HTML tags in the Host
        # header.  The output must HTML-encode the hostname so that
        # raw tags are not rendered by a browser.
        url = env.mkurl("http", "test1", "/balancer-manager")
        r = env.curl_get(url, options=[
            "-H", "Host: <br><h1><blink>Gotcha",
        ])
        assert r.exit_code == 0
        assert r.response["status"] == 200
        body = r.response["body"].decode("utf-8", errors="replace")
        # If vulnerable, the unescaped HTML appears in the page title
        assert "Load Balancer Manager for <br>" not in body, \
            "Host header HTML was not properly encoded in " \
            "balancer-manager output"
        assert "<blink>" not in body, \
            "HTML tag was not encoded in balancer-manager output"

        env.httpd_error_log.ignore_recent(
            lognos=["AH01106", "AH01114", "AH00957", "AH10187"]
        )
