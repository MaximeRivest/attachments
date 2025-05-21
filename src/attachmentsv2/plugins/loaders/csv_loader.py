import pandas as pd
from attachmentsv2.plugin_api import register_plugin
from attachmentsv2.core import Loader

# No external dependencies that need gating here (pandas is common enough or a direct dep of the library)
# If pandas were optional, it would be in PLUGIN_REQUIRES and imported in initialize_plugin.

@register_plugin("loader", priority=100)
class CSVLoader(Loader):
    def match(self, path):
        return path.lower().endswith('.csv')

    def load(self, path):
        return pd.read_csv(path)
