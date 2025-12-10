# These were in utils.py but we're not ready to compile the full file yet
from datetime import datetime
from time import strptime

_CACHE_MAXSIZE: Final = 10_000
_TIMESTAMP_TO_DATETIME: Final[Dict[str, datetime]] = {}

def current_timestamp():
    return datetime2timestamp(datetime.now())

def datetime2timestamp(d: datetime) -> str:
    result = d.isoformat(' ')
    if len(result) == 19: return result + '.000000'
    return result

def timestamp2datetime(t: str) -> datetime:
    # we keep the cache in order of last usage
    dt = _TIMESTAMP_TO_DATETIME.pop(t, None)
    if dt is None:
        time_tuple = strptime(t[:19], '%Y-%m-%d %H:%M:%S')
        microseconds = int((t[20:26] + '000000')[:6])
        dt = datetime(*time_tuple[:6], microseconds)

    _TIMESTAMP_TO_DATETIME[t] = dt

    # trim the cache if necessary
    while len(_TIMESTAMP_TO_DATETIME) >= _CACHE_MAXSIZE:
        first_key = next(iter(_TIMESTAMP_TO_DATETIME))
        _TIMESTAMP_TO_DATETIME.pop(first_key)

    return dt
