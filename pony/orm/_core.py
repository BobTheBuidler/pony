from collections import defaultdict
from typing import TYPE_CHECKING, Any, Final, Tuple, final

from pony.utils import localbase, throw

if TYPE_CHECKING:
  from pony.orm.core import EntityMeta


@final
class Local(localbase):
    def __init__(local):
        local.debug = False
        local.show_values = None
        local.debug_stack = []
        local.db2cache = {}
        local.db_context_counter = 0
        local.db_session = None
        local.prefetch_context_stack = []
        local.current_user = None
        local.perms_context = None
        local.user_groups_cache = {}
        local.user_roles_cache = defaultdict(dict)
    @property
    def prefetch_context(local):
        if local.prefetch_context_stack:
            return local.prefetch_context_stack[-1]
        return None
    def push_debug_state(local, debug, show_values):
        local.debug_stack.append((local.debug, local.show_values))
        if not suppress_debug_change:
            local.debug = debug
            local.show_values = show_values
    def pop_debug_state(local):
        local.debug, local.show_values = local.debug_stack.pop()


local: Final = Local()


class NotLoadedValueType(object):
    def __repr__(self): return 'NOT_LOADED'

NOT_LOADED: Final = NotLoadedValueType()


class DefaultValueType(object):
    def __repr__(self): return 'DEFAULT'

DEFAULT: Final = DefaultValueType()


def _parse_row_(entity: "EntityMeta", row: tuple, attr_offsets: dict) -> Tuple[type, tuple, dict]:  # type: ignore [type-arg]
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
    cache = local.db2cache[database]

    avdict = {}
    for attr in real_entity_subclass._attrs_:
        offsets = attr_offsets.get(attr)
        if offsets is None:
            continue
        if attr.is_discriminator:
            avdict[attr] = discr_value
        else:
            avdict[attr] = attr.parse_value(row, offsets, cache.dbvals_deduplication_cache)

    pkval = tuple(map(avdict.pop, entity._pk_attrs_))
    assert None not in pkval
    if not entity._pk_is_composite_: pkval = pkval[0]
    return real_entity_subclass, pkval, avdict


def _get_from_identity_map_(
    entity: "EntityMeta",
    pkval: Any,
    status: str,
    for_update: bool = False,
    undo_funcs=None,
    obj_to_init=None,
):
    cache = entity._database_._get_cache()
    pk_attrs = entity._pk_attrs_
    cache_index = cache.indexes[pk_attrs]
    if pkval is None: obj = None
    else: obj = cache_index.get(pkval)

    if obj is None: pass
    elif status == 'created':
        if entity._pk_is_composite_: pkval = ', '.join(map(str, pkval))
        throw(CacheIndexError, 'Cannot create %s: instance with primary key %s already exists'
                         % (obj.__class__.__name__, pkval))
    elif obj.__class__ is entity: pass
    elif issubclass(obj.__class__, entity): pass
    elif not issubclass(entity, obj.__class__): throw(TransactionError,
        'Unexpected class change from %s to %s for object with primary key %r' %
        (obj.__class__, entity, obj._pkval_))
    elif obj._rbits_ or obj._wbits_: throw(NotImplementedError)
    else: obj.__class__ = entity

    if obj is None:
        with cache.flush_disabled():
            obj = obj_to_init
            if obj_to_init is None:
                obj = object.__new__(entity)
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
                        if attr.reverse: attr.db_update_reverse(obj, NOT_LOADED, val)
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
                    if attr.reverse: attr.db_update_reverse(obj, NOT_LOADED, pkval)
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
):
    i = 0
    pkval = []
    for attr in entity._pk_attrs_:
        if attr.column is not None:
            val = raw_pkval[i]
            i += 1
            if not attr.reverse: val = attr.validate(val, None, entity, from_db=from_db)
            else: val = _get_by_raw_pkval_(attr.py_type (val,), from_db=from_db, seed=seed)
        else:
            if not attr.reverse: throw(NotImplementedError)
            vals = raw_pkval[i:i+len(attr.columns)]
            val = _get_by_raw_pkval_(attr.py_type, vals, from_db=from_db, seed=seed)
            i += len(attr.columns)
        pkval.append(val)

    final_pkval = tuple(pkval) if entity._pk_is_composite_ else pkval[0]
    obj = _get_from_identity_map_(entity, final_pkval, 'loaded', for_update) if seed else entity[final_pkval]
    assert obj._status_ != 'cancelled'
    return obj
  
