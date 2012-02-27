#==============================================================================
# Copyright 2011 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Amazon Software License (the "License"). You may not use
# this file except in compliance with the License. A copy of the License is
# located at
#
#       http://aws.amazon.com/asl/
#
# or in the "license" file accompanying this file. This file is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, express or
# implied. See the License for the specific language governing permissions
# and limitations under the License.
#==============================================================================

from __future__ import with_statement
import logging.config
import os.path
import sys

def _getLogFile(filename):
    if os.name == 'nt':
        logdir = os.path.expandvars('${SystemDrive}\cfn\log')
        if not os.path.exists(logdir):
            os.makedirs(logdir)
        return logdir + os.path.sep + filename

    return '/var/log/%s' % filename


def configureLogging(level='INFO', quiet=False, filename='cfn-init.log'):
    output_file=_getLogFile(filename)
    try:
        with file(os.path.dirname(__file__) + os.path.sep + 'logging.conf') as f:
            logging.config.fileConfig(f, {'conf_level' : level, 'conf_handler' : 'default', 'conf_file' : output_file})
    except IOError:
        if not quiet:
            print >> sys.stderr, "Could not open %s for logging.  Using stderr instead." % output_file
        with file(os.path.dirname(__file__) + os.path.sep + 'logging.conf') as f:
            logging.config.fileConfig(f, {'conf_level' : level, 'conf_handler' : 'tostderr'})

configureLogging(quiet=True)