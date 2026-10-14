import pytest

from pyhttpd.conf import HttpdConf


class TestProxyHtmlEncoding:

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        env.require(env.has_shared_module("info"),
                    "need mod_info for this",
                    dep="mod_info",
                    detected=f"no mod_info.so in {env.libexec_dir}")

        mod_path = (f"{env.libexec_dir}/mod_info.so"
                    .replace('\\', '/'))
        conf = HttpdConf(env)
        conf.add(f'LoadModule info_module "{mod_path}"')
        conf.add("HttpProtocolOptions Unsafe")
        conf.start_vhost(domains=[f"test1.{env.http_tld}"],
                         port=env.http_port,
                         doc_root="htdocs", with_ssl=False)
        conf.add([
            "<Location /our-server-info>",
            "    SetHandler server-info",
            "</Location>",
        ])
        conf.end_vhost()
        conf.install()
        assert env.apache_restart() == 0
        yield

    def test_proxy_11_01_server_info_host_escaped(self, env):
        # Request the server-info page with an HTML tag in the Host
        # header.  The output must HTML-encode the hostname so that
        # the raw tag is not rendered by a browser.
        url = env.mkurl("http", "test1", "/our-server-info")
        r = env.curl_get(url, options=[
            "-H", "Host: <br>",
        ])
        assert r.exit_code == 0
        assert r.response["status"] == 200
        body = r.response["body"].decode("utf-8", errors="replace")
        # If vulnerable, the output contains the literal <br> tag
        # inside the Hostname/port display
        assert "<tt><br>:" not in body, \
            "Host header HTML was not properly encoded in server-info"

        env.httpd_error_log.ignore_recent(
            lognos=["AH01106", "AH01114", "AH00957"]
        )
