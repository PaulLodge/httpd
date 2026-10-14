"""Basic digest authentication handshake.

Verifies the full round-trip of digest authentication: an unauthenticated
request receives a 401 challenge, a correctly computed Authorization header
grants access, and the response body is the expected protected content.
Also verifies that the same nonce can be reused with an incremented
nonce-count.
"""

from . import digest_client as dc
from .env import AAATestEnv


class TestDigestAuth:

    def url(self, env, path="secret.txt"):
        return env.mkurl("http", "aaa", "/digest/default/" + path)

    def challenge(self, env):
        r = env.curl_get(self.url(env))
        assert r.response["status"] == 401
        return dc.DigestChallenge.parse(r.response["header"]["www-authenticate"])

    def test_digest_014_01_unauthenticated_request_is_challenged(self, env):
        # A request with no credentials receives a 401 with a well-formed
        # Digest challenge containing the expected realm and parameters.
        r = env.curl_get(self.url(env))
        assert r.response["status"] == 401
        challenge = dc.DigestChallenge.parse(
            r.response["header"]["www-authenticate"])
        assert challenge.realm == AAATestEnv.REALM
        assert challenge.nonce is not None
        assert challenge.qop == "auth"

    def test_digest_014_02_full_handshake_grants_access(self, env):
        # After obtaining a challenge, a client which computes a correct
        # digest response is granted access and receives the protected
        # content.
        challenge = self.challenge(env)
        uri = "/digest/default/secret.txt"
        auth = dc.build_authorization(
            AAATestEnv.DIGEST_USER, challenge, AAATestEnv.DIGEST_PASSWORD,
            method="GET", uri=uri)
        r = env.curl_get(self.url(env), options=["-H", f"Authorization: {auth}"])
        assert r.response["status"] == 200
        assert b"digest-default-secret" in r.response["body"]

    def test_digest_014_03_nonce_reuse_with_incremented_nc(self, env):
        # A subsequent request reusing the same nonce but incrementing the
        # nonce-count must also succeed.
        challenge = self.challenge(env)
        uri = "/digest/default/secret.txt"

        auth1 = dc.build_authorization(
            AAATestEnv.DIGEST_USER, challenge, AAATestEnv.DIGEST_PASSWORD,
            method="GET", uri=uri, nc="00000001", cnonce="reuse-test-1")
        r1 = env.curl_get(self.url(env), options=["-H", f"Authorization: {auth1}"])
        assert r1.response["status"] == 200

        auth2 = dc.build_authorization(
            AAATestEnv.DIGEST_USER, challenge, AAATestEnv.DIGEST_PASSWORD,
            method="GET", uri=uri, nc="00000002", cnonce="reuse-test-2")
        r2 = env.curl_get(self.url(env), options=["-H", f"Authorization: {auth2}"])
        assert r2.response["status"] == 200
