import sys
import types
from typing import Any, Dict, Final, List, Optional, Tuple, Union, final

from typing_extensions import Self

from pony.utils import throw, parse_expr
from pony.utils._utils import deref_proxy


NoneType: Final = type(None)
Item = Union[str, Tuple[str, types.CodeType]]
Parsed = Tuple[Tuple[Item, ...], Tuple[types.CodeType, ...]]

raw_sql_cache: Final[Dict[str, Parsed]] = {}

function_types = {type, types.FunctionType, types.BuiltinFunctionType}


@final
class SetType:
    def __deepcopy__(self, memo: Any) -> Self:
        return self  # SetType instances are "immutable"
    def __init__(self, item_type: type) -> None:
        self.item_type: Final = item_type
    def __eq__(self, other: Any) -> bool:
        return type(other) is SetType and self.item_type == other.item_type
    def __ne__(self, other: Any) -> bool:
        return type(other) is not SetType or self.item_type != other.item_type
    def __hash__(self) -> int:
        return hash(self.item_type) + 1


@final
class FuncType:
    def __deepcopy__(self, memo: Any) -> Self:
        return self  # FuncType instances are "immutable"
    def __init__(self, func: types.FunctionType) -> None:
        self.func: Final = func
    def __eq__(self, other: Any) -> bool:
        return type(other) is FuncType and self.func == other.func
    def __ne__(self, other: Any) -> bool:
        return type(other) is not FuncType or self.func != other.func
    def __hash__(self) -> int:
        return hash(self.func) + 1
    def __repr__(self) -> str:
        return 'FuncType(%s at %d)' % (self.func.__name__, id(self.func))


@final
class MethodType:
    def __deepcopy__(self, memo: Any) -> Self:
        return self  # MethodType instances are "immutable"
    def __init__(self, method: types.MethodType) -> None:
        self.obj: Final = method.__self__
        self.func: Final = method.__func__
    def __eq__(self, other: Any) -> bool:
        return type(other) is MethodType and self.obj == other.obj and self.func == other.func
    def __ne__(self, other: Any) -> bool:
        return type(other) is not MethodType or self.obj != other.obj or self.func != other.func
    def __hash__(self) -> int:
        return hash(self.obj) ^ hash(self.func)


def parse_raw_sql(sql: str) -> Parsed:
    result = raw_sql_cache.get(sql)
    if result is not None: return result
    if not isinstance(sql, str) or not sql:
        throw(TypeError, "Raw SQL string fragment expected. Got: %r" % sql)
    items: List[Item] = []
    codes: List[types.CodeType] = []
    pos = 0
    while True:
        try: i = sql.index('$', pos)
        except ValueError:
            items.append(sql[pos:])
            break
        items.append(sql[pos:i])
        if sql[i+1] == '$':
            items.append('$')
            pos = i+2
        else:
            try: expr, _ = parse_expr(sql, i+1)
            except ValueError:
                raise ValueError(sql[i:])
            pos = i+1 + len(expr)
            if expr.endswith(';'): expr = expr[:-1]
            code = compile(expr, '<?>', 'eval')  # expr correction check
            codes.append(code)
            items.append((expr, code))
    result = tuple(items), tuple(codes)
    raw_sql_cache[sql] = result
    return result


def raw_sql(sql: str, result_type=None) -> "RawSQL":  # type: ignore [no-untyped-def]
    globals = sys._getframe(1).f_globals
    locals = sys._getframe(1).f_locals
    return RawSQL(sql, globals, locals, result_type)


@final
class RawSQL:
    def __deepcopy__(self, memo) -> Self:  # type: ignore[no-untyped-def]
        assert False  # should not attempt to deepcopy RawSQL instances, because of locals/globals
    def __init__(  # type: ignore[no-untyped-def]
        self,
        sql: str,
        globals: Optional[Dict[str, Any]] = None,
        locals: Optional[Dict[str, Any]] = None,
        result_type=None,
    ) -> None:
        self.sql: Final = sql
        items, codes = parse_raw_sql(sql)
        self.items: Final = items
        self.codes: Final = codes
        types, values = normalize(tuple(eval(code, globals, locals) for code in self.codes))
        self.types: Final = types
        self.values: Final = values
        self.result_type: Final = result_type
    def _get_type_(self) -> "RawSQLType":
        return RawSQLType(self.sql, self.items, self.types, self.result_type)


@final
class RawSQLType:
    def __deepcopy__(self, memo) -> Self:  # type: ignore[no-untyped-def]
        return self  # RawSQLType instances are "immutable"
    def __init__(self, sql: str, items: Tuple[Item, ...], types: Tuple[type, ...], result_type) -> None:  # type: ignore[no-untyped-def]
        self.sql: Final = sql
        self.items: Final = items
        self.types: Final = types
        self.result_type: Final = result_type
    def __hash__(self) -> int:
        return hash(self.sql) ^ hash(self.types)
    def __eq__(self, other: Any) -> bool:
        return type(other) is RawSQLType and self.sql == other.sql and self.types == other.types
    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)


# TODO: add overloads
def normalize(value: Any) -> Tuple[Any, Any]:
    value = deref_proxy(value)
    t = type(value)
    if t is tuple:
        item_types, item_values = [], []
        for item in value:
            item_type, item_value = normalize(item)
            item_values.append(item_value)
            item_types.append(item_type)
        return tuple(item_types), tuple(item_values)

    if (tname := t.__name__) == 'EntityMeta':
        return SetType(value), value

    if tname == 'EntityIter':
        entity = value.entity
        return SetType(entity), entity

    if isinstance(value, str):
        return str, value

    if t in function_types:
        return FuncType(value), value

    if t is types.MethodType:
        return MethodType(value), value

    if hasattr(value, '_get_type_'):
        return value._get_type_(), value

    return normalize_type(t), value


# TODO: add overloads
#def normalize_type(t: type) -> type:
def normalize_type(t: Any) -> Any:
    tt = type(t)
    if tt is tuple: return tuple(map(normalize_type, t))
    if not isinstance(t, type):
        return t
    assert t.__name__ != 'EntityMeta'
    if tt.__name__ == 'EntityMeta': return t
    if t is NoneType: return t
    from pony.orm.ormtypes import Array, Json, primitive_types, type_normalization_dict
    t = type_normalization_dict.get(t, t)
    if t in primitive_types: return t
    if t in (slice, type(Ellipsis)): return t
    if issubclass(t, str): return str
    if issubclass(t, (dict, Json)): return Json
    if issubclass(t, Array): return t
    throw(TypeError, 'Unsupported type %r' % t.__name__)
