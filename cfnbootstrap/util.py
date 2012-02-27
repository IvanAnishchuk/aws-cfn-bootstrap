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
import subprocess
import random
import logging
import time
import urllib2
import os.path
import re
import stat
log = logging.getLogger("cfn.init")

_trues = frozenset([True, 1, 'true', 'yes', 'y', '1'])

def interpret_boolean(input):
    """
    This tries to interpret if the user intended True
    I don't use python's boolean equivalent because it's
    likely that we're getting a string
    """
    if not input:
        return False

    input = input.lower().strip() if isinstance(input, basestring) else input

    return input in _trues

def extract_credentials(path):
    """
    Extract credentials from a file at path, returning tuple of (access_key, secret_key)
    Raises an exception if the file is readable by group or other.
    """
    if not os.path.isfile(path):
        raise IOError(None, "Credential file was not found at %s" % path)

    if os.name == 'posix':
        mode = os.stat(path)[stat.ST_MODE]

        if stat.S_IRWXG & mode or stat.S_IRWXO & mode:
            raise IOError(None, "Credential file cannot be accessible by group or other. Please chmod 600 the credential file.")

    access_key, secret_key = '', ''
    with file(path, 'r') as f:
        for line in (line.strip() for line in f):
            if line.startswith("AWSAccessKeyId="):
                access_key = line.partition('=')[2]
            elif line.startswith("AWSSecretKey="):
                secret_key = line.partition('=')[2]

    if not access_key or not secret_key:
        raise IOError(None, "Credential file must contain the keys 'AWSAccessKeyId' and 'AWSSecretKey'")

    return (access_key, secret_key)

_dot_split = re.compile(r'(?<!\\)\.')
_slash_replace = re.compile(r'\\(?=\.)')

def extract_value(metadata, path):
    """Returns a value from metadata (a dict) at a (possibly empty) path, where path is in dotted object syntax (like root.child.leaf)"""
    if not path:
        return metadata

    return_data = metadata
    for element in (_slash_replace.sub('', s) for s in _dot_split.split(path)):
        if not element in return_data:
            log.debug("No value at path %s (missing index: %s)", path, element)
            return None
        return_data = return_data[element]

    return return_data

def exponential_backoff(max_tries):
    """
    Returns a series of floating point numbers between 0 and 2^i-1 for i in 0 to max_tries
    """
    return [random.random() * (2**i - 1) for i in range(0, max_tries)]

def extend_backoff(durations):
    """
    Adds another exponential delay time to a list of delay times
    """
    durations.append(random.random() * (2**len(durations) - 1))

def _extract_http_error(e):
    return (e.code < 500, e.code==503, "HTTP Error %s : %s" % (e.code, e.msg))

_default_opener = urllib2.build_opener()

def urlopen_withretry(request_or_url, max_tries=5, http_error_extractor=_extract_http_error, opener = _default_opener):
    """
    Exponentially retries up to max_tries to open request_or_url.
    Raises an IOError on failure

    http_error_extractor is a function that takes a urllib2.HTTPError and returns a 3-tuple of
    (is_terminal, is_ignorable, message)
    """
    durations = exponential_backoff(max_tries)
    for i in durations:
        if i > 0:
            log.debug("Sleeping for %f seconds before retrying", i)
            time.sleep(i)

        try:
            return opener.open(request_or_url)
        except urllib2.HTTPError, e:
            terminal, ignorable, lastMessage = http_error_extractor(e)
            if terminal:
                raise IOError(None, lastMessage)
            elif ignorable:
                extend_backoff(durations)
            log.error(lastMessage)
        except urllib2.URLError, u:
            log.error("URLError: %s", u.reason)
            lastMessage = u.reason
    else:
        raise IOError(None, lastMessage)

class ProcessResult(object):
    """
    Return object for ProcessHelper

    """

    def __init__(self, returncode, stdout, stderr):
        self._returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    @property
    def returncode(self):
        return self._returncode

    @property
    def stdout(self):
        return self._stdout

    @property
    def stderr(self):
        return self._stderr

class ProcessHelper(object):
    """
    Helper to simplify command line execution

    """

    def __init__(self, cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=None, cwd=None):
        self._cmd = cmd
        self._stdout = stdout
        self._stderr = stderr
        self._env = env
        self._cwd = cwd

    def call(self):
        """
        Calls the command, returning a tuple of (returncode, stdout, stderr)
        """

        process = subprocess.Popen(self._cmd, stdout=self._stdout, stderr=self._stderr,
                                   shell=isinstance(self._cmd, basestring), env=self._env, cwd=self._cwd)
        returnData = process.communicate()

        return ProcessResult(process.returncode, returnData[0], returnData[1])
