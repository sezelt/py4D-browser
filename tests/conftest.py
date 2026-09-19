"""
Shared fixtures for the py4D_browser test suite.

The tests run headless; Qt uses the offscreen platform plugin.
"""

import os

# Ensure Qt runs offscreen even if the user has not set this already.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile

import pytest


@pytest.fixture(scope="session")
def qapp():
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="session")
def viewer(qapp):
    """
    A fully constructed DataViewer, with the real sample plugins loaded,
    pointing at a throwaway config file so the tests never touch the
    user's real GUI settings.
    """
    import py4D_browser.main_window as mw
    from py4D_browser import DataViewer

    config_dir = tempfile.mkdtemp(prefix="py4dgui_test_")
    mp = pytest.MonkeyPatch()
    mp.setattr(
        mw.platformdirs,
        "user_config_dir",
        lambda appname, appauthor=None, roaming=False: config_dir,
    )
    v = DataViewer(reset_state=True)
    yield v
    mp.undo()
