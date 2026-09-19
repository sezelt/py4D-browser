"""
The versioned plugin API for py4DGUI.

Plugins declare which version of this API they were written against with a
class-level attribute::

    api_version = (1, 0)

The loader resolves that against :data:`SUPPORTED_API_VERSIONS` and passes
the plugin an instance of the matching API class. Within a major version the
API is only ever extended: existing methods keep their signatures and
behavior, so a plugin written against an older minor version of a major
continues to work.

Multiple major versions coexist: when a new major version is introduced, the
old class is kept in the registry so that plugins written against it keep
loading. The API objects are the "glue" between plugins and the DataViewer:
their outgoing interface is stable for the lifetime of the major version,
while their implementation (which calls into the viewer) may be updated as
the GUI evolves.

Plugins must declare ``api_version``; a plugin that does not, or that
requires a version this browser does not provide, is logged and skipped.
Plugins that set ``full_access = True`` additionally receive the raw
``DataViewer`` as ``parent`` (bypassing the versioned surface); everyone
else interacts with the browser solely through the API object passed as
``api``.
"""

from functools import partial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from py4D_browser.main_window import DataViewer

__all__ = [
    "API_VERSION",
    "PluginAPI",
    "PluginAPI1",
    "PluginAPIVersionError",
    "SUPPORTED_API_VERSIONS",
    "resolve_api_class",
]


class PluginAPIVersionError(Exception):
    """
    Raised when a plugin declares an API version that this browser does not
    provide, i.e. the plugin is newer than the GUI.
    """


class PluginAPI1:
    """
    The version 1.0 plugin API.

    Instances are created by the loader (or by hand for testing) with a
    reference to the DataViewer, and passed to plugins as ``api``. All
    state lives in the viewer; this object is a thin, stable facade over it.
    """

    api_version = (1, 0)

    def __init__(self, viewer: "DataViewer"):
        # Hold a strong reference to the viewer; the API is a facade over it.
        self._viewer = viewer

        # Signals: direct references to the viewer's bound signals, so
        # connecting/disconnecting through the API acts on the same signal.
        self.signal_diffraction_data_changed = (
            viewer.signal_diffraction_data_changed
        )
        self.signal_virtual_image_data_changed = (
            viewer.signal_virtual_image_data_changed
        )
        self.signal_datacube_changed = viewer.signal_datacube_changed

        # Pane setters: bound to the viewer; signatures match the
        # corresponding DataViewer methods (see update_views.py).
        self.set_virtual_image = partial(viewer.set_virtual_image)
        self.set_diffraction_image = partial(viewer.set_diffraction_image)
        self.set_result_image = partial(viewer.set_result_image)
        self.set_scalebar = partial(viewer.set_scalebar)

        # Replace the currently loaded datacube (see set_datacube in
        # menu_actions.py). `refresh` (default True) triggers the normal
        # post-load machinery: view resets + signal_datacube_changed.
        self.set_datacube = partial(viewer.set_datacube)

        # Detector getters (see "Accessing the detectors" in PLUGINS.md)
        self.get_diffraction_detector = partial(viewer.get_diffraction_detector)
        self.get_virtual_image_detector = partial(viewer.get_virtual_image_detector)

        # Qt plumbing
        self.qtapp = viewer.qtapp
        # The DataViewer itself; use it only as the parent widget for dialogs,
        # e.g. QDialog(parent=api.qt_window).
        self.qt_window = viewer
        self.status_bar = viewer.statusBar()
        # QSettings object; only write under a top-level section named
        # after your plugin_id.
        self.settings = viewer.settings

    @property
    def datacube(self):
        """
        The currently loaded DataCube (read-only through the API).
        Mutating the cube object itself is fine; to replace the whole
        cube, use ``set_datacube``.
        """
        return self._viewer.datacube

    @datacube.setter
    def datacube(self, value):
        raise AttributeError(
            "The datacube cannot be assigned; use "
            "api.set_datacube(datacube) to replace the currently loaded "
            "datacube."
        )


# Major version -> (highest minor version provided, API class).
# New major versions are added here; older ones are kept so that plugins
# written against them continue to load.
SUPPORTED_API_VERSIONS = {
    1: (0, PluginAPI1),
}

# The newest API version provided by this browser.
API_VERSION = (
    max(SUPPORTED_API_VERSIONS),
    SUPPORTED_API_VERSIONS[max(SUPPORTED_API_VERSIONS)][0],
)

# Convenience alias for the latest API class.
PluginAPI = SUPPORTED_API_VERSIONS[API_VERSION[0]][1]


def resolve_api_class(api_version):
    """
    Return the API class to serve a plugin requiring the ``(major, minor)``
    ``api_version``, or raise :class:`PluginAPIVersionError` if this browser
    does not provide it (major absent, or minor ahead of the latest).

    A minor version at or below the latest for a major is compatible: within
    a major the API is only ever extended.
    """
    try:
        major, minor = int(api_version[0]), int(api_version[1])
    except (TypeError, ValueError, IndexError, KeyError) as exc:
        raise PluginAPIVersionError(
            f"api_version must be a (major, minor) pair of integers, "
            f"got {api_version!r}"
        ) from exc

    entry = SUPPORTED_API_VERSIONS.get(major)
    if entry is None:
        supported = ", ".join(
            f"v{major}.{minor}"
            for major, (minor, _) in sorted(SUPPORTED_API_VERSIONS.items())
        )
        raise PluginAPIVersionError(
            f"requires API v{major}.{minor}, but this browser only provides "
            f"{supported}. Please upgrade py4D_browser to a version that "
            "provides it."
        )

    latest_minor, cls = entry
    if minor > latest_minor:
        raise PluginAPIVersionError(
            f"requires API v{major}.{minor}, but this browser only provides "
            f"v{major}.{latest_minor}. Please upgrade py4D_browser to a "
            "version that provides it."
        )

    return cls
