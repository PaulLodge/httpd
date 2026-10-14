import inspect
import logging
import os

from pyhttpd.env import HttpdTestEnv, HttpdTestSetup

log = logging.getLogger(__name__)


class SessionTestSetup(HttpdTestSetup):

    def __init__(self, env: 'HttpdTestEnv'):
        super().__init__(env=env)
        self.add_source_dir(os.path.dirname(inspect.getfile(SessionTestSetup)))
        self.add_cgi_module()
        self.add_modules(["session", "session_cookie"])
        self.add_optional_modules(["session_crypto"])


class SessionTestEnv(HttpdTestEnv):

    def __init__(self, pytestconfig=None):
        super().__init__(pytestconfig=pytestconfig)
        log_modules = ["session", "core"]
        self.add_httpd_log_modules(log_modules)

    def setup_httpd(self, setup: HttpdTestSetup = None):
        super().setup_httpd(setup=SessionTestSetup(env=self))

    @property
    def has_session_crypto_module(self) -> bool:
        return self.has_shared_module("session_crypto")
