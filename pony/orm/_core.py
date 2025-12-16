# mypy: disable-error-code="var-annotated,has-type,union-attr"
import itertools
import types
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Dict, Final, Iterator, Literal, Optional, Type, Union, cast, final

from pony.utils import localbase, throw
from pony.utils._utils import parse_expr

if TYPE_CHECKING:
    from pony.orm.core import Attribute, DBSessionContextManager, Entity, EntityMeta, Local, PrefetchContext, QueryResult, Set
    from pony.orm.ormtypes import QueryType


statuses: Final = {'created', 'cancelled', 'loaded', 'modified', 'inserted', 'updated', 'marked_to_delete', 'deleted'}
del_statuses: Final = {'marked_to_delete', 'deleted', 'cancelled'}
created_or_deleted_statuses: Final = {'created'} | del_statuses
saved_statuses: Final = {'inserted', 'updated', 'deleted'}


'''
@final
class Local(localbase):
    def __init__(local) -> None:
        local.debug: bool = False
        local.show_values: Optional[bool] = None
        local.debug_stack: list[tuple[bool, Optional[bool]]] = []
        local.db2cache = {}
        local.db_context_counter = 0
        local.db_session: Optional["DBSessionContextManager"] = None
        local.prefetch_context_stack: Final[list["PrefetchContext"]] = []
        local.current_user: Any = None
        local.perms_context: Any = None
        local.user_groups_cache = {}
        local.user_roles_cache: Final = defaultdict(dict)
    @property
    def prefetch_context(local) -> Optional["PrefetchContext"]:
        if prefetch_context_stack := local.prefetch_context_stack:
            return prefetch_context_stack[-1]
        return None
    def push_debug_state(local, debug: bool, show_values: Optional[bool]) -> None:
        from pony.orm.core import suppress_debug_change
      
        local.debug_stack.append((local.debug, local.show_values))
        if not suppress_debug_change:
            local.debug = debug
            local.show_values = show_values
    def pop_debug_state(local) -> None:
        local.debug, local.show_values = local.debug_stack.pop()


#local: Final = Local()
'''


class NotLoadedValueType(object):
    def __repr__(self) -> Literal["NOT_LOADED"]:
        return 'NOT_LOADED'

NOT_LOADED: Final = NotLoadedValueType()


class DefaultValueType(object):
    def __repr__(self) -> Literal["DEFAULT"]:
        return 'DEFAULT'

DEFAULT: Final = DefaultValueType()


local: Optional["Local"] = None

def __set_local() -> "Local":
    from pony.orm import core
    global local
    local = core.local
    return local


def _parse_row_(entity: "EntityMeta", row: tuple, attr_offsets: Dict["Attribute"]) -> tuple[type, Any, dict]:  # type: ignore [type-arg]
    discr_attr: Optional["Attribute"] = entity._discriminator_attr_
    if not discr_attr:
        discr_value = None
        real_entity_subclass = entity
    else:
        discr_offset = attr_offsets[discr_attr][0]
        discr_value = discr_attr.validate(row[discr_offset], None, entity, from_db=True)  # type: ignore [no-untyped-call]
        real_entity_subclass = discr_attr.code2cls[discr_value]  # type: ignore [attr-defined]
        discr_value = real_entity_subclass._discriminator_  # To convert str to str in Python 2.x

    database = entity._database_
    cache = (local or __set_local()).db2cache[database]

    avdict: Dict["Attribute", Any] = {}
    for attr in real_entity_subclass._attrs_:
        offsets = attr_offsets.get(attr)
        if offsets is None:
            continue
        if attr.is_discriminator:
            avdict[attr] = discr_value
        else:
            avdict[attr] = attr.parse_value(row, offsets, cache.dbvals_deduplication_cache)

    pktup = tuple(map(avdict.pop, entity._pk_attrs_))
    assert None not in pktup
    pkval = pktup if entity._pk_is_composite_ else pktup[0]
    return real_entity_subclass, pkval, avdict


new_instance_id_counter: Final = itertools.count(1)


def _get_from_identity_map_(
    entity: "EntityMeta",
    pkval: Any,
    status: str,
    for_update: bool = False,
    undo_funcs: Any = None,
    obj_to_init: Any = None,
) -> Any:
    #attr: "Attribute"
    #obj: Optional["Entity"]
  
    cache = entity._database_._get_cache()
    pk_attrs = entity._pk_attrs_
    cache_index = cache.indexes[pk_attrs]
    if pkval is None: obj = None
    else: obj = cache_index.get(pkval)

    if obj is None: pass
    elif status == 'created':
        from pony.orm.core import CacheIndexError

        if entity._pk_is_composite_:
            pkval = ', '.join(map(str, pkval))        
        throw(CacheIndexError, 'Cannot create %s: instance with primary key %s already exists'
                         % (obj.__class__.__name__, pkval))
    elif obj.__class__ is entity: pass
    elif issubclass(obj.__class__, entity): pass
    elif not issubclass(entity, obj.__class__):
        from pony.orm.core import TransactionError
        
        throw(TransactionError,
        'Unexpected class change from %s to %s for object with primary key %r' % (obj.__class__, entity, obj._pkval_))
    elif obj._rbits_ or obj._wbits_: throw(NotImplementedError)
    else: obj.__class__ = entity

    if obj is None:
        with cache.flush_disabled():
            obj = obj_to_init
            if obj_to_init is None:
                obj = object.__new__(entity)  # type: ignore [arg-type]
            cache.objects.add(obj)
            obj._pkval_ = pkval
            obj._status_ = status
            obj._vals_ = {}
            obj._dbvals_ = {}
            obj._save_pos_ = None
            obj._session_cache_ = cache
            if pkval is not None:
                cache_index[pkval] = obj
                obj._newid_ = None
            else: obj._newid_ = next(new_instance_id_counter)
            if obj._pk_is_composite_:
                obj_vals = obj._vals_
                if status == 'loaded':
                    assert undo_funcs is None
                    obj._rbits_ = obj._wbits_ = 0
                    for attr, val in zip(pk_attrs, pkval):
                        obj_vals[attr] = val
                        if attr.reverse: db_update_reverse(attr, obj, NOT_LOADED, val)
                    cache.seeds[pk_attrs].add(obj)
                elif status == 'created':
                    assert undo_funcs is not None
                    obj._rbits_ = obj._wbits_ = None
                    for attr, val in zip(pk_attrs, pkval):
                        obj_vals[attr] = val
                        if attr.reverse: attr.update_reverse(obj, NOT_LOADED, val, undo_funcs)
                    cache.for_update.add(obj)
                else: assert False  # pragma: no cover
            else:
                attr = pk_attrs[0]
                if status == 'loaded':
                    assert undo_funcs is None
                    obj._rbits_ = obj._wbits_ = 0
                    obj._vals_[attr] = pkval
                    if attr.reverse: db_update_reverse(attr, obj, NOT_LOADED, pkval)
                    cache.seeds[pk_attrs].add(obj)
                elif status == 'created':
                    assert undo_funcs is not None
                    obj._rbits_ = obj._wbits_ = None
                    obj._vals_[attr] = pkval
                    if attr.reverse: attr.update_reverse(obj, NOT_LOADED, pkval, undo_funcs)
                    cache.for_update.add(obj)
                else: assert False  # pragma: no cover
    if for_update:
        assert cache.in_transaction
        cache.for_update.add(obj)
    return obj


def _get_by_raw_pkval_(
    entity: "EntityMeta",
    raw_pkval: Any,
    for_update: bool = False,
    from_db: bool = True,
    seed: bool = True,
) -> Any:
    i = 0
    pkval = []
    for attr in entity._pk_attrs_:
        if attr.column is not None:
            val = raw_pkval[i]
            i += 1
            if not attr.reverse: val = attr.validate(val, None, entity, from_db=from_db)
            else: val = _get_by_raw_pkval_(attr.py_type, (val,), from_db=from_db, seed=seed)
        elif not attr.reverse:
            throw(NotImplementedError)
        else:
            vals = raw_pkval[i:i+len(attr.columns)]
            val = _get_by_raw_pkval_(attr.py_type, vals, from_db=from_db, seed=seed)
            i += len(attr.columns)
        pkval.append(val)

    final_pkval = tuple(pkval) if entity._pk_is_composite_ else pkval[0]
    obj = _get_from_identity_map_(entity, final_pkval, 'loaded', for_update) if seed else entity[final_pkval]
    assert obj._status_ != 'cancelled'
    return obj


def _attrs_with_bit_(entity: Type["Entity"], attrs: list["Attribute"], mask: int = -1) -> Iterator[Entity]:
    return _attrs_with_bit_(entity, attrs, mask)


def _get_raw_pkval_(obj: "Entity") -> tuple[Any, ...]:
    pkval = obj._pkval_
    if not obj._pk_is_composite_:
        if not obj._pk_attrs_[0].reverse: return (pkval,)
        else: return _get_raw_pkval_(pkval)
    raw_pkval: list[Any] = []
    for attr, val in zip(obj._pk_attrs_, pkval):
        if not attr.reverse: raw_pkval.append(val)
        else: raw_pkval.extend(_get_raw_pkval_(val))
    return tuple(raw_pkval)
  

def _db_set_(obj: "Entity", avdict: Dict["Attribute", Any], unpickling: bool = False) -> None:
    attr: "Attribute"
  
    assert obj._status_ not in created_or_deleted_statuses
    cache = obj._session_cache_  # type: ignore [attr-defined]
    assert cache is not None and cache.is_alive
    cache.seeds[obj._pk_attrs_].discard(obj)  # type: ignore [attr-defined]
    if not avdict: return

    obj_vals: Dict["Attribute", Any] = obj._vals_  # type: ignore [attr-defined]
    obj_dbvals: Dict["Attribute", Any] = obj._dbvals_  # type: ignore [attr-defined]
  
    rbits = obj._rbits_
    wbits = obj._wbits_
    for attr, new_dbval in list(avdict.items()):
        assert attr.pk_offset is None
        assert new_dbval is not NOT_LOADED
        old_dbval = obj_dbvals.get(attr, NOT_LOADED)
        if old_dbval is not NOT_LOADED:
            if unpickling or old_dbval == new_dbval or (
                    not attr.reverse and attr.converters[0].dbvals_equal(old_dbval, new_dbval)):
                del avdict[attr]
                continue

    if unpickling:
        new_vals = avdict
        new_dbvals = {attr: attr.converters[0].val2dbval(val, obj) if not attr.reverse else val
                            for attr, val in avdict.items()}
    else:
        new_dbvals = avdict
        new_vals = {attr: attr.converters[0].dbval2val(dbval, obj) if not attr.reverse else dbval
                          for attr, dbval in avdict.items()}

    for attr, new_val in list(new_vals.items()):
        new_dbval = new_dbvals[attr]
        old_dbval = obj_dbvals.get(attr, NOT_LOADED)
        bit = obj._bits_except_volatile_[attr]  # type: ignore [attr-defined]
        if rbits & bit:
            from pony.orm.core import UnrepeatableReadError
            errormsg = 'Please contact PonyORM developers so they can ' \
                       'reproduce your error and fix a bug: support@ponyorm.org'
            assert old_dbval is not NOT_LOADED, errormsg
            throw(UnrepeatableReadError,
                  'Value of %s.%s for %s was updated outside of current transaction (was: %r, now: %r)'
                  % (obj.__class__.__name__, attr.name, obj, old_dbval, new_dbval))

        if attr.reverse: db_update_reverse(attr, obj, old_dbval, new_dbval)
        obj_dbvals[attr] = new_dbval
        if wbits & bit:
            del new_vals[attr]

    for attr, new_val in new_vals.items():
        if attr.is_unique:
            old_val = obj_vals.get(attr)
            if old_val != new_val:
                cache.db_update_simple_index(obj, attr, old_val, new_val)

    for attrs in obj._composite_keys_:  # type: ignore [attr-defined]
        if any(attr in new_vals for attr in attrs):
            key_vals = list(map(obj_vals.get, attrs))  # In Python 2 var name leaks into the function scope!
            prev_key_vals = tuple(key_vals)
            for i, attr in enumerate(attrs):
                if attr in new_vals: key_vals[i] = new_vals[attr]
            new_key_vals = tuple(key_vals)
            if prev_key_vals != new_key_vals:
                cache.db_update_composite_index(obj, attrs, prev_key_vals, new_key_vals)

    obj_vals.update(new_vals)


def db_update_reverse(
    attr: "Attribute",
    obj: "Entity",
    old_dbval: "Entity" | NotLoadedValueType | None,
    new_dbval: "Entity" | None,
) -> None:
    reverse = attr.reverse
    if reverse is None: throw(NotImplementedError)
    if not reverse.is_collection:
        if old_dbval not in (None, NOT_LOADED): reverse.db_set(old_dbval, NOT_LOADED, True)  # type: ignore [no-untyped-call]
        if new_dbval is not None: reverse.db_set(new_dbval, obj, True)  # type: ignore [no-untyped-call]
        return
        
    from pony.orm.core import Set
    if isinstance(reverse, Set):
        if old_dbval not in (None, NOT_LOADED): reverse.db_reverse_remove((old_dbval,), obj)  # type: ignore [no-untyped-call]
        if new_dbval is not None: reverse.db_reverse_add((new_dbval,), obj)
    else: throw(NotImplementedError)


@final
class QueryResultIterator:
    def __init__(self, query_result: "QueryResult") -> None:
        self._query_result: Final = query_result
        self._position: int = 0
    def _get_type_(self) -> Union["QueryType", tuple]:  # type: ignore [type-arg]
        if self._position != 0:
            throw(NotImplementedError, 'Cannot use partially exhausted iterator, please convert to list')
        return cast(Union["QueryType", tuple], self._query_result._get_type_())  # type: ignore [type-arg, no-untyped-call]
    def _normalize_var(self, query_type: Union["QueryType", tuple]):  # type: ignore [type-arg, no-untyped-def]
        if self._position != 0: throw(NotImplementedError)
        return self._query_result._normalize_var(query_type)  # type: ignore [no-untyped-call]
    def next(self):  # type: ignore [no-untyped-def]
        qr = self._query_result
        if qr._items is None:
            qr._items = qr._query._actual_fetch(qr._limit, qr._offset)
        if self._position >= len(qr._items):
            raise StopIteration
        item = qr._items[self._position]
        self._position += 1
        return item
    def __next__(self):  # type: ignore [no-untyped-def]
        return self.next()  # type: ignore [no-untyped-call]
    def __length_hint__(self) -> int:
        return len(self._query_result) - self._position


adapted_sql_cache: Final[dict[tuple[str, str], tuple[str, types.CodeType]]] = {}

def adapt_sql(sql: str, paramstyle: str) -> Any:
    result: tuple[str, types.CodeType] | None = adapted_sql_cache.get((sql, paramstyle))
    if result is not None: return result
    pos: int = 0
    preresult: list[str] = []
    args: list[str] = []
    kwargs: dict[str, str] = {}
    original_sql = sql
    if paramstyle in ('format', 'pyformat'): sql = sql.replace('%', '%%')
    while True:
        try: i = sql.index('$', pos)
        except ValueError:
            preresult.append(sql[pos:])
            break
        preresult.append(sql[pos:i])
        if sql[i+1] == '$':
            preresult.append('$')
            pos = i+2
        else:
            try: expr, _ = parse_expr(sql, i+1)
            except ValueError:
                raise # TODO
            pos = i+1 + len(expr)
            if expr.endswith(';'): expr = expr[:-1]
            compile(expr, '<?>', 'eval')  # expr correction check
            if paramstyle == 'qmark':
                args.append(expr)
                preresult.append('?')
            elif paramstyle == 'format':
                args.append(expr)
                preresult.append('%s')
            elif paramstyle == 'numeric':
                args.append(expr)
                preresult.append(':%d' % len(args))
            elif paramstyle == 'named':
                key = 'p%d' % (len(kwargs) + 1)
                kwargs[key] = expr
                preresult.append(':' + key)
            elif paramstyle == 'pyformat':
                key = 'p%d' % (len(kwargs) + 1)
                kwargs[key] = expr
                preresult.append('%%(%s)s' % key)
            else: throw(NotImplementedError)
    if args or kwargs:
        adapted_sql = ''.join(preresult)
        if args: source = '(%s,)' % ', '.join(args)
        else: source = '{%s}' % ','.join('%r:%s' % item for item in kwargs.items())
        code = compile(source, '<?>', 'eval')
    else:
        adapted_sql = original_sql.replace('$$', '$')
        code = compile('None', '<?>', 'eval')
    result = adapted_sql, code
    adapted_sql_cache[(sql, paramstyle)] = result
    return result
