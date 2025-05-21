import pandas as pd
from attachmentsv2.plugin_api import register_plugin
from attachmentsv2.core import Transform

@register_plugin("transform", priority=100)
class Summary(Transform):
    name = 'summary'

    def apply(self, obj, args):
        if isinstance(obj, pd.DataFrame) and args and args.lower() == 'true':
            return obj.describe()
        return obj
