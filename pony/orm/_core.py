# mypy: disable-error-code="var-annotated"
import itertools
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Final, List, Optional, Tuple, final

from pony.utils import localbase, throw

if TYPE_CHECKING:
    from pony.orm.core import Attribute, DBSessionContextManager, Entity, EntityMeta, Local, PrefetchContext, Set


statuses = {'created', 'cancelled', 'loaded', 'modified', 'inserted', 'updated', 'marked_to_delete', 'deleted'}
del_statuses = {'marked_to_delete', 'deleted', 'cancelled'}
created_or_deleted_statuses = {'created'} | del_statuses
saved_statuses = {'inserted', 'updated', 'deleted'}


'''
@final
class Local(localbase):
    def __init__(local) -> None:
        local.debug: bool = False
        local.show_values: Optional[bool] = None
        local.debug_stack: List[Tuple[bool, Optional[bool]]] = []
        local.db2cache = {}
        local.db_context_counter = 0
        local.db_session: Optional["DBSessionContextManager"] = None
        local.prefetch_context_stack: Final[List["PrefetchContext"]] = []
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
    def __repr__(self) -> str:
        return 'NOT_LOADED'

NOT_LOADED: Final = NotLoadedValueType()


class DefaultValueType(object):
    def __repr__(self) -> str:
        return 'DEFAULT'

DEFAULT: Final = DefaultValueType()


local: Optional["Local"] = None

def __set_local() -> "Local":
    from pony.orm import core
    global local
    local = core.local
    return local


def _parse_row_(entity: "EntityMeta", row: tuple, attr_offsets: dict) -> Tuple[type, Any, dict]:  # type: ignore [type-arg]
    discr_attr = entity._discriminator_attr_
    if not discr_attr:
        discr_value = None
        real_entity_subclass = entity
    else:
        discr_offset = attr_offsets[discr_attr][0]
        discr_value = discr_attr.validate(row[discr_offset], None, entity, from_db=True)
        real_entity_subclass = discr_attr.code2cls[discr_value]
        discr_value = real_entity_subclass._discriminator_  # To convert str to str in Python 2.x

    database = entity._database_
    cache = (local or __set_local()).db2cache[database]

    avdict = {}
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
    attr: "Attribute"
    obj: Optional["Entity"]
  
    cache = entity._database_._get_cache()  # type: ignore [union-attr]
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
                        if attr.reverse: attr.update_reverse(obj, NOT_LOADED, val, undo_funcs)  # type: ignore [no-untyped-call]
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
                    if attr.reverse: attr.update_reverse(obj, NOT_LOADED, pkval, undo_funcs)  # type: ignore [no-untyped-call]
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
  

def _db_set_(obj: "Entity", avdict: dict, unpickling: bool = False) -> None:  # type: ignore [type-arg]
    attr: "Attribute"
  
    assert obj._status_ not in created_or_deleted_statuses
    cache = obj._session_cache_  # type: ignore [attr-defined]
    assert cache is not None and cache.is_alive
    cache.seeds[obj._pk_attrs_].discard(obj)  # type: ignore [attr-defined]
    if not avdict: return

    obj_vals: dict = obj._vals_  # type: ignore [attr-defined, type-arg]
    obj_dbvals: dict = obj._dbvals_  # type: ignore [attr-defined, type-arg]
  
    rbits = obj._rbits_  # type: ignore [has-type]
    wbits = obj._wbits_  # type: ignore [has-type]
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


def db_update_reverse(attr: "Attribute", obj: "Entity", old_dbval: Any, new_dbval: Any) -> None:
    reverse = attr.reverse
    if reverse is None: throw(NotImplementedError)
    if not reverse.is_collection:
        if old_dbval not in (None, NOT_LOADED): reverse.db_set(old_dbval, NOT_LOADED, True)
        if new_dbval is not None: reverse.db_set(new_dbval, obj, True)
    elif isinstance(reverse, Set):
        if old_dbval not in (None, NOT_LOADED): reverse.db_reverse_remove((old_dbval,), obj)
        if new_dbval is not None: reverse.db_reverse_add((new_dbval,), obj)
    else: throw(NotImplementedError)
