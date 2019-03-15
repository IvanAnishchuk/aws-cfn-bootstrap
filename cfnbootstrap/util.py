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
import hashlib
from optparse import OptionGroup
from requests.exceptions import ConnectionError, HTTPError, Timeout, \
    SSLError
import StringIO
import imp
import logging
import os.path
import random
import re
import requests
import stat
import subprocess
import sys
import time

try:
    import simplejson as json
except ImportError:
    import json

log = logging.getLogger("cfn.init")
wire_log = logging.getLogger("wire")

#==============================================================================
# HTTP backoff-and-retry
#==============================================================================

def exponential_backoff(max_tries, max_sleep=20):
    """
    Returns a series of floating point numbers between 0 and min(max_sleep, 2^i-1) for i in 0 to max_tries
    """
    return [random.random() * min(max_sleep, (2**i - 1)) for i in range(0, max_tries)]

def extend_backoff(durations, max_sleep=20):
    """
    Adds another exponential delay time to a list of delay times
    """
    durations.append(random.random() * min(max_sleep, (2**len(durations) - 1)))

def _extract_http_error(resp):
    if resp.status_code == 503:
        retry_mode='RETRIABLE_FOREVER'
    elif resp.status_code < 500 and resp.status_code not in (404, 408):
        retry_mode='TERMINAL'
    else:
        retry_mode='RETRIABLE'

    return RemoteError(resp.status_code, "HTTP Error %s : %s" % (resp.status_code, resp.text), retry_mode)

class EtagCheckedResponse(object):

    def __init__(self, response):
        self._response = check_status(response)
        etag = response.headers['etag'].strip('"') if 'etag' in response.headers and is_s3_url(response.url) else None
        if etag and '-' in etag:
            log.warn('cannot check consistency of file uploaded multipart; etag has - character present')
            etag = None

        self._etag = etag
        self._digest = hashlib.md5() if self._etag else NoOpDigest()

    def _check_digest(self):
        if not self._etag:
            return

        final_digest = self._digest.hexdigest()
        if self._etag != final_digest:
            raise ChecksumError("Expected digest %s; received %s" % (self._etag, final_digest))

    def write_to(self, dest):
        dest.seek(0, 0)
        dest.truncate()
        for c in self._response.iter_content(10 * 1024):
            dest.write(c)
            self._digest.update(c)
        self._check_digest()

    def contents(self):
        content = self._response.content
        self._digest.update(content)
        self._check_digest()
        return content

class ChecksumError(IOError):

    def __init__(self, msg):
        super(ChecksumError, self).__init__(None, msg)

class NoOpDigest():

    def __init__(self):
        self.digest_size = -1
        self.block_size = -1

    def update(self, content):
        pass

    def hexdigest(self):
        return None

    def digest(self):
        return None

    def copy(self):
        return self

class RemoteError(IOError):

    retry_modes = frozenset(['TERMINAL', 'RETRIABLE', 'RETRIABLE_FOREVER'])

    def __init__(self, code, msg, retry_mode='RETRIABLE'):
        super(RemoteError, self).__init__(code, msg)
        if not retry_mode in RemoteError.retry_modes:
            raise ValueError("Invalid retry mode: %s" % retry_mode)
        self.retry_mode = retry_mode

def retry_on_failure(max_tries = 5, http_error_extractor=_extract_http_error):
    def _decorate(f):
        def _retry(*args, **kwargs):
            durations = exponential_backoff(max_tries)
            for i in durations:
                if i > 0:
                    log.debug("Sleeping for %f seconds before retrying", i)
                    time.sleep(i)

                try:
                    return f(*args, **kwargs)
                except SSLError, e:
                    log.exception("SSLError")
                    raise RemoteError(None, str(e), retry_mode='TERMINAL')
                except ChecksumError, e:
                    log.exception("Checksum mismatch")
                    last_error = RemoteError(None, str(e))
                except ConnectionError, e:
                    log.exception('ConnectionError')
                    last_error = RemoteError(None, str(e))
                except HTTPError, e:
                    last_error = http_error_extractor(e.response)
                    if last_error.retry_mode == 'TERMINAL':
                        raise last_error
                    elif last_error.retry_mode == 'RETRIABLE_FOREVER':
                        extend_backoff(durations)

                    log.exception(last_error.strerror)
                except Timeout, e:
                    log.exception('Timeout')
                    last_error = RemoteError(None, str(e))
            else:
                raise last_error
        return _retry
    return _decorate

#==============================================================================
# Certificate loading
#==============================================================================

def main_is_frozen():
    return (hasattr(sys, "frozen") or # new py2exe
            hasattr(sys, "importers") # old py2exe
            or imp.is_frozen("__main__")) # tools/freeze

def get_cert():
    if main_is_frozen():
        return os.path.join(os.path.dirname(sys.executable), 'cacert.pem')
    return True # True tells Requests to find its own cert

#==============================================================================
# Instance metadata
#==============================================================================

@retry_on_failure(max_tries=10)
def get_instance_identity_document():
    resp = requests.get('http://169.254.169.254/latest/dynamic/instance-identity/document')
    resp.raise_for_status()
    return resp.text.rstrip()

@retry_on_failure(max_tries=10)
def get_instance_identity_signature():
    resp = requests.get('http://169.254.169.254/latest/dynamic/instance-identity/signature')
    resp.raise_for_status()
    return resp.text.rstrip()

_instance_id = '__unset'

@retry_on_failure(max_tries=10)
def _fetch_instance_id():
    resp = requests.get('http://169.254.169.254/latest/meta-data/instance-id', timeout=2)
    resp.raise_for_status()
    return resp.text.strip()

def get_instance_id():
    """
    Attempt to retrieve an EC2 instance id, returning None if this is not EC2
    """
    global _instance_id
    if _instance_id == '__unset':
        try:
            _instance_id = _fetch_instance_id()
        except IOError:
            log.exception("Exception retrieving InstanceId")
            _instance_id =  None

    return _instance_id

def is_ec2():
    return get_instance_id() is not None

@retry_on_failure(max_tries=10)
def get_role_creds(name):
    resp = requests.get('http://169.254.169.254/latest/meta-data/iam/security-credentials/%s' % name)
    resp.raise_for_status()
    role = json_from_response(resp)
    return role['AccessKeyId'], role['SecretAccessKey'], role['Token']

_trues = frozenset([True, 1, 'true', 'yes', 'y', '1'])

#==============================================================================
# Miscellaneous
#==============================================================================

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

def json_from_response(resp):
    if hasattr(resp, 'json'):
        if callable(resp.json):
            return resp.json()
        return resp.json
    return json.load(StringIO.StringIO(resp.content))

def is_s3_url(url):
    return re.match(r'https?://([-\w.]+?\.)?s3(-[\w\d-]+)?.amazonaws.com.*', url, re.IGNORECASE) is not None

#==============================================================================
# Command-line (credentials, options, etc)
#==============================================================================

def get_proxy_options(parser):
    proxy_group = OptionGroup(parser, "Proxy", "Options for specifying proxies. Format: [scheme://][user:password@]host:port")

    proxy_group.add_option("", "--http-proxy", help="A (non-SSL) HTTP proxy", type="string", dest="http_proxy")
    proxy_group.add_option("", "--https-proxy", help="An HTTPS proxy", type="string", dest="https_proxy")

    return proxy_group

def get_proxyinfo(options):
    return_info = {}
    if options.http_proxy:
        return_info['http'] = options.http_proxy
    if options.https_proxy:
        return_info['https'] = options.https_proxy

    return return_info if return_info else None

def get_cred_options(parser):
    creds_group = OptionGroup(parser, "AWS Credentials", "Options for specifying AWS Account Credentials.")

    creds_group.add_option("-f", "--credential-file", help="A credential file, readable only by the owner, with keys "
                                                           "'AWSAccessKeyId' and 'AWSSecretKey'",
                           type="string", dest="credential_file")

    creds_group.add_option("", "--role", help="An IAM Role",
        type="string", dest="iam_role")

    creds_group.add_option("", "--access-key", help="An AWS Access Key",
                           type="string", dest="access_key")
    creds_group.add_option("", "--secret-key", help="An AWS Secret Key",
                           type="string", dest="secret_key")

    return creds_group

def get_creds_or_die(options):
    if options.credential_file:
        try:
            return extract_credentials(options.credential_file)
        except IOError, e:
            print >> sys.stderr, "Error retrieving credentials from file:\n\t%s" % e.strerror
            sys.exit(1)
    elif options.iam_role:
        return Credentials(*get_role_creds(options.iam_role))
    else:
        return Credentials(options.access_key, options.secret_key)


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

    return Credentials(access_key, secret_key)

#==============================================================================
# Process running utilities
#==============================================================================

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
        if not env:
            self._env = None
        elif os.name == 'nt': # stringify the environment in Windows, which cannot handle unicodes
            self._env = dict(((str(k), str(v)) for k,v in env.iteritems()))
        else:
            self._env = dict(env)
        self._cwd = cwd

    def call(self):
        """
        Calls the command, returning a tuple of (returncode, stdout, stderr)
        """

        process = subprocess.Popen(self._cmd, stdout=self._stdout, stderr=self._stderr,
                                   shell=isinstance(self._cmd, basestring), env=self._env, cwd=self._cwd)
        returnData = process.communicate()

        return ProcessResult(process.returncode, returnData[0], returnData[1])


class Credentials(object):
    '''
    AWS Credentials
    '''

    def __init__(self, access_key, secret_key, security_token=None, expiration=None):
        self._access_key = access_key
        self._secret_key = secret_key
        self._security_token = security_token
        self._expiration = expiration

    @property
    def access_key(self):
        return self._access_key

    @property
    def secret_key(self):
        return self._secret_key

    @property
    def security_token(self):
        return self._security_token

    @property
    def expiration(self):
        return self._expiration


def log_request(req):
    wire_log.debug('Request: %s %s [headers: %s]', req.method, req.full_url, req.headers)

def log_response(resp, *args, **kwargs):
    wire_log.debug('Response: %s %s [headers: %s]', resp.status_code, resp.url, resp.headers)
    if not resp.ok:
        wire_log.debug('Response error: %s', resp.content)
#==============================================================================
# Requests compat
#==============================================================================

_IS_1_DOT_0_REQUESTS = tuple(int(v) for v in requests.__version__.split('.')) >= (1, 0, 0)
_IS_1_DOT_2_REQUESTS = tuple(int(v) for v in requests.__version__.split('.')) >= (1, 2, 0)

def get_hooks():
    hooks = { 'response' : log_response }
    if not _IS_1_DOT_2_REQUESTS:
        hooks['pre_request'] = log_request
    return hooks


def req_opts(kwargs):
    kwargs = dict(kwargs) if kwargs else {}
    kwargs['verify'] = get_cert()
    kwargs['hooks'] = get_hooks()

    if _IS_1_DOT_0_REQUESTS:
        kwargs['stream'] = True
    else:
        kwargs['prefetch'] = False

    return kwargs

def check_status(resp):
    resp.raise_for_status()
    return resp