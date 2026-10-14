import os
import re

import pytest

from pyhttpd.conf import HttpdConf


class TestCheckBasename:
    """Test mod_speling CheckBasenameMatch behaviour.

    When CheckSpelling is On and there are files that share the same
    basename but differ in extension (e.g. test-cgi.bat and test-cgi.sh),
    a request for the bare basename (/test-cgi, no extension) should:
      - return 300 (Multiple Choices) when CheckBasenameMatch is On
      - return 404 when CheckBasenameMatch is Off

    The default for CheckBasenameMatch changed to On in httpd 2.4.50.
    """

    SPELLING_DIR = "spellingTest"

    @pytest.fixture(autouse=True, scope='class')
    def _class_scope(self, env):
        if not env.has_shared_module("speling"):
            pytest.skip("mod_speling not available")
        # Create a test directory with two files that share a basename
        # but have different extensions.
        doc_dir = os.path.join(env.server_dir, "htdocs", "test1",
                               self.SPELLING_DIR)
        os.makedirs(doc_dir, exist_ok=True)
        for fname in ("test-cgi.bat", "test-cgi.sh"):
            path = os.path.join(doc_dir, fname)
            with open(path, "w") as f:
                f.write(f"placeholder for {fname}\n")

    def _configure(self, env, check_spelling="On", check_case_only=None,
                   check_basename=None):
        """Write an httpd config with the given mod_speling directives."""
        directives = f"CheckSpelling {check_spelling}\n"
        if check_case_only is not None:
            directives += f"CheckCaseOnly {check_case_only}\n"
        if check_basename is not None:
            directives += f"CheckBasenameMatch {check_basename}\n"

        conf = HttpdConf(env, extras={
            f"test1.{env.http_tld}": directives,
        })
        conf.add_vhost_test1()
        conf.install()
        assert env.apache_restart() == 0

    # -- CheckBasenameMatch On: basename-only differences produce 300 --

    def test_spelling_002_01_basename_on_case_on_300(self, env):
        """CheckBasenameMatch On, CheckCaseOnly On: requesting a bare
        basename returns 300 with suggestions."""
        self._configure(env, check_basename="On", check_case_only="On")
        url = env.mkurl("http", "test1",
                         f"/{self.SPELLING_DIR}/test-cgi")
        r = env.curl_get(url, options=["--max-redirs", "0"])
        assert r.response["status"] == 300, \
            "Expected 300 with CheckBasenameMatch On + CheckCaseOnly On"

    def test_spelling_002_02_basename_on_case_off_300(self, env):
        """CheckBasenameMatch On, CheckCaseOnly Off: requesting a bare
        basename returns 300 with suggestions."""
        self._configure(env, check_basename="On", check_case_only="Off")
        url = env.mkurl("http", "test1",
                         f"/{self.SPELLING_DIR}/test-cgi")
        r = env.curl_get(url, options=["--max-redirs", "0"])
        assert r.response["status"] == 300, \
            "Expected 300 with CheckBasenameMatch On + CheckCaseOnly Off"

    # -- CheckBasenameMatch Off: basename-only differences yield 404 --

    def test_spelling_002_03_basename_off_case_on_404(self, env):
        """CheckBasenameMatch Off (explicit), CheckCaseOnly On: requesting
        a bare basename returns 404."""
        self._configure(env, check_basename="Off", check_case_only="On")
        url = env.mkurl("http", "test1",
                         f"/{self.SPELLING_DIR}/test-cgi")
        r = env.curl_get(url, options=["--max-redirs", "0"])
        assert r.response["status"] == 404, \
            "Expected 404 with CheckBasenameMatch Off + CheckCaseOnly On"

    def test_spelling_002_04_basename_off_case_off_404(self, env):
        """CheckBasenameMatch Off (explicit), CheckCaseOnly Off: requesting
        a bare basename returns 404."""
        self._configure(env, check_basename="Off", check_case_only="Off")
        url = env.mkurl("http", "test1",
                         f"/{self.SPELLING_DIR}/test-cgi")
        r = env.curl_get(url, options=["--max-redirs", "0"])
        assert r.response["status"] == 404, \
            "Expected 404 with CheckBasenameMatch Off + CheckCaseOnly Off"

    # -- Verify the 300 response body contains the expected suggestions --

    def test_spelling_002_05_300_lists_alternatives(self, env):
        """When CheckBasenameMatch is On and the response is 300, the body
        should list both .bat and .sh alternatives."""
        self._configure(env, check_basename="On", check_case_only="On")
        url = env.mkurl("http", "test1",
                         f"/{self.SPELLING_DIR}/test-cgi")
        r = env.curl_get(url, options=["--max-redirs", "0"])
        assert r.response["status"] == 300

        body = r.response["body"].decode("utf-8")
        pattern = re.compile(r"test-cgi\.(bat|sh)")
        matches = pattern.findall(body)
        assert len(matches) >= 2, \
            f"Expected both .bat and .sh suggestions in body, found: {matches}"

    def test_spelling_002_06_404_no_suggestions(self, env):
        """When CheckBasenameMatch is Off and the response is 404, the body
        should not contain file suggestions."""
        self._configure(env, check_basename="Off", check_case_only="Off")
        url = env.mkurl("http", "test1",
                         f"/{self.SPELLING_DIR}/test-cgi")
        r = env.curl_get(url, options=["--max-redirs", "0"])
        assert r.response["status"] == 404

        body = r.response["body"].decode("utf-8")
        pattern = re.compile(r"test-cgi\.(bat|sh)")
        assert not pattern.search(body), \
            "Response body should not contain file suggestions with " \
            "CheckBasenameMatch Off"

        env.httpd_error_log.ignore_recent(lognos=["AH01264"])
