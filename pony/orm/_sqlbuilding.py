
from binascii import hexlify
from pony.converting import timedelta2str

class Value(object):
    def __init__(self, paramstyle: str, value) -> None:
        self.paramstyle: Final = paramstyle
        self.value: Final = value
    def __str__(self) -> str:
        value = self.value
        if value is None:
            return 'null'
        if isinstance(value, bool):
            return value and '1' or '0'
        if isinstance(value, str):
            return self.quote_str(value)
        if isinstance(value, datetime):
            return 'TIMESTAMP ' + self.quote_str(datetime2timestamp(value))
        if isinstance(value, date):
            return 'DATE ' + self.quote_str(str(value))
        if isinstance(value, timedelta):
            return "INTERVAL '%s' HOUR TO SECOND" % timedelta2str(value)
        if isinstance(value, (int, float, Decimal)):
            return str(value)
        if isinstance(value, bytes):
            return f"X'{hexlify(value).decode('ascii')}'"
        assert False, repr(value)  # pragma: no cover
    def __repr__(self) -> str:
        return '%s(%r)' % (self.__class__.__name__, self.value)
    def quote_str(self, s: str) -> str:
        if self.paramstyle in ('format', 'pyformat'): s = s.replace('%', '%%')
        return f"'{s.replace("'", "''")}'"
