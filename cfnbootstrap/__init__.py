#==============================================================================
# Copyright 2011 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#==============================================================================
import logging.config
import os.path
import sys
import StringIO

class NullHandler(logging.Handler):
    def emit(self, record):
        pass

_config ="""[loggers]
keys=root,cfninit,cfnclient,cfnhup,wire
[handlers]
keys=%(all_handlers)s,null
[formatters]
keys=amzn
[logger_root]
level=NOTSET
handlers=%(root_handler)s
[logger_cfninit]
level=NOTSET
handlers=%(root_handler)s
qualname=cfn.init
propagate=0
[logger_wire]
level=NOTSET
handlers=%(wire_handler)s
qualname=wire
propagate=0
[logger_cfnhup]
level=NOTSET
handlers=%(root_handler)s
qualname=cfn.hup
propagate=0
[logger_cfnclient]
level=NOTSET
handlers=%(root_handler)s
qualname=cfn.client
propagate=0
[handler_default]
class=handlers.RotatingFileHandler
level=%(conf_level)s
formatter=amzn
args=('%(conf_file)s', 'a', 5242880, 5, 'UTF-8')
[handler_wire]
class=handlers.RotatingFileHandler
level=DEBUG
formatter=amzn
args=('%(wire_file)s', 'a', 5242880, 5, 'UTF-8')
[handler_null]
class=cfnbootstrap.NullHandler
args=()
[handler_tostderr]
class=StreamHandler
level=%(conf_level)s
formatter=amzn
args=(sys.stderr,)
[formatter_amzn]
format=%(asctime)s [%(levelname)s] %(message)s
datefmt=
class=logging.Formatter
"""

def _getLogFile(filename):
    if os.name == 'nt':
        logdir = os.path.expandvars(r'${SystemDrive}\cfn\log')
        if not os.path.exists(logdir):
            os.makedirs(logdir)
        return logdir + os.path.sep + filename

    return '/var/log/%s' % filename


def configureLogging(level='INFO', quiet=False, filename='cfn-init.log', log_dir=None, wire_log=True):
    if not log_dir:
        output_file=_getLogFile(filename)
        wire_file =_getLogFile('cfn-wire.log') if wire_log else None
    else:
        output_file = os.path.join(log_dir, filename)
        wire_file = os.path.join(log_dir, 'cfn-wire.log') if wire_log else None

    config = {'conf_level': level,
              'all_handlers': 'default' + (',wire' if wire_log else ''),
              'root_handler' : 'default',
              'wire_handler': 'wire' if wire_log else 'null',
              'conf_file': output_file}

    if wire_file:
        config['wire_file'] = wire_file

    try:
        logging.config.fileConfig(StringIO.StringIO(_config), config)
    except IOError:
        config['all_handlers'] = 'tostderr'
        config['root_handler'] = 'tostderr'
        config['wire_handler'] = 'null'
        if not quiet:
            print >> sys.stderr, "Could not open %s for logging.  Using stderr instead." % output_file
        logging.config.fileConfig(StringIO.StringIO(_config), config)

configureLogging(quiet=True, wire_log=True)