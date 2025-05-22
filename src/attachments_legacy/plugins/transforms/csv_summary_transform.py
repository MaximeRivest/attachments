import pandas as pd
from attachments.plugin_api import register_plugin
from attachments.core import Transform
from attachments.testing import PluginContract

@register_plugin("transform", priority=100)
class Summary(Transform, PluginContract):
    name = 'summary'
    _sample_obj = pd.DataFrame({"a": [1,2], "b": [3,4]})

    def apply(self, obj, args):
        if isinstance(obj, pd.DataFrame) and args and args.lower() == 'true':
            return obj.describe()
        return obj

__all__ = ["Summary"]
