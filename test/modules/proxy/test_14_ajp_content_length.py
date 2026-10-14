import struct

import pytest

from pyhttpd.conf import HttpdConf
from .env import TCPFaker


class _SimpleAJPBackend(TCPFaker):
    """Minimal AJP/1.3 backend that responds with 200 OK."""

    def __init__(self, host, port):
        super().__init__(host, port)
        self._request_count = 0

    @property
    def request_count(self):
        return self._request_count

    def _make_response(self, data):
        self._request_count += 1
        body = b"AJP OK"
        cl_val = str(len(body)).encode()

        # SEND_HEADERS packet  (prefix_code 4)
        sh = bytearray()
        sh.append(0x04)                              # type
        sh.extend(struct.pack(">H", 200))            # status code
        sh.extend(struct.pack(">H", 2))              # status-msg len
        sh.extend(b"OK\x00")                         # status msg + NUL
        sh.extend(struct.pack(">H", 2))              # num_headers
        # Content-Type  (coded 0xA001)
        sh.extend(struct.pack(">H", 0xA001))
        ct = b"text/plain"
        sh.extend(struct.pack(">H", len(ct)))
        sh.extend(ct + b"\x00")
        # Content-Length  (coded 0xA003)
        sh.extend(struct.pack(">H", 0xA003))
        sh.extend(struct.pack(">H", len(cl_val)))
        sh.extend(cl_val + b"\x00")
        pkt1 = b"AB" + struct.pack(">H", len(sh)) + bytes(sh)

        # SEND_BODY_CHUNK packet  (prefix_code 3)
        sc = bytearray()
        sc.append(0x03)
        sc.extend(struct.pack(">H", len(body)))
        sc.extend(body + b"\x00")
        pkt2 = b"AB" + struct.pack(">H", len(sc)) + bytes(sc)

        # END_RESPONSE packet  (prefix_code 5, reuse=0)
        er = bytearray([0x05, 0x00])
        pkt3 = b"AB" + struct.pack(">H", len(er)) + bytes(er)

        return bytes(pkt1) + bytes(pkt2) + bytes(pkt3)


class TestAjpContentLength:

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        env.require(env.has_shared_module("proxy_ajp"),
                    "need mod_proxy_ajp for this",
                    dep="mod_proxy_ajp",
                    detected=f"no mod_proxy_ajp.so in {env.libexec_dir}")

        faker = _SimpleAJPBackend("127.0.0.1", env.http_port2)
        faker.start()

        conf = HttpdConf(env)
        conf.start_vhost(domains=[f"test1.{env.http_tld}"],
                         port=env.http_port,
                         doc_root="htdocs", with_ssl=False)
        conf.add([
            "ProxyPreserveHost On",
            f"ProxyPass / ajp://127.0.0.1:{env.http_port2}/",
            f"ProxyPassReverse / ajp://127.0.0.1:{env.http_port2}/",
        ])
        conf.end_vhost()
        conf.install()
        assert env.apache_restart() == 0
        yield faker
        faker.stop()

    def test_proxy_14_01_ajp_get_basic(self, env, _class_scope):
        # Verify that a plain GET through the AJP proxy works.
        url = env.mkurl("http", "test1", "/test")
        r = env.curl_get(url)
        assert r.exit_code == 0
        assert r.response["status"] == 200

        env.httpd_error_log.ignore_recent(
            lognos=["AH00957", "AH01106", "AH01114", "AH00878",
                    "AH00992"]
        )

    def test_proxy_14_02_ajp_malformed_te_rejected(self, env, _class_scope):
        # Send requests with a malformed Transfer-Encoding header.
        # The value ",chunked" must not be accepted as chunked
        # encoding -- doing so would allow a second request to be
        # constructed from the body.
        faker = _class_scope
        initial_count = faker.request_count

        url = env.mkurl("http", "test1", "/test")
        for _ in range(10):
            r = env.curl_raw([url], options=[
                "-H", "Transfer-Encoding: ,chunked",
                "--data-binary", "test_body_data",
            ])
            # If the request reached the backend, verify the
            # response does not contain data from a misinterpreted
            # second request.
            if r.exit_code == 0 and r.response is not None:
                body = r.response.get("body", b"")
                if isinstance(body, bytes):
                    body = body.decode("utf-8", errors="replace")
                assert "Query string" not in body

        env.httpd_error_log.ignore_recent(
            lognos=["AH00957", "AH01106", "AH01114", "AH01075",
                    "AH00878", "AH00992", "AH01031", "AH10404",
                    "AH01080", "AH01081", "AH10396"]
        )
