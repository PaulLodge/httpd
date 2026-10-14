"""Malformed digest authorization headers must not leak data.

Sends a deliberately malformed Digest Authorization header and verifies
that the server responds with 401 without exposing uninitialized or
unexpected data in the response headers or the error log.
"""

from . import digest_client as dc
from .env import AAATestEnv


class TestDigestResponseHeaders:

    def url(self, env):
        return env.mkurl("http", "aaa", "/digest/default/secret.txt")

    def test_digest_015_01_malformed_header_returns_401(self, env):
        # A Digest Authorization header with missing or malformed fields
        # (no proper realm quoting, bogus nonce, no uri, bad response
        # format) must be cleanly rejected with a 401 and a fresh
        # challenge, without leaking data.
        malformed_auth = (
            'Digest username, realm="' + AAATestEnv.REALM + '", '
            'nonce=a, uri=/digest/default/secret.txt, '
            'digest=a, cnonce=a, nonce_count=10, response=A'
        )
        r = env.curl_get(self.url(env),
                         options=["-H", f"Authorization: {malformed_auth}"])
        assert r.response["status"] == 401
        # The response must carry a valid Digest challenge so a
        # well-behaved client can retry.
        challenge = dc.DigestChallenge.parse(
            r.response["header"]["www-authenticate"])
        assert challenge.realm == AAATestEnv.REALM
        env.httpd_error_log.ignore_recent(lognos=["AH01782"])

    def test_digest_015_02_no_leaked_fill_bytes_in_error_log(self, env):
        # When httpd processes a malformed Digest header, no fill-pattern
        # bytes (e.g. repeated 0x41 from a valgrind malloc-fill) should
        # appear in the error log, which would indicate uninitialized
        # memory being read.
        #
        # Read the current end-of-log position, send the malformed
        # request, then check the new lines for the fill pattern.
        log_pos = env.httpd_error_log.current_pos()
        malformed_auth = (
            'Digest username, realm="' + AAATestEnv.REALM + '", '
            'nonce=a, uri=/digest/default/secret.txt, '
            'digest=a, cnonce=a, nonce_count=10, response=A'
        )
        r = env.curl_get(self.url(env),
                         options=["-H", f"Authorization: {malformed_auth}"])
        assert r.response["status"] == 401
        # Check the error log lines written since log_pos do not contain
        # a run of 'A' characters that would indicate leaked
        # uninitialized memory (the valgrind malloc fill pattern
        # 0x41 = 'A').
        with open(env.httpd_error_log.path) as fd:
            fd.seek(log_pos)
            for line in fd:
                assert "AAAA" not in line, \
                    f"possible uninitialized memory leak in error log: {line}"
        env.httpd_error_log.ignore_recent(lognos=["AH01782"])

    def test_digest_015_03_response_headers_are_printable(self, env):
        # After a malformed Authorization, the response headers must not
        # contain raw or binary data outside the expected Digest challenge
        # parameters.
        malformed_auth = (
            'Digest username="x", realm="wrong", '
            'nonce="bad", uri="/digest/default/secret.txt", '
            'response="' + ("41" * 16) + '", qop=auth, '
            'nc=00000001, cnonce="test"'
        )
        r = env.curl_get(self.url(env),
                         options=["-H", f"Authorization: {malformed_auth}"])
        assert r.response["status"] == 401
        www_auth = r.response["header"]["www-authenticate"]
        # The WWW-Authenticate value must start with "Digest " and contain
        # only printable ASCII characters.
        assert www_auth.startswith("Digest ")
        assert all(32 <= ord(c) < 127 for c in www_auth), \
            f"non-printable characters in WWW-Authenticate: {www_auth!r}"
        env.httpd_error_log.ignore_recent(lognos=["AH01782", "AH01788",
                                                   "AH01776", "AH01794"])
