import orjson
from flask.json.provider import DefaultJSONProvider

class ORJSONProvider(DefaultJSONProvider):
    def dumps(self, obj, **kwargs):
        # orjson.dumps returns bytes; Flask expects str
        if obj is None:
            return "null"
        elif obj is True:
            return "true"
        elif obj is False:
            return "false"
        elif obj == {}:
            return "{}"
        elif obj == []:
            return "[]"
        return orjson.dumps(obj).decode("utf-8")

    def loads(self, s, **kwargs):
        return orjson.loads(s)
