# These were in utils.py but we're not ready to compile the full file yet
import re
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


_ident_re: Final = re.compile(r'^[A-Za-z_]\w*\Z')

# is_ident = ident_re.match
def is_ident(string: str) -> bool:
    'is_ident(string) -> bool'
    return bool(_ident_re.match(string))

_name_parts_re: Final = re.compile(r'''
            [A-Z][A-Z0-9]+(?![a-z]) # ACRONYM
        |   [A-Z][a-z]*             # Capitalized or single capital
        |   [a-z]+                  # all-lowercase
        |   [0-9]+                  # numbers
        |   _+                      # underscores
        ''', re.VERBOSE)

def split_name(name: str) -> str:
    "split_name('Some_FUNNYName') -> ['Some', 'FUNNY', 'Name']"
    if not _ident_re.match(name):
        raise ValueError('Name is not correct Python identifier')
    list = _name_parts_re.findall(name)
    if not (list[0].strip('_') and list[-1].strip('_')):
        raise ValueError('Name must not starting or ending with underscores')
    return [ s for s in list if s.strip('_') ]

def uppercase_name(name: str) -> str:
    "uppercase_name('Some_FUNNYName') -> 'SOME_FUNNY_NAME'"
    return '_'.join(s.upper() for s in split_name(name))

def lowercase_name(name: str) -> str:
    "uppercase_name('Some_FUNNYName') -> 'some_funny_name'"
    return '_'.join(s.lower() for s in split_name(name))

def camelcase_name(name: str) -> str:
    "uppercase_name('Some_FUNNYName') -> 'SomeFunnyName'"
    return ''.join(s.capitalize() for s in split_name(name))

def mixedcase_name(name: str) -> str:
    "mixedcase_name('Some_FUNNYName') -> 'someFunnyName'"
    list = split_name(name)
    return list[0].lower() + ''.join(s.capitalize() for s in list[1:])
