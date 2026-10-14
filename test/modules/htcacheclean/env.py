import inspect
import logging
import os

from pyhttpd.env import HttpdTestEnv, HttpdTestSetup

log = logging.getLogger(__name__)


class HtcachecleanTestSetup(HttpdTestSetup):

    def __init__(self, env: 'HttpdTestEnv'):
        super().__init__(env=env)
        self.add_source_dir(os.path.dirname(
            inspect.getfile(HtcachecleanTestSetup)))
        self.add_modules(["cache", "cache_disk"])


class HtcachecleanTestEnv(HttpdTestEnv):

    def __init__(self, pytestconfig=None):
        super().__init__(pytestconfig=pytestconfig)
        self.add_httpd_log_modules(["cache", "cache_disk"])

    def setup_httpd(self, setup: HttpdTestSetup = None):
        super().setup_httpd(setup=HtcachecleanTestSetup(env=self))

    @property
    def htcacheclean(self) -> str:
        return os.path.join(self.bin_dir, "htcacheclean")
