"""
The virtual-image tab: an independent display pane a plugin can drive to show
its own image alongside the built-in virtual image, without overwriting it.

A :class:`VirtualImageTab` wraps a ``pyqtgraph.ImageView`` and its own
:class:`~py4D_browser.scalebar.ScaleBar`, and tracks any pyqtgraph ROIs and
annotations a plugin attaches to it. It is created and owned by the
:class:`~py4D_browser.main_window.DataViewer` (see
``create_virtual_image_tab`` / ``close_virtual_image_tab``), which is what
performs the actual add/remove of the tab in the pane and tears the tab down
(cleanly detaching its ROIs/annotations) when the user closes it.

Rendering is deliberately "raw": unlike the built-in virtual image, a tab's
image is **not** passed through the browser's Linear/Log/Square-Root scaling
group, so a plugin's output is displayed as-is.
"""

from typing import Optional

import numpy as np
from PyQt5 import QtCore

import pyqtgraph as pg

from py4D_browser.scalebar import ScaleBar
from py4D_browser.utils import complex_to_Lab, format_unit, try_get_cmap


class VirtualImageTab(QtCore.QObject):
    """
    A single virtual-image tab.

    Instances are created by the ``DataViewer`` (via
    ``create_virtual_image_tab``) and returned to the plugin. A plugin drives
    its display through :meth:`set_image`, :meth:`set_scalebar`, and
    :meth:`add_roi` / :meth:`add_annotation`, and tears it down with
    :meth:`close` (or by the user closing the tab, which routes here via the
    viewer). All state lives in the tab's own widget; the viewer only keeps a
    reference for bookkeeping.

    Parameters
    ----------
    title : str
        The text shown on the tab's label.
    viewer : DataViewer
        The owning window; used to update the tab's label and to route
        :meth:`close` through the viewer's teardown path.
    """

    # Emitted (with the tab itself as the argument) after :meth:`set_image`.
    signal_data_changed = QtCore.pyqtSignal(object)

    def __init__(self, title: str, viewer: "DataViewer"):
        super().__init__()
        self._viewer = viewer
        self._title = title
        self._closed = False
        self._image: Optional[np.ndarray] = None

        # An independent display pane, mirroring the built-in real-space
        # widget: menu disabled, and a scale bar anchored to the lower-right.
        self._widget = pg.ImageView()
        self._widget.getView().setMenuEnabled(False)

        self._scale_bar = ScaleBar(pixel_size=1, units="px", width=10)
        self._scale_bar.setParentItem(self._widget.getView())
        self._scale_bar.anchor((1, 1), (1, 1), offset=(-40, -40))

        # Tracked so the viewer can detach them cleanly on close.
        self._rois = []
        self._annotations = []

    ########## read-only surface ##########

    @property
    def widget(self):
        """The underlying ``pyqtgraph.ImageView`` backing this tab."""
        return self._widget

    @property
    def title(self):
        return self._title

    @title.setter
    def title(self, value: str):
        self._title = value
        if not self._closed and self._viewer is not None:
            self._viewer._update_tab_title(self)

    @property
    def image(self):
        """The raw array last passed to :meth:`set_image` (or ``None``)."""
        return self._image

    @property
    def scale_bar(self):
        """The tab's own :class:`ScaleBar` object (prefer :meth:`set_scalebar`)."""
        return self._scale_bar

    @property
    def colormap(self):
        """
        The tab's active pyqtgraph colormap (a ``pg.ColorMap`` object, or
        ``None`` if the tab is using pyqtgraph's default).

        Each tab keeps its own colormap. A new tab is seeded with the browser's
        default virtual-image colormap (the ``gui/realspace_colormap`` setting,
        the same default the built-in pane starts with — see
        ``create_virtual_image_tab``). Set this property (a ``pg.ColorMap`` or a
        colormap name) to change the tab independently of the other panes.
        """
        return self._widget.getImageItem()._colorMap

    @colormap.setter
    def colormap(self, value):
        """
        Set the tab's colormap. ``value`` may be a ``pyqtgraph.ColorMap`` or a
        colormap name (resolved via the browser's colormap lookup). ``None``
        is ignored.
        """
        if self._closed:
            raise RuntimeError(
                "Cannot set the colormap of a closed virtual-image tab."
            )
        if value is None:
            return
        cmap = value
        if isinstance(cmap, str):
            cmap = try_get_cmap(cmap)
        if cmap is None:
            raise ValueError(f"Unknown colormap: {value!r}")
        self._widget.getImageItem().setColorMap(cmap)

    @property
    def rois(self):
        """A copy of the list of ROIs attached via :meth:`add_roi`."""
        return list(self._rois)

    @property
    def annotations(self):
        """A copy of the list of annotations attached via :meth:`add_annotation`."""
        return list(self._annotations)

    ########## display ##########

    def set_image(
        self,
        image,
        reset: bool = True,
        pixel_size: Optional[float] = None,
        pixel_units: Optional[str] = None,
    ):
        """
        Set the raw image displayed in this tab.

        Parameters
        ----------
        image : array_like
            A real 2D array, or a complex 2D array (rendered as an RGB
            Lab-derived image, mirroring the built-in virtual image).
        reset : bool
            If True, re-derive the display level range from the data.
        pixel_size, pixel_units : optional
            If given, also update the tab's scale bar.
        """
        if self._closed:
            raise RuntimeError(
                "Cannot set the image of a closed virtual-image tab."
            )

        self._image = image
        self._render(reset=reset)
        if pixel_size is not None or pixel_units is not None:
            self.set_scalebar(pixel_size, pixel_units)

        self.signal_data_changed.emit(self)

        # If this tab is the one currently on display, tell the result
        # machinery (and any listeners) that the visible virtual image
        # changed. The built-in path emits the same signal in
        # ``set_virtual_image``; this is the tab's equivalent.
        if self._viewer is not None and self._viewer.is_virtual_image_tab_visible(self):
            self._viewer.signal_current_virtual_image_changed.emit()

    def _render(self, reset: bool = False):
        image = self._image
        if image is None:
            return

        # Mirrors the built-in ``_render_virtual_image`` (update_views.py),
        # except that the user's Linear/Log/Square-Root scaling group is not
        # applied: a plugin tab renders its image raw.
        if np.iscomplexobj(image):
            new_view = complex_to_Lab(image)
            self._widget.setImage(
                np.transpose(new_view, (1, 0, 2)),  # flip x/y but keep RGB ordering
                autoLevels=False,
                levels=(0, 1),
                autoRange=bool(reset),
            )
        else:
            new_view = np.asarray(image)
            if reset and self._viewer is not None:
                # Respect the user's configured real-space autoscale percentiles
                # (same range the built-in virtual image uses), rather than the
                # full min/max that pyqtgraph's default autoLevels would pick.
                p0, p1 = self._viewer.real_space_autoscale_percentiles
                levels = (
                    float(np.percentile(new_view, p0)),
                    float(np.percentile(new_view, p1)),
                )
                self._widget.setImage(
                    new_view.T, autoLevels=False, levels=levels, autoRange=True
                )
            elif reset:
                # No owning viewer (defensive): fall back to full autorange.
                self._widget.setImage(new_view.T, autoLevels=True, autoRange=True)
            else:
                # reset=False: keep the tab's existing levels.
                self._widget.setImage(new_view.T, autoLevels=False, autoRange=False)

    def set_scalebar(
        self, pixel_size: Optional[float] = None, units: Optional[str] = None
    ):
        """
        Update this tab's scale bar. Either ``pixel_size`` and/or ``units``
        may be ``None`` to leave that field unchanged.
        """
        if self._closed:
            raise RuntimeError(
                "Cannot update the scale bar of a closed virtual-image tab."
            )
        if pixel_size is not None:
            self._scale_bar.pixel_size = pixel_size
        if units is not None:
            # Translate ASCII unit strings (e.g. "A") to Unicode for display,
            # matching the built-in scale bars.
            self._scale_bar.units = format_unit(units)
        if pixel_size is not None or units is not None:
            self._scale_bar.updateBar()

    ########## ROIs and annotations ##########

    def add_roi(self, roi):
        """
        Attach a pre-built pyqtgraph ROI (e.g. ``pg.RectROI``) to this tab's
        view, and track it so it is detached when the tab is closed. Returns
        the ROI for convenience.
        """
        if self._closed:
            raise RuntimeError(
                "Cannot add a ROI to a closed virtual-image tab."
            )
        self._widget.getView().addItem(roi)
        self._rois.append(roi)
        return roi

    def add_annotation(self, annotation):
        """
        Attach any pyqtgraph ``QGraphicsItem`` (line, text, path, ...) as an
        annotation on this tab's view, and track it so it is detached when the
        tab is closed. Returns the item for convenience.
        """
        if self._closed:
            raise RuntimeError(
                "Cannot add an annotation to a closed virtual-image tab."
            )
        self._widget.getView().addItem(annotation)
        self._annotations.append(annotation)
        return annotation

    def detach_items(self):
        """
        Detach any tracked ROIs/annotations from this tab's view and stop
        tracking them. The items themselves are **not** deleted, so a plugin
        that wants to reuse one can do so. Safe to call more than once.
        """
        for item in list(self._rois) + list(self._annotations):
            scene = item.scene()
            if scene is not None:
                scene.removeItem(item)
            item.setParentItem(None)
        self._rois = []
        self._annotations = []

    ########## lifecycle ##########

    @property
    def closed(self):
        """True once :meth:`close` has run (or the tab has been closed)."""
        return self._closed

    def close(self):
        """
        Close this tab, cleaning up its ROIs, annotations, and widget.

        Delegates to the viewer's teardown path, which detaches the tab's
        tracked items, removes it from the pane, and frees the widget. Safe to
        call more than once (a no-op after the first close).
        """
        if self._closed:
            return
        self._viewer.close_virtual_image_tab(self)
