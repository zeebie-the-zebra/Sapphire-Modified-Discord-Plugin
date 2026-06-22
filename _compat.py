# _compat.py -- Portable import setup for leona_discord plugin
#
# Ensures `from plugins.leona_discord.lib import X` works regardless of whether
# the plugin is installed at plugins/leona_discord/ (bundled with Sapphire) or
# user/plugins/leona_discord/ (installed via Plugin Store or drag-drop).
#
# How: appends this plugin's parent directory to the `plugins` namespace
# package __path__ so Python's import machinery finds leona_discord/ either way.

import sys
import types
from pathlib import Path

_plugins_dir = str(Path(__file__).resolve().parent.parent)

_pkg = sys.modules.get('plugins')
if _pkg is not None:
    if hasattr(_pkg, '__path__') and _plugins_dir not in list(_pkg.__path__):
        _pkg.__path__.append(_plugins_dir)
else:
    _pkg = types.ModuleType('plugins')
    _pkg.__path__ = [_plugins_dir]
    _pkg.__package__ = 'plugins'
    sys.modules['plugins'] = _pkg
