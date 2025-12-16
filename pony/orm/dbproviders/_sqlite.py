import binascii
import re
import os
import datetime, json, time
from functools import wraps
from typing import Any, Callable, Final, TypeVar, cast, final, overload

import sqlite
from typing_extensions import Concatenate, ParamSpec

from pony.orm import dbapiprovider
from pony.orm._dbapiprovider import Pool
from pony.orm._sqlbuilding import Value
from pony.utils import datetime2timestamp, timestamp2datetime


_T = TypeVar("_T")
_P = ParamSpec("_P")
_L = TypeVar("_L", bound=list[Any])

hexlify: Final = binascii.hexlify

_dumps: Final = json.dumps
_loads: Final = json.loads


@final
class SQLiteValue(Value):
    def __str__(self) -> str:
        value = self.value
        if isinstance(value, datetime.datetime):
            return self.quote_str(datetime2timestamp(value))
        if isinstance(value, datetime.date):
            return self.quote_str(str(value))
        if isinstance(value, datetime.timedelta):
            return repr(value.total_seconds() / (24 * 60 * 60))
        return super().__str__()

@final
class SQLiteDateConverter(dbapiprovider.DateConverter):
    def sql2py(converter, val: str) -> datetime.date | str:
        try:
            time_tuple = time.strptime(val[:10], '%Y-%m-%d')
            return datetime.date(*time_tuple[:3])
        except: return val
    def py2sql(converter, val: datetime.date) -> str:
        return val.strftime('%Y-%m-%d')

@final
class SQLiteTimeConverter(dbapiprovider.TimeConverter):
    def sql2py(converter, val: str) -> datetime.time | str:
        try:
            dt = datetime.strptime(val, '%H:%M:%S' if len(val) <= 8 else '%H:%M:%S.%f')  # type: ignore [attr-defined]
            return cast(datetime.time, dt.datetime.time())
        except: return val
    def py2sql(converter, val: datetime.time) -> str:
        return val.isoformat()

@final
class SQLiteTimedeltaConverter(dbapiprovider.TimedeltaConverter):
    def sql2py(converter, val: float) -> datetime.timedelta:
        return datetime.timedelta(days=val)
    def py2sql(converter, val: datetime.timedelta) -> float:
        return val.days + (val.seconds + val.microseconds / 1000000.0) / 86400.0

@final
class SQLiteDatetimeConverter(dbapiprovider.DatetimeConverter):
    def sql2py(converter, val: str) -> datetime.datetime | str:
        try: return timestamp2datetime(val)
        except: return val
    def py2sql(converter, val: datetime.datetime) -> str:
        return datetime2timestamp(val)

@final
class SQLiteJsonConverter(dbapiprovider.JsonConverter):
    json_kwargs: Final = {'separators': (',', ':'), 'sort_keys': True, 'ensure_ascii': False}  # type: ignore [misc]


@final
def dumps(items: Any) -> str:
    return _dumps(items, **SQLiteJsonConverter.json_kwargs)  # type: ignore [arg-type]

def py_json_unwrap(value: Any) -> str | None:
    # "[null,some_json]" -> "some_json"
    if isinstance(value, str) and value.startswith('[null,'):
        return value[6:-1]
    return None

path_cache: Final[dict[Any, Any]] = {}

json_path_re: Final = re.compile(r'\[(-?\d+)\]|\.(?:(\w+)|"([^"]*)")', re.UNICODE)

def _parse_path(path: Any) -> Any:
    if path in path_cache:
        return path_cache[path]
    keys: Any = None
    if isinstance(path, str) and path.startswith('$'):
        keys = []
        pos = 1
        path_len = len(path)
        while pos < path_len:
            match = json_path_re.match(path, pos)
            if match is not None:
                g1, g2, g3 = match.groups()
                keys.append(int(g1) if g1 else g2 or g3)
                pos = match.end()
            else:
                keys = None
                break
        else: keys = tuple(keys)
    path_cache[path] = keys
    return keys

def _traverse(obj: Any, keys: Any) -> Any:
    if keys is None: return None
    list_or_dict = (list, dict)
    for key in keys:
        if type(obj) is list:
            try: obj = obj[key]
            except IndexError: return None
        elif type(obj) is dict:
            try: obj = obj[key]
            except KeyError: return None
        else: return None
    return obj

def _extract(expr: str, *paths: Any) -> Any:
    expr = _loads(expr) if isinstance(expr, str) else expr
    result = []
    for path in paths:
        keys = _parse_path(path)
        result.append(_traverse(expr, keys))
    return result[0] if len(paths) == 1 else result

def py_json_extract(expr: str, *paths: Any) -> str:
    result = _extract(expr, *paths)
    if type(result) in (list, dict):
        result = _dumps(result, **SQLiteJsonConverter.json_kwargs)  # type: ignore [arg-type]
    return result  # type: ignore [no-any-return]

def py_json_query(expr: str, path: Any, with_wrapper: bool) -> str | None:
    result = _extract(expr, path)
    if type(result) not in (list, dict):
        if not with_wrapper: return None
        result = [result]
    return _dumps(result, **SQLiteJsonConverter.json_kwargs)  # type: ignore [arg-type]

def py_json_value(expr: str, path: Any) -> Any:
    result = _extract(expr, path)
    return result if type(result) not in (list, dict) else None

def py_json_contains(expr: Any, path: Any, key: Any) -> bool:
    expr = _loads(expr) if isinstance(expr, str) else expr
    keys = _parse_path(path)
    expr = _traverse(expr, keys)
    return type(expr) in (list, dict) and key in expr

def py_json_nonzero(expr: Any, path: Any) -> bool:
    expr = _loads(expr) if isinstance(expr, str) else expr
    keys = _parse_path(path)
    expr = _traverse(expr, keys)
    return bool(expr)

def py_json_array_length(expr: Any, path: Any = None) -> int:
    expr = _loads(expr) if isinstance(expr, str) else expr
    if path:
        keys = _parse_path(path)
        expr = _traverse(expr, keys)
    return len(expr) if type(expr) is list else 0

def wrap_array_func(func: Callable[Concatenate[_L, _P], _T]) -> Callable[Concatenate[str | bytes | bytearray, _P], _T]:
    @wraps(func)
    def new_func(array_json: str | bytes | bytearray | None, *args: _P.args, **_: _P.kwargs) -> _T | None:
        if array_json is None:
            return None
        array = _loads(array_json)
        return func(array, *args)  # type: ignore [call-arg]
    return new_func  # type: ignore [return-value]

@wrap_array_func
def py_array_index(array: list[_T], index: int) -> _T | None:
    try:
        return array[index]
    except IndexError:
        return None

@wrap_array_func
def py_array_contains(array: list[Any], item: Any) -> bool:
    return item in array

@wrap_array_func
def py_array_subset(array: list[Any], items: Any) -> bool | None:
    if items is None: return None
    items = _loads(items)
    return set(items).issubset(set(array))

@wrap_array_func
def py_array_length(array: list[Any]) -> int:
    return len(array)

@wrap_array_func
def py_array_slice(array: list[Any], start: int, stop: int) -> str:
    return dumps(array[start:stop])

def py_make_array(*items: Any) -> str:
    return dumps(items)

@overload
def py_string_slice(s: str, start: int | str, end: int | str) -> str: ...
@overload
def py_string_slice(s: None, start: int | str, end: int | str) -> None: ...
def py_string_slice(s: str | None, start: int | str, end: int | str) -> str | None:
    if s is None:
        return None
    if isinstance(start, str):
        start = int(start)
    if isinstance(end, str):
        end = int(end)
    return s[start:end]


def _text_factory(s: bytes) -> str:
    return s.decode('utf8', 'replace')

def py_upper(value: Any) -> str | None:
    if value is None:
        return None
    t = type(value)
    if t is str:
        string = value
    elif t is buffer:
        string = hexlify(value).decode('ascii')
    else:
        string = str(value)
    return string.upper()

def py_lower(value: Any) -> str | None:
    if value is None:
        return None
    t = type(value)
    if t is str:
        string = value
    elif t is buffer:
        string = hexlify(value).decode('ascii')
    else:
        string = str(value)
    return string.lower()


@final
class SQLitePool(Pool):
    def __init__(pool, is_shared_memory_db: bool, filename: str, create_db: bool, **kwargs: Any): # called separately in each thread
        pool.is_shared_memory_db: Final = is_shared_memory_db
        pool.filename: Final = filename
        pool.create_db: Final = create_db
        pool.kwargs: Final = kwargs
        pool.con: Any = None
    def _connect(pool) -> None:
        filename = pool.filename
        if pool.is_shared_memory_db or pool.filename == ':memory:':
            pass
        elif not pool.create_db and not os.path.exists(filename):
            throw(IOError, "Database file is not found: %r" % filename)

        pool.con = con = sqlite.connect(filename, isolation_level=None, **pool.kwargs)
        con.text_factory = _text_factory

        def create_function(name: str, num_params: int, func: Callable[..., Any]) -> None:
            func = keep_exception(func)
            con.create_function(name, num_params, func)

        create_function('power', 2, pow)
        create_function('rand', 0, random)
        create_function('py_upper', 1, py_upper)
        create_function('py_lower', 1, py_lower)
        create_function('py_json_unwrap', 1, py_json_unwrap)
        create_function('py_json_extract', -1, py_json_extract)
        create_function('py_json_contains', 3, py_json_contains)
        create_function('py_json_nonzero', 2, py_json_nonzero)
        create_function('py_json_array_length', -1, py_json_array_length)

        create_function('py_array_index', 2, py_array_index)
        create_function('py_array_contains', 2, py_array_contains)
        create_function('py_array_subset', 2, py_array_subset)
        create_function('py_array_length', 1, py_array_length)
        create_function('py_array_slice', 3, py_array_slice)
        create_function('py_make_array', -1, py_make_array)

        create_function('py_string_slice', 3, py_string_slice)

        if sqlite.sqlite_version_info >= (3, 6, 19):
            con.execute('PRAGMA foreign_keys = true')

        con.execute('PRAGMA case_sensitive_like = true')
    def disconnect(pool) -> None:
        if pool.is_shared_memory_db or pool.filename == ':memory:':
            pass
        else:
            Pool.disconnect(pool)
    def drop(pool, con: Any) -> None:
        if pool.is_shared_memory_db or pool.filename == ':memory:':
            con.rollback()
        else:
            Pool.drop(pool, con)
