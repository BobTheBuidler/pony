from typing import Any, Final, final

from mypy_extensions import mypyc_attr

import pony
from pony.utils import localbase


@final
@mypyc_attr(allow_interpreted_subclasses=True)
class Pool(localbase):
    con: Any  # TODO: type this properly
    pid: int | None
    forked_connections: Final[list[tuple[Any, int]]] = []
    def __init__(
        pool,
        dbapi_module: types.ModuleType,
        *args: Any,
        **kwargs: Any,
) -> None: # called separately in each thread
        pool.dbapi_module: Final = dbapi_module
        pool.args: Final = args
        pool.kwargs: Final = kwargs
        pool.con = pool.pid = None
    def connect(pool):
        pid = os.getpid()
        if pool.con is not None and pool.pid != pid:
            pool.forked_connections.append((pool.con, pool.pid))
            pool.con = pool.pid = None
        core = pony.orm.core
        is_new_connection = False
        if pool.con is None:
            if core.local.debug: core.log_orm('GET NEW CONNECTION')
            is_new_connection = True
            pool._connect()
            pool.pid = pid
        elif core.local.debug:
            core.log_orm('GET CONNECTION FROM THE LOCAL POOL')
        return pool.con, is_new_connection
    def _connect(pool) -> None:
        pool.con = pool.dbapi_module.connect(*pool.args, **pool.kwargs)
    def release(pool, con: Any) -> None:
        assert con is pool.con
        try: con.rollback()
        except:
            pool.drop(con)
            raise
    def drop(pool, con: Any) -> None:
        assert con is pool.con, (con, pool.con)
        pool.con = None
        con.close()
    def disconnect(pool) -> None:
        con = pool.con
        pool.con = None
        if con is not None: con.close()
