from __future__ import absolute_import, print_function

import os, sys
from os.path import dirname
from typing import Final, Literal

__version__: Final = '0.7.19'


Mode = Literal["GAE-LOCAL", "GAE-SERVER", "MOD_WSGI", "INTERACTIVE", "FCGI-FLIP", "UWSGI", "FLASK", "CHERRYPY", "BOTTLE", "UNKNOWN"]

def detect_mode() -> Mode:
    try: import google.appengine
    except ImportError: pass
    else:
        if os.getenv('SERVER_SOFTWARE', '').startswith('Development'):
            return 'GAE-LOCAL'
        return 'GAE-SERVER'

    try: from mod_wsgi import version
    except: pass
    else: return 'MOD_WSGI'

    main = sys.modules['__main__']

    if not hasattr(main, '__file__'): # console
        return 'INTERACTIVE'

    if os.getenv('IPYTHONENABLE', '') == 'True':
        return 'INTERACTIVE'

    if getattr(main, 'INTERACTIVE_MODE_AVAILABLE', False): # pycharm console
        return 'INTERACTIVE'

    if 'flup.server.fcgi' in sys.modules: return 'FCGI-FLUP'
    if 'uwsgi' in sys.modules: return 'UWSGI'
    if 'flask' in sys.modules: return 'FLASK'
    if 'cherrypy' in sys.modules: return 'CHERRYPY'
    if 'bottle' in sys.modules: return 'BOTTLE'
    return 'UNKNOWN'

MODE: Final = detect_mode()

main_file = None
if MODE == 'MOD_WSGI':
    for module_name, module in sys.modules.items():
        if module_name.startswith('_mod_wsgi_'):
            main_file = module.__file__
            break
elif MODE != 'INTERACTIVE':
    main_file = sys.modules['__main__'].__file__

MAIN_FILE: Final = main_file
del main_file

MAIN_DIR: Final = None if MAIN_FILE is None else dirname(MAIN_FILE)

PONY_DIR: Final = dirname(__file__)
