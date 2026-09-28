"""
Tests for 3D volume tabs (API v1.7): a plugin tab in the virtual-image pane
that renders a 3D volume with pyqtgraph's OpenGL volume rendering, with
user-adjustable color/alpha transfer functions.

These tests exercise construction and state only — the GL view is never
painted (the test suite runs on the offscreen platform, where QOpenGLWidget
is unsupported).
"""

import numpy as np
import pytest

pytest.importorskip("OpenGL")

from py4D_browser.plugin_api import PluginAPI  # noqa: E402
from py4D_browser.volume_tabs import VolumeTab  # noqa: E402


########## creation and selection ##########


def test_create_volume_tab(viewer):
    from PyQt5.QtWidgets import QTabBar, QSplitter

    api = PluginAPI(viewer)
    tab_widget = viewer.virtual_image_tab_widget

    # before: only the default tab exists and the tab bar is hidden
    assert tab_widget.count() == 1
    assert tab_widget.tabBar().isHidden()

    # the API exposes create_volume_tab (new in v1.7)
    assert api.create_volume_tab is not None

    tab = api.create_volume_tab("Vol")
    try:
        # default tab (index 0) + the new volume tab (index 1)
        assert tab_widget.count() == 2
        assert tab_widget.widget(0) is viewer.real_space_widget
        assert tab_widget.widget(1) is tab.widget

        # the tab's backing widget is a QSplitter (3D view + editor panel),
        # not a pyqtgraph.ImageView like an image tab's
        assert isinstance(tab.widget, QSplitter)
        assert isinstance(tab, VolumeTab)

        # labeled, tracked, and given a close button
        assert tab_widget.tabText(1) == "Vol"
        assert not tab_widget.tabBar().isHidden()
        assert api.virtual_image_tabs == [tab]
        assert viewer.virtual_image_tabs == [tab]
        assert tab_widget.tabBar().tabButton(1, QTabBar.RightSide) is not None

        # not auto-selected: the built-in pane stays on display
        assert tab_widget.currentIndex() == 0
    finally:
        api.close_virtual_image_tab(tab)

    # after closing: back to a single (default) tab, tab bar hidden again
    assert tab_widget.count() == 1
    assert tab_widget.tabBar().isHidden()
    assert api.virtual_image_tabs == []


def test_create_volume_tab_select_switches_pane(viewer):
    api = PluginAPI(viewer)
    tab_widget = viewer.virtual_image_tab_widget
    tab = api.create_volume_tab("Vol", select=True)
    try:
        assert tab_widget.currentIndex() == 1
    finally:
        api.close_virtual_image_tab(tab)
    assert tab_widget.currentIndex() == 0


########## set_volume / set_levels ##########


def test_set_volume_stores_array_and_rejects_bad_input(viewer):
    api = PluginAPI(viewer)
    tab = api.create_volume_tab("Vol")
    try:
        # non-3D arrays are rejected
        with pytest.raises(ValueError):
            tab.set_volume(np.ones((4, 4), dtype=np.float32))
        # complex arrays are rejected
        with pytest.raises(ValueError):
            tab.set_volume(np.ones((4, 4, 4), dtype=np.complex64))

        vol = np.random.default_rng(0).random((8, 8, 8), dtype=np.float32)
        tab.set_volume(vol)

        # the raw array is stored (and aliased as `image`, so the tab is
        # interchangeable with an image tab where a tab's array is read)
        assert tab.volume is vol
        assert tab.image is vol
    finally:
        api.close_virtual_image_tab(tab)


def test_set_volume_derives_levels_in_range(viewer):
    api = PluginAPI(viewer)
    tab = api.create_volume_tab("Vol")
    try:
        assert tab.levels is None
        vol = np.random.default_rng(0).random((8, 8, 8), dtype=np.float32)
        tab.set_volume(vol)

        # with reset (the default), levels are derived from the data
        lo, hi = tab.levels
        assert vol.min() <= lo <= hi <= vol.max()

        # set_levels overrides them
        tab.set_levels(0.25, 0.75)
        assert tab.levels == (0.25, 0.75)
    finally:
        api.close_virtual_image_tab(tab)


########## transfer-function editors ##########


def test_editors_are_gradient_items_with_expected_luts(viewer):
    from pyqtgraph.graphicsItems.GradientEditorItem import GradientEditorItem

    api = PluginAPI(viewer)
    tab = api.create_volume_tab("Vol")
    try:
        assert isinstance(tab.color_editor, GradientEditorItem)
        assert isinstance(tab.alpha_editor, GradientEditorItem)

        # color LUT: (256, 3) uint8; alpha LUT: (256, 4) uint8
        color_lut = tab.color_editor.getLookupTable(256, alpha=False)
        assert color_lut.shape == (256, 3)
        assert color_lut.dtype == np.ubyte

        alpha_lut = tab.alpha_editor.getLookupTable(256, alpha=True)
        assert alpha_lut.shape == (256, 4)
        assert alpha_lut.dtype == np.ubyte

        # a fresh tab is seeded transparent at the low end, opaque at the
        # high end
        assert alpha_lut[0, 3] == 0
        assert alpha_lut[-1, 3] == 255
    finally:
        api.close_virtual_image_tab(tab)


########## current_virtual_image tracking ##########


def test_current_virtual_image_tracks_visible_volume_tab(viewer):
    api = PluginAPI(viewer)
    vol = np.random.default_rng(0).random((8, 8, 8), dtype=np.float32)
    tab = api.create_volume_tab("Vol")
    tab.set_volume(vol)

    fired = []
    handler = lambda: fired.append(True)
    try:
        viewer.signal_current_virtual_image_changed.connect(handler)

        # default tab visible: the built-in (empty) image
        assert viewer.virtual_image_tab_widget.currentIndex() == 0
        assert viewer.current_virtual_image is viewer.unscaled_realspace_image

        # switching to the volume tab exposes its 3D array and fires the signal
        viewer.virtual_image_tab_widget.setCurrentIndex(1)
        assert viewer.current_virtual_image is vol
        assert api.current_virtual_image is vol
        assert fired == [True]

        # set_volume on the visible tab also fires the signal
        fired.clear()
        vol2 = np.full((8, 8, 8), 7.0, dtype=np.float32)
        tab.set_volume(vol2)
        assert viewer.current_virtual_image is vol2
        assert fired == [True]
    finally:
        viewer.signal_current_virtual_image_changed.disconnect(handler)
        api.close_virtual_image_tab(tab)


########## closing ##########


def test_close_volume_tab_cleans_up(viewer):
    api = PluginAPI(viewer)
    tab = api.create_volume_tab("Vol")
    tab.set_volume(np.random.default_rng(0).random((8, 8, 8), dtype=np.float32))

    try:
        assert viewer.virtual_image_tab_widget.count() == 2
        assert api.virtual_image_tabs == [tab]

        api.close_virtual_image_tab(tab)

        # removed from the pane and from the tracked list
        assert viewer.virtual_image_tab_widget.count() == 1
        assert api.virtual_image_tabs == []

        # the tab is marked closed, and mutating it now raises
        assert tab.closed
        with pytest.raises(RuntimeError):
            tab.set_volume(np.zeros((2, 2, 2), dtype=np.float32))
        with pytest.raises(RuntimeError):
            tab.set_levels(0.0, 1.0)
    finally:
        # idempotent: a second close is a harmless no-op
        api.close_virtual_image_tab(tab)
        tab.close()  # ... and tab.close() routes through the same path


########## GL view contents ##########


def test_view_contains_grid_axis_and_then_volume(viewer):
    api = PluginAPI(viewer)
    tab = api.create_volume_tab("Vol")
    try:
        # before any volume: just the orientation aids (grid + axis)
        assert len(tab.view.items) == 2
        assert tab.grid in tab.view.items
        assert tab.axis in tab.view.items

        # set_volume adds the GLVolumeItem (the 3D texture itself is only
        # uploaded at paint time, which never happens in these tests)
        tab.set_volume(np.random.default_rng(0).random((8, 8, 8), dtype=np.float32))
        assert len(tab.view.items) == 3
    finally:
        api.close_virtual_image_tab(tab)


def test_volume_tab_has_no_set_image(viewer):
    # Duck-check guidance for plugins: a volume tab is driven by
    # set_volume, not set_image (and vice versa for image tabs).
    api = PluginAPI(viewer)
    tab = api.create_volume_tab("Vol")
    try:
        assert hasattr(tab, "set_volume")
        assert not hasattr(tab, "set_image")
    finally:
        api.close_virtual_image_tab(tab)
