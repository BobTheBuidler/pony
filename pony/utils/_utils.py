# These were in utils.py but we're not ready to compile the full file yet
import re
import types
from collections import defaultdict
from datetime import datetime
from time import strptime
from typing import Any, DefaultDict, Dict, Final, Iterable, List, TypeVar, overload

_T = TypeVar("_T")

InstanceType: Final = types.InstanceType

_CACHE_MAXSIZE: Final = 10_000
_TIMESTAMP_TO_DATETIME: Final[Dict[str, datetime]] = {}

def current_timestamp() -> str:
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

def split_name(name: str) -> List[str]:
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

expr1_re: Final = re.compile(r'''
        ([A-Za-z_]\w*)  # identifier (group 1)
    |   ([(])           # open parenthesis (group 2)
    ''', re.VERBOSE)

expr2_re: Final = re.compile(r'''
     \s*(?:
            (;)                 # semicolon (group 1)
        |   (\.\s*[A-Za-z_]\w*) # dot + identifier (group 2)
        |   ([([])              # open parenthesis or braces (group 3)
        )
    ''', re.VERBOSE)

expr3_re: Final = re.compile(r"""
        [()[\]]                   # parenthesis or braces (group 1)
    |   '''(?:[^\\]|\\.)*?'''     # '''triple-quoted string'''
    |   \"""(?:[^\\]|\\.)*?\"""   # \"""triple-quoted string\"""
    |   '(?:[^'\\]|\\.)*?'        # 'string'
    |   "(?:[^"\\]|\\.)*?"        # "string"
    """, re.VERBOSE)

def parse_expr(s: str, pos: int = 0) -> Tuple[str, bool]:
    z = 0
    match = expr1_re.match(s, pos)
    if match is None: raise ValueError()
    start = pos
    i = match.lastindex
    if i == 1: pos = match.end()  # identifier
    elif i == 2: z = 2  # "("
    else: assert False  # pragma: no cover
    while True:
        match = expr2_re.match(s, pos)
        if match is None: return s[start:pos], z==1
        pos = match.end()
        i = match.lastindex
        if i == 1: return s[start:pos], False  # ";" - explicit end of expression
        elif i == 2: z = 2  # .identifier
        elif i == 3:  # "(" or "["
            pos = match.end()
            counter = 1
            open = match.group(i)
            if open == '(': close = ')'
            elif open == '[': close = ']'; z = 2
            else: assert False  # pragma: no cover
            while True:
                match = expr3_re.search(s, pos)
                if match is None: raise ValueError()
                pos = match.end()
                x = match.group()
                if x == open: counter += 1
                elif x == close:
                    counter -= 1
                    if not counter: z += 1; break
        else: assert False  # pragma: no cover

def tostring(x: Any) -> str:
    if isinstance(x, str): return x
    if hasattr(x, '__unicode__'):
        try: return str(x)
        except: pass
    if hasattr(x, 'makeelement'): return cElementTree.tostring(x)
    try: return str(x)
    except: pass
    try: return repr(x)
    except: pass
    if type(x) == InstanceType: return '<%s instance at 0x%X>' % (x.__class__.__name__)
    return '<%s object at 0x%X>' % (x.__class__.__name__)

def strjoin(
    sep: str,
    strings: Iterable[str],
    source_encoding: str = 'ascii',
    dest_encoding: str | None = None,
) -> str:
    "Can join mix of str and byte strings in different encodings"
    strings = list(strings)
    try: return sep.join(strings)
    except UnicodeDecodeError: pass
    for i, s in enumerate(strings):
        if isinstance(s, str):
            strings[i] = s.decode(source_encoding, 'replace').replace(u'\ufffd', '?')
    result = sep.join(strings)
    if dest_encoding is None: return result
    return result.encode(dest_encoding, 'replace')

@overload
def group_concat(items: Iterable[Any], sep: Any = ',') -> str:
    ...
@overload
def group_concat(items: None, sep: Any = ',') -> None:
    ...
def group_concat(items: Iterable[Any] | None, sep: Any = ',') -> str | None:
    if items is None:
        return None
    return str(sep).join(map(str, items))

def coalesce(*args: _T) -> _T:
    for arg in args:
        if arg is not None:
            return arg
    return None

def distinct(iter: Iterable[_T]) -> DefaultDict[_T, int]:
    d: DefaultDict[_T, int] = defaultdict(int)
    for item in iter:
        d[item] = d[item] + 1
    return d

def concat(*args: Any) -> str:
    return ''.join(map(tostring, args))

codeobjects: Final[dict[int, object]] = {}

def get_codeobject_id(codeobject: object) -> int:
    codeobject_id = id(codeobject)
    if codeobject_id not in codeobjects:
        codeobjects[codeobject_id] = codeobject
    return codeobject_id

def is_utf8(encoding: str) -> bool:
    return encoding.upper().replace('_', '').replace('-', '') in ('UTF8', 'UTF', 'U8')
