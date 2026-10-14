import re
import time

import pytest

from pyhttpd.conf import HttpdConf
from .env import TCPFaker


class _HealthCheckBackend(TCPFaker):
    """Backend that returns a configurable body for health check tests."""

    def __init__(self, host, port, body="Hello"):
        super().__init__(host, port)
        self._response_body = body

    def _make_response(self, data):
        body = self._response_body.encode()
        return (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: text/plain\r\n"
            + f"Content-Length: {len(body)}\r\n".encode()
            + b"\r\n"
            + body
        )


class TestProxyHealthCheck:

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        env.require(env.has_shared_module("proxy_hcheck"),
                    "need mod_proxy_hcheck for this",
                    dep="mod_proxy_hcheck",
                    detected=f"no mod_proxy_hcheck.so in {env.libexec_dir}")

        # Backend 1: body does not contain "world" -- health check fails
        faker1 = _HealthCheckBackend("127.0.0.1", env.http_port2,
                                     body="No match here")
        faker1.start()
        # Backend 2: body contains "world" -- health check passes
        faker2 = _HealthCheckBackend("127.0.0.1", env.ws_port,
                                     body="Hello world!")
        faker2.start()
        # Allow backends to start listening
        time.sleep(0.2)

        mod_path = (f"{env.libexec_dir}/mod_proxy_hcheck.so"
                    .replace('\\', '/'))
        conf = HttpdConf(env)
        conf.add(f'LoadModule proxy_hcheck_module "{mod_path}"')
        # Enable trace logging so that pass/fail messages are visible
        conf.add("LogLevel proxy_hcheck:trace2")
        conf.add([
            "ProxyHCExpr world {hc('body') =~ /world/}",
            "",
            "<Proxy balancer://hctest>",
            f"    BalancerMember http://127.0.0.1:{env.http_port2}"
            f" hcinterval=2 hcmethod=GET hcexpr=world",
            f"    BalancerMember http://127.0.0.1:{env.ws_port}"
            f" hcinterval=2 hcmethod=GET hcexpr=world"
            f" hcuri=/check",
            "</Proxy>",
        ])
        conf.start_vhost(domains=[f"test1.{env.http_tld}"],
                         port=env.http_port,
                         doc_root="htdocs", with_ssl=False)
        conf.add([
            "ProxyPass /hctest balancer://hctest/",
            "ProxyPassReverse /hctest balancer://hctest/",
        ])
        conf.end_vhost()
        conf.install()
        assert env.apache_restart() == 0
        yield
        faker1.stop()
        faker2.stop()

    def test_proxy_09_01_hcexpr_pass_fail(self, env):
        # Verify that the health check module correctly evaluates
        # the hcexpr expression against backend responses.
        # Backend 1 returns "No match here" (no "world") -- should fail.
        # Backend 2 returns "Hello world!" -- should pass.
        start_pos = env.httpd_error_log.current_pos()

        # The pass/fail trace messages use the format:
        #   "Condition <expr> for <hc_worker> (<worker>): passed|failed"
        found_failed = env.httpd_error_log.wait_for(
            re.compile(r'.*Condition.*failed.*'),
            start_pos, timeout=30)
        assert found_failed, \
            "Expected health check failure for backend without " \
            "matching body"

        found_passed = env.httpd_error_log.wait_for(
            re.compile(r'.*Condition.*passed.*'),
            start_pos, timeout=30)
        assert found_passed, \
            "Expected health check pass for backend with " \
            "matching body"

        env.httpd_error_log.ignore_recent(
            matches=[r'.*proxy_hcheck.*', r'.*Condition.*',
                     r'.*HCOH.*', r'.*Health check.*',
                     r'.*hcheck.*'],
            lognos=["AH03930", "AH01106", "AH01114", "AH00959",
                    "AH00957", "AH03248", "AH03249", "AH03251",
                    "AH03256", "AH03258", "AH03261", "AH03300",
                    "AH03301", "AH03302", "AH03303", "AH03311",
                    "AH03312", "AH03313", "AH03314"]
        )
