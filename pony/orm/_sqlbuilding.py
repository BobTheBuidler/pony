from binascii import hexlify
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, Final, Union

from mypy_extensions import mypyc_attr

from pony.converting import timedelta2str
from pony.utils import datetime2timestamp

if TYPE_CHECKING:
    from pony.orm.sqlbuilding import Param


ValueType = Union[bool, str, datetime, date, timedelta, int, float, Decimal, bytes]


def adapter_qmark(params: tuple["Param", ...]) -> Callable[[dict[str, "Value"]], tuple[str, ...]]:
    def adapter(values: dict[str, "Value"]) -> tuple[str, ...]:
        return tuple(param.eval(values) for param in params)
    return adapter

def adapter_numeric(params: tuple["Param", ...]) -> Callable[[dict[str, "Value"]], tuple[str, ...]]:
    def adapter(values: dict[str, "Value"]) -> tuple[str, ...]:
        return tuple(param.eval(values) for param in params)
    return adapter

def adapter_named(params: tuple["Param", ...]) -> Callable[[dict[str, "Value"]], dict[str, Any]]:
    def adapter(values: dict[str, "Value"]) -> dict[str, Any]:
        return {'p%d' % param.id: param.eval(values) for param in params}
    return adapter


@mypyc_attr(allow_interpreted_subclasses=True)
class Value:
    def __init__(self, paramstyle: str, value: ValueType) -> None:
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
        return f"'%s'" % s.replace("'", "''")
