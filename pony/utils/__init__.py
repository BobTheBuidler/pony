import _strptime as builtins_strptime

from pony.utils import _strptime
from pony.utils._utils import *
from pony.utils.utils import *
from pony.utils.properties import *

# patch the builtin module with our faster _strptime utils
setattr(builtins_strptime, "_strptime", _strptime._strptime)
setattr(builtins_strptime, "_strptime_time", _strptime._strptime_time)
setattr(builtins_strptime, "_strptime_datetime", _strptime._strptime_datetime)
