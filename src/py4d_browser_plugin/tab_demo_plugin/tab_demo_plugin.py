from PyQt5.QtWidgets import QWidget


class TabDemoPlugin(QWidget):
    """
    A minimal demonstration of the v1.6 virtual-image tab API.

    Adds a single menu item ("Copy Virtual Image to Tab") that copies the
    raw array currently on display in the virtual-image pane — the built-in
    virtual image, or another plugin tab's image — into a new tab, so a
    user can keep it alongside the live display without the plugin
    overwriting anything.
    """

    # required for py4DGUI to recognize this as a plugin.
    plugin_id = "py4DGUI.internal.tab_demo"

    # the plugin API version this plugin was written against
    api_version = (1, 6)

    uses_single_action = True
    display_name = "Copy Virtual Image to Tab"

    def __init__(self, api, plugin_action, **kwargs):
        super().__init__()

        self.api = api
        # Note: we do not keep a list of the tabs we create. A closed tab is
        # not freed by the browser (it still holds its raw image array in
        # `tab.image`), so retaining it would pin that memory until exit. The
        # tabs are the viewer's to own and clean up; we only create and drive
        # them, then let the viewer close them.

        plugin_action.triggered.connect(self.copy_to_tab)

    def close(self):
        # `close` runs only at app shutdown and is for releasing non-visual
        # resources (sockets, threads, open files). The tabs this plugin
        # created are visual items the viewer frees on shutdown, so there is
        # nothing to do here.
        pass

    def _next_title(self):
        # "Copy 1", "Copy 2", ... skipping titles already taken (e.g. by a
        # tab the user has not yet closed).
        tabs = self.api.virtual_image_tabs
        n = len(tabs) + 1
        while any(tab.title == f"Copy {n}" for tab in tabs):
            n += 1
        return f"Copy {n}"

    def copy_to_tab(self):
        api = self.api

        image = api.current_virtual_image
        if image is None:
            api.status_bar.showMessage(
                "No virtual image to copy — display one first.", 5_000
            )
            return

        title = self._next_title()
        tab = api.create_virtual_image_tab(title)

        # If a dataset is loaded, carry its real-space calibration over so
        # the copy's scale bar matches the source's.
        set_scalebar = {}
        if api.datacube is not None:
            set_scalebar = dict(
                pixel_size=api.datacube.calibration.get_R_pixel_size(),
                pixel_units=api.datacube.calibration.get_R_pixel_units(),
            )
        tab.set_image(image, reset=True, **set_scalebar)

        api.status_bar.showMessage(
            f"Copied the current virtual image to the '{title}' tab.", 5_000
        )
