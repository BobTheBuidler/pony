from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from pony.orm.core import Entity

def _get_from_identity_map_(
    entity: "Entity",
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
