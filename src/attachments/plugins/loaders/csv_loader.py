import pandas as pd
from attachments.plugin_api import register_plugin
from attachments.core import Loader
from attachments.testing import PluginContract

# No external dependencies that need gating here (pandas is common enough or a direct dep of the library)
# If pandas were optional, it would be in PLUGIN_REQUIRES and imported in initialize_plugin.

@register_plugin("loader", priority=100)
class CSVLoader(Loader, PluginContract):
    _sample_path = "csv"

    @classmethod
    def match(cls, path):
        return path.lower().endswith('.csv')

    def load(self, path):
        return pd.read_csv(path)

__all__ = ["CSVLoader"]
