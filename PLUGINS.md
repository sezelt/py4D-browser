# py4DGUI Plugins

Over time, we have substantially pared down the functionality available in the browser, removing things such as pre-processing, file conversion, and data analysis. This has allowed the browser code to become much cleaner, and focused primarily on its core functionality of visualizing 4D-STEM data. In doing so, we have made the browser more robust and maintainable. 
With the introduction of plugins in version 1.3.0, we hope to enable easy expansibility of the capabilities of the browser without complicating the core implementation.

## Known Plugins
We hope to maintain a list of existing plugins here. If you produce a browser plugin, feel free to message `sezelt` or create a PR to be added to this list.

### Pre-packaged plugins
Parts of what used to be "core" functionality are now implemented using the plugin interface to separate them from the core browser code. These are packaged with py4DGUI and always available:
* `Calibration`: Allows for the calibration of the scale bars using known physical distances. Uses the versioned plugin API (v1.0) and updates the scale bars through `set_scalebar`.
* `tcBF`: Allows for the computation of tilt-corrected brightfield images. Uses the versioned plugin API (v1.0) and the detector getters.

### External plugins
* [EMPAD2 Raw File Reader](https://github.com/sezelt/empad2): This also previously was present in the core browser code and would add an additional menu if the external package was installed. This adds the ability to import the "concatenated" raw binary data from the TFS EMPAD-G2 detector. This plugin is considered conforming to the guidelines.  

# Creating a Plugin

The py4D_browser plugin mechanics are inspired by [Nion Swift](https://nionswift.readthedocs.io/en/stable/api/plugins.html), particularly how plugins are installed, discovered, and loaded. 

Plugins should create a module in the `py4d_browser_plugin` namespace and should define a class with the `plugin_id` attribute

```python
class ExamplePlugin:

    # required for py4DGUI to recognize this as a plugin.
    plugin_id = "my.plugin.identifier"

    # the version of the plugin API this plugin was built against.
    # REQUIRED: a plugin that does not declare this is skipped with a log
    # message. The browser passes it the matching API object (see below),
    # or skips the plugin if this version is not supported.
    api_version = (1, 0)

    ######## optional flags ########
    display_name = "Example Plugin"

    # Plugins are always passed the versioned plugin API object as `api`
    # and should only use that surface. Setting this to True additionally
    # passes the raw DataViewer window as `parent` (with the API object
    # still available as `api`) for plugins that need to go beyond the
    # API. This bypasses all compatibility guarantees.
    full_access = False

    # Plugins may add a top-level menu on their own, or can opt to have
    # a submenu located under Plugins>[display_name], which is created before
    # initialization and its QMenu object passed as `plugin_menu`
    uses_plugin_menu = False

    # If the plugin only needs a single action button, the browser can opt
    # to have that menu item created automatically under Plugins>[Display Name]
    # and its QAction object passed as `plugin_action`
    uses_single_action = False

    def __init__(self, api, **kwargs):
        self.api = api

    def close(self):
        pass  # perform any shutdown activities                   

```

On loading the class is initialized using
```python
ExamplePlugin(api=api, [...])
```
where `api` is always the versioned plugin API object described in [The Plugin API](#the-plugin-api-v10) (see below). If the plugin sets `full_access = True`, it additionally receives the `DataViewer` instance (the main window object) as `parent`. All arguments will always be passed as keywords, including any additional arguments that are provided as a result of setting various optional flags. Plugins are loaded as the last step after constructing the `DataViewer`, before its `show()` method is called.  

## Versioning and compatibility

Plugins declare which version of the plugin API they were built against using the class-level `api_version` attribute, a `(major, minor)` tuple. The browser resolves this against its table of supported API versions:

* If the plugin's **major** version is supported and its minor version is at most the latest minor for that major, the plugin is passed the matching API class. Within a major version the API is strictly additive: new features may appear, but existing ones never change behavior.
* If the major version is unknown, or the plugin requests a minor version newer than the browser provides, the plugin is **skipped**: a `PluginAPIVersionError` naming the plugin and both versions is logged, and loading of all other plugins continues. The fix is to upgrade `py4D_browser` (or, for plugin authors, to build the plugin against an API version their users have).
* Multiple major API versions coexist in the same browser, so a plugin built against 1.x continues to work after a 2.x API is introduced, as long as the browser still supports major 1.
* `api_version` is **required**: a plugin that does not declare it is **skipped** with a log message telling it to declare one (e.g. `api_version = (1, 0)`). There is no legacy fallback.
* `full_access = True` is an unversioned escape hatch: the plugin receives the raw `DataViewer` as `parent` in addition to the API object as `api`, and any breakage caused by the browser changing its internals is the plugin's responsibility.

The following design guidelines should still be followed:

* If the plugin adds menu items, it should only add items to its own menu (not to ones already existing in the GUI). The plugin is permitted to add a menu to the top bar on its own, or (preferably) can set the `uses_plugin_menu` attribute which will initialize a menu under Plugins>MyPluginDisplayName which gets passed to the initializer as `plugin_menu`.
* If the plugin adds a single menu item, it can have the browser create and insert that action item automatically by setting `uses_single_action`. The `QAction` object will be passed in as `plugin_action`. 
* The plugin should *never* render an image to the views directly. To display images, plugins should always call `set_virtual_image` or `set_diffraction_image` using raw, unscaled data. If the plugin needs to produce a customized display, it cannot do that in the existing views and must create its own window. 
* The plugin should not retain references to any objects in the `DataViewer`, as that may prevent objects from being freed at the right times. For example, do not do something like `self.current_datacube = self.api.datacube`, as until this reference is cleared the browser could not free memory after closing a dataset and opening a new one. 
* The plugin is allowed to read/write from the QSettings of the GUI, but should only do so in a top-level section with the same name as `plugin_id`, i.e. `value = self.api.settings.value(self.plugin_id + "/my_setting", default_value)`.

## The Plugin API (v1.0)

The v1.0 API object is a broker between the plugin and the browser. Plugins should use only this surface; the browser is free to change its internals as long as the API object keeps working. The full v1.0 surface:

* **`api_version`** — `(1, 0)`, for introspection.
* **`datacube`** — read-only access to the currently loaded `DataCube` (or `None`). Mutating the cube object (e.g. its calibration) is fine; to replace the whole cube, use `set_datacube` below.
* **`set_datacube(datacube, refresh=True)`** — replace the currently loaded datacube (e.g. a cube a plugin computed, or read from a file format the browser doesn't natively open). With `refresh` (the default) the normal post-load machinery runs: both views are reset and `signal_datacube_changed` is emitted. Pass `refresh=False` to swap in the cube without redrawing or notifying listeners. In either case the previous cube is released (a garbage-collection pass is run) so its memory is reclaimed.
* **Signals** — `signal_diffraction_data_changed`, `signal_virtual_image_data_changed`, `signal_datacube_changed`. These are the live signals from the main window, so `connect`/`disconnect` through the API object behaves exactly as if they were accessed directly.
* **Pane setters** — `set_virtual_image(vimg, reset, pixel_size, pixel_units)`, `set_diffraction_image(dp, reset, pixel_size, pixel_units)`, `set_result_image(vimg, reset, pixel_size, pixel_units, title)`. Always pass raw, unscaled data.
* **`set_scalebar(view, pixel_size, units)`** — update the scale bar of one pane, where `view` is one of `"diffraction"`, `"real_space"`, or `"result"`. This is the supported way for plugins to change a scale bar; do not touch the scale bar objects directly.
* **Detector getters** — `get_diffraction_detector()` and `get_virtual_image_detector()`, each returning a `DetectorInfo` (see below).
* **Qt plumbing** — `qtapp` (the `QApplication`), `qt_window` (the main window), `status_bar` (the status bar), and `settings` (the QSettings).

**Dialog parenting:** `QDialog` requires a `QWidget` parent, so any dialog a plugin creates should be parented with `parent=self.api.qt_window`; pass the window object itself for no other reason, and keep doing all data access through the API object.

## Accessing the detectors

With version 1.3.0, there is a new API for accessing the ROI selections made using the detectors on the two views. Plugins should only interact with the detectors via this API, as the implementation details of the ROI objects themselves are considered internal and subject to change. Calling `get_diffraction_detector` or `get_virtual_image_detector` yields a `DetectorInfo` object containing the properties of the current detector and the information (either a slice or a mask array) needed to produce the selection it represents.

## Namespace packages

Namespace packages are a way to split a package across multiple sources, which can be provided by different distributions. This allows the py4DGUI to import this special namespace and have all plugins, regardless of their source, appear under that import. Details can be found in [PEP 420](https://peps.python.org/pep-0420/).

In order to create a plugin, create a directory called `py4d_browser_plugin` under your `src` directory, and then create a directory for your plugin within that folder. _Do not place an `__init__.py` file in the `py4d_browser_plugin` folder, or the import mechanism will be broken for all plugins._