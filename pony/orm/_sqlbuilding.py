from binascii import hexlify
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable, Final, Union

from mypy_extensions import mypyc_attr

from pony.converting import timedelta2str
from pony.utils import datetime2timestamp

if TYPE_CHECKING:
    from pony.orm.sqlbuilding import Param


ValueType = bool | str | datetime | date | timedelta | int | float | Decimal | bytes

Params = tuple["Param", ...]

InputValues = dict[str, "Value"] | tuple[Any, ...] | list[Any]

SQLValue = str | int | bytes |  date | datetime
SQLTuple = tuple[SQLValue, ...]

def adapter_qmark(params: Params) -> Callable[[InputValues], SQLTuple]:
    def adapter(values: InputValues) -> SQLTuple:
        return tuple(param.eval(values) for param in params)
    return adapter

def adapter_numeric(params: Params) -> Callable[[InputValues], SQLTuple]:
    def adapter(values: InputValues) -> SQLTuple:
        return tuple(param.eval(values) for param in params)
    return adapter

def adapter_named(params: Params) -> Callable[[InputValues], dict[str, SQLValue]]:
    def adapter(values: InputValues) -> dict[str, SQLValue]:
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
        if isinstance(value, int):
            return str(value)
        if isinstance(value, float):
            return str(value)
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, bytes):
            return f"X'{hexlify(value).decode('ascii')}'"
        assert False, repr(value)  # pragma: no cover
    def __repr__(self) -> str:
        return '%s(%r)' % (self.__class__.__name__, self.value)
    def quote_str(self, s: str) -> str:
        if self.paramstyle in ('format', 'pyformat'): s = s.replace('%', '%%')
        return f"'%s'" % s.replace("'", "''")
