from __future__ import absolute_import, print_function, division
from pony.py23compat import buffer, int_types

import sys, types, weakref
from decimal import Decimal
from datetime import date, time, datetime, timedelta
from functools import wraps
from uuid import UUID
from typing import TYPE_CHECKING, Any, Final, Literal, Tuple

from typing_extensions import Self

from pony.orm._ormtypes import FuncType, MethodType, RawSQL, RawSQLType, SetType, normalize, normalize_type, parse_raw_sql, raw_sql
from pony.utils import throw

if TYPE_CHECKING:
    from pony.orm._sqlbuilding import Value
    from pony.orm.core import Attribute, Entity

NoneType = type(None)

class LongStr(str):
    lazy = True

LongUnicode = LongStr

class QueryType(object):
    def __init__(self, query, limit=None, offset=None):
        self.query_key = query._key
        self.translator = query._translator
        self.limit = limit
        self.offset = offset
    def __hash__(self) -> int:
        result = hash(self.query_key)
        if self.limit is not None:
            result ^= hash(self.limit + 3)
        if self.offset is not None:
            result ^= hash(self.offset)
        return result
    def __eq__(self, other: Any) -> bool:
        return type(other) is QueryType and self.query_key == other.query_key \
               and self.limit == other.limit and self.offset == other.offset
    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

coercions = {
    (int, float): float,
    (int, Decimal): Decimal,
    (date, datetime): datetime,
    (bool, int): int,
    (bool, float): float,
    (bool, Decimal): Decimal
    }
coercions.update(((t2, t1), t3) for ((t1, t2), t3) in list(coercions.items()))

def coerce_types(t1, t2):
    if t1 == t2: return t1
    is_set_type = False
    if type(t1) is SetType:
        is_set_type = True
        t1 = t1.item_type
    if type(t2) is SetType:
        is_set_type = True
        t2 = t2.item_type
    result = coercions.get((t1, t2))
    if result is not None and is_set_type: result = SetType(result)
    return result

def are_comparable_types(t1, t2, op='=='):
    # types must be normalized already!
    tt1 = type(t1)
    tt2 = type(t2)

    t12 = {t1, t2}
    if Json in t12 and t12 < {Json, str, str, int, bool, float}:
        return True
    if op in ('in', 'not in'):
        if tt2 is RawSQLType: return True
        if tt2 is not SetType: return False
        op = '=='
        t2 = t2.item_type
        tt2 = type(t2)
    if op in ('is', 'is not'):
        return t1 is not None and t2 is NoneType
    if tt1 is tuple:
        if not tt2 is tuple: return False
        if len(t1) != len(t2): return False
        for item1, item2 in zip(t1, t2):
            if not are_comparable_types(item1, item2): return False
        return True
    if tt1 is RawSQLType or tt2 is RawSQLType: return True
    if op in ('==', '<>', '!='):
        if t1 is NoneType and t2 is NoneType: return False
        if t1 is NoneType or t2 is NoneType: return True
        if t1 in primitive_types:
            if t1 is t2: return True
            if (t1, t2) in coercions: return True
            if tt1 is not type or tt2 is not type: return False
            if issubclass(t1, int_types) and issubclass(t2, str): return True
            if issubclass(t2, int_types) and issubclass(t1, str): return True
            return False
        if tt1.__name__ == tt2.__name__ == 'EntityMeta':
            return t1._root_ is t2._root_
        return False
    if t1 is t2 and t1 in comparable_types: return True
    return (t1, t2) in coercions

class TrackedValue(object):
    def __init__(self, obj: "Entity", attr: "Attribute") -> None:
        self.obj_ref: Final = weakref.ref(obj)
        self.attr: Final = attr
    @classmethod
    def make(cls, obj: "Entity", attr: "Attribute", value: "Value") -> None:
        if isinstance(value, dict):
            return TrackedDict(obj, attr, value)
        if isinstance(value, list):
            return TrackedList(obj, attr, value)
        return value
    def _changed_(self) -> None:
        obj = self.obj_ref()
        if obj is not None:
            obj._attr_changed_(self.attr)
    def get_untracked(self) -> Tuple[Literal[False], Literal["Abstract method"]]:
        assert False, 'Abstract method'  # pragma: no cover

def tracked_method(func):
    @wraps(func)
    def new_func(self, *args, **kwargs):
        obj = self.obj_ref()
        attr = self.attr
        if obj is not None:
            args = tuple(TrackedValue.make(obj, attr, arg) for arg in args)
            if kwargs: kwargs = {key: TrackedValue.make(obj, attr, value) for key, value in kwargs.items()}
        result = func(self, *args, **kwargs)
        self._changed_()
        return result
    return new_func

class TrackedDict(TrackedValue, dict):
    def __init__(self, obj: "Entity", attr: "Attribute", value: "Value"):
        TrackedValue.__init__(self, obj, attr)
        dict.__init__(self, {key: self.make(obj, attr, val) for key, val in value.items()})
    def __reduce__(self):
        return dict, (dict(self),)
    __setitem__ = tracked_method(dict.__setitem__)
    __delitem__ = tracked_method(dict.__delitem__)
    _update = tracked_method(dict.update)
    def update(self, *args, **kwargs):
        args = [ arg if isinstance(arg, dict) else dict(arg) for arg in args ]
        return self._update(*args, **kwargs)
    setdefault = tracked_method(dict.setdefault)
    pop = tracked_method(dict.pop)
    popitem = tracked_method(dict.popitem)
    clear = tracked_method(dict.clear)
    def get_untracked(self):
        return {key: val.get_untracked() if isinstance(val, TrackedValue) else val
                for key, val in self.items()}

class TrackedList(TrackedValue, list):
    def __init__(self, obj: "Entity", attr: "Attribute", value: "Value"):
        TrackedValue.__init__(self, obj, attr)
        list.__init__(self, (self.make(obj, attr, val) for val in value))
    def __reduce__(self):
        return list, (list(self),)
    __setitem__ = tracked_method(list.__setitem__)
    __delitem__ = tracked_method(list.__delitem__)
    extend = tracked_method(list.extend)
    append = tracked_method(list.append)
    pop = tracked_method(list.pop)
    remove = tracked_method(list.remove)
    insert = tracked_method(list.insert)
    reverse = tracked_method(list.reverse)
    sort = tracked_method(list.sort)
    clear = tracked_method(list.clear)
    def get_untracked(self):
        return [val.get_untracked() if isinstance(val, TrackedValue) else val for val in self]

def validate_item(item_type, item):
    if not isinstance(item, item_type):
        if item_type is not str and hasattr(item, '__index__'):
            return item.__index__()
        throw(TypeError, 'Cannot store %r item in array of %r' % (type(item).__name__, item_type.__name__))
    return item

class TrackedArray(TrackedList):
    def __init__(self, obj: "Entity", attr: "Attribute", value: "Value"):
        TrackedList.__init__(self, obj, attr, value)
        self.item_type = attr.py_type.item_type
    def extend(self, items):
        items = [validate_item(self.item_type, item) for item in items]
        TrackedList.extend(self, items)
    def append(self, item):
        item = validate_item(self.item_type, item)
        TrackedList.append(self, item)
    def insert(self, index, item):
        item = validate_item(self.item_type, item)
        TrackedList.insert(self, index, item)
    def __setitem__(self, index, item):
        item = validate_item(self.item_type, item)
        TrackedList.__setitem__(self, index, item)

    def __contains__(self, item):
        if not isinstance(item, str) and hasattr(item, '__iter__'):
            return all(it in set(self) for it in item)
        return list.__contains__(self, item)


class Json(object):
    """A wrapper over a dict or list
    """
    @classmethod
    def default_empty_value(cls):
        return {}

    def __init__(self, wrapped):
        self.wrapped = wrapped

    def __repr__(self):
        return '<Json %r>' % self.wrapped

class Array(object):
    item_type = None  # Should be overridden in subclass

    @classmethod
    def default_empty_value(cls):
        return []


class IntArray(Array):
    item_type = int


class StrArray(Array):
    item_type = str


class FloatArray(Array):
    item_type = float


numeric_types = {bool, int, float, Decimal}
comparable_types = {int, float, Decimal, str, date, time, datetime, timedelta, bool, UUID, IntArray, StrArray, FloatArray}
primitive_types = comparable_types | {buffer}
function_types = {type, types.FunctionType, types.BuiltinFunctionType}
type_normalization_dict = {}

array_types = {
    int: IntArray,
    float: FloatArray,
    str: StrArray
}

