"""02truesize - Map Truth Lab: QGIS plugin entry point.

The package directory is ``zero2truesize`` — the QGIS Plugin Hub requires
the zip's top-level directory to be a valid Python identifier, so a
digit-first name is not allowed. The displayed plugin name stays
"02truesize". Convention kept from the 02viz family: every import inside
this package is relative (``from .module import X``).
"""
from .main_plugin import O2TrueSizePlugin

PLUGIN_VERSION = "0.1.0"


def classFactory(iface):
    return O2TrueSizePlugin(iface)
