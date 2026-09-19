"""
Tests for the versioned plugin API (py4D_browser.plugin_api).

The pure version-resolution logic is tested without Qt; the API surface
and behavior tests use the session-scoped DataViewer fixture from
conftest.py.
"""

import numpy as np
import pytest

from py4D_browser.plugin_api import (
    API_VERSION,
    PluginAPI,
    PluginAPI1,
    PluginAPIVersionError,
    SUPPORTED_API_VERSIONS,
    resolve_api_class,
)


########## Version resolution (pure logic, no Qt) ##########


@pytest.mark.parametrize(
    "requested",
    [
        (1, 0),
        (1, 0, 0),  # extra entries beyond (major, minor) are ignored
        [1, 0],  # any indexable (major, minor) pair works
    ],
)
def test_resolve_compatible_versions(requested):
    assert resolve_api_class(requested) is PluginAPI1
    assert resolve_api_class((1, 0)) is PluginAPI  # latest alias


@pytest.mark.parametrize(
    "requested",
    [
        (1, 1),  # minor ahead of the latest 1.x
        (1, 9),
        (2, 0),  # major not provided at all
        (99, 0),
    ],
)
def test_resolve_unsupported_versions_raises(requested):
    with pytest.raises(PluginAPIVersionError):
        resolve_api_class(requested)


@pytest.mark.parametrize(
    "requested",
    [
        1,
        (1,),
        (),
        "1.0",
        None,
        (None, None),
        {},
    ],
)
def test_resolve_bad_shapes_raise(requested):
    with pytest.raises(PluginAPIVersionError, match="api_version must be"):
        resolve_api_class(requested)


def test_error_message_names_both_versions():
    with pytest.raises(PluginAPIVersionError, match=r"v1\.9") as excinfo:
        resolve_api_class((1, 9))
    assert "v1.0" in str(excinfo.value)  # the version the browser provides


def test_registry_and_api_version_agree():
    assert API_VERSION == (1, 0)
    assert PluginAPI is SUPPORTED_API_VERSIONS[1][1]
    assert PluginAPI1.api_version == (1, 0)


########## API surface ##########


def test_api_exposes_v1_surface(viewer):
    api = PluginAPI(viewer)

    assert api.api_version == (1, 0)

    # datacube is readable (None: no dataset loaded)
    assert api.datacube is viewer.datacube

    # The API's signals are the viewer's underlying signals: connecting
    # through the API must fire when the viewer's signal is emitted.
    # (PyQt5 returns a fresh bound-signal proxy per attribute access, so
    # identity comparison is not meaningful here; check behavior instead.)
    for name in (
        "signal_diffraction_data_changed",
        "signal_virtual_image_data_changed",
        "signal_datacube_changed",
    ):
        fired = []

        def handler():  # signals are no-arg; a plain function, not list.append
            fired.append(True)

        api_sig = getattr(api, name)
        viewer_sig = getattr(viewer, name)
        api_sig.connect(handler)
        try:
            viewer_sig.emit()
            assert fired == [True], name
        finally:
            api_sig.disconnect(handler)

    # pane setters, datacube replacement, and detector getters are callable
    for attr in (
        "set_virtual_image",
        "set_diffraction_image",
        "set_result_image",
        "set_scalebar",
        "set_datacube",
        "get_diffraction_detector",
        "get_virtual_image_detector",
    ):
        assert callable(getattr(api, attr)), attr

    # Qt plumbing
    assert api.qtapp is viewer.qtapp
    assert api.qt_window is viewer
    assert api.status_bar is viewer.statusBar()
    assert api.settings is viewer.settings


def test_datacube_assignment_is_rejected(viewer):
    api = PluginAPI(viewer)
    with pytest.raises(AttributeError, match="cannot be assigned"):
        api.datacube = object()


########## Datacube replacement (set_datacube) ##########


def _make_datacube():
    import py4DSTEM

    return py4DSTEM.DataCube(np.zeros((2, 2, 4, 4), dtype=np.float32))


def test_set_datacube_replaces_and_refreshes_by_default(viewer):
    api = PluginAPI(viewer)

    original = viewer.datacube
    fired = []
    handler = lambda: fired.append(True)

    cube = _make_datacube()
    api.signal_datacube_changed.connect(handler)
    try:
        api.set_datacube(cube)
        assert viewer.datacube is cube
        # refresh=True is the default: the load machinery ran, which
        # includes emitting signal_datacube_changed.
        assert fired == [True]
    finally:
        api.signal_datacube_changed.disconnect(handler)
        viewer.datacube = original


def test_set_datacube_refresh_false_skips_machinery(viewer):
    api = PluginAPI(viewer)

    original = viewer.datacube
    fired = []
    handler = lambda: fired.append(True)

    cube = _make_datacube()
    api.signal_datacube_changed.connect(handler)
    try:
        api.set_datacube(cube, refresh=False)
        # the cube is still swapped in ...
        assert viewer.datacube is cube
        # ... but the refresh machinery (view resets + signal) did not run.
        assert fired == []
    finally:
        api.signal_datacube_changed.disconnect(handler)
        viewer.datacube = original


########## Pane setters (behavior through the API object) ##########


def test_set_virtual_image(viewer):
    api = PluginAPI(viewer)
    vimg = np.arange(64, dtype=np.float32).reshape(8, 8)

    api.set_virtual_image(vimg, reset=True, pixel_size=0.5, pixel_units="nm")

    assert viewer.unscaled_realspace_image is vimg
    assert viewer.real_space_scale_bar.pixel_size == 0.5
    assert viewer.real_space_scale_bar.units == "nm"


def test_set_diffraction_image(viewer):
    api = PluginAPI(viewer)
    DP = np.arange(64, dtype=np.float32).reshape(8, 8)

    api.set_diffraction_image(DP, reset=True, pixel_size=0.25, pixel_units="mrad")

    assert viewer.unscaled_diffraction_image is DP
    assert viewer.diffraction_scale_bar.pixel_size == 0.25
    assert viewer.diffraction_scale_bar.units == "mrad"


def test_set_result_image(viewer):
    api = PluginAPI(viewer)
    fft = np.arange(64, dtype=np.float32).reshape(8, 8)

    api.set_result_image(
        fft, reset=True, pixel_size=2.0, pixel_units="nm^-1", title="test result"
    )

    assert viewer.unscaled_fft_image is fft
    assert viewer.fft_scale_bar.pixel_size == 2.0
    assert viewer.fft_scale_bar.units == "nm^-1"
    assert viewer.fft_widget_text.toPlainText() == "test result"


def test_set_scalebar_updates_each_view(viewer):
    api = PluginAPI(viewer)

    cases = [
        ("diffraction", viewer.diffraction_scale_bar),
        ("real_space", viewer.real_space_scale_bar),
        ("result", viewer.fft_scale_bar),
    ]
    for view_name, scale_bar in cases:
        api.set_scalebar(view_name, 1.5, "nm")
        assert scale_bar.pixel_size == 1.5
        assert scale_bar.units == "nm"


def test_set_scalebar_unknown_view_raises(viewer):
    api = PluginAPI(viewer)
    with pytest.raises(ValueError, match="Unknown view"):
        api.set_scalebar("not_a_view", 1.0, "nm")


########## Signal wiring through the API object ##########


def test_signals_fire_through_api(viewer):
    api = PluginAPI(viewer)

    fired = []

    def handler():
        fired.append(True)

    api.signal_virtual_image_data_changed.connect(handler)
    try:
        api.set_virtual_image(np.zeros((4, 4), dtype=np.float32), reset=True)
        assert fired == [True]
    finally:
        api.signal_virtual_image_data_changed.disconnect(handler)
