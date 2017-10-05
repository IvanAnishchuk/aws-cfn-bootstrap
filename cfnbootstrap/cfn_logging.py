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

# Wrapper for the CFN logging operations in order to avoid string encoding problems
# Still using logging.Logger methods, but provided with UTF-8 encoded arguments
# Takes the (unique) logger returned by logging.getLogger()
class CfnLogger:
    def __init__(self, logger):
        self._log = logger
    
    def debug(self, msg, *args, **kwargs):
        self._log.debug(to_unicode(msg), *to_unicode_list(args), **to_unicode_kwargs_dictionary(kwargs))

    def info(self, msg, *args, **kwargs):
        self._log.info(to_unicode(msg), *to_unicode_list(args), **to_unicode_kwargs_dictionary(kwargs))

    def warning(self, msg, *args, **kwargs):
        self._log.warning(to_unicode(msg), *to_unicode_list(args), **to_unicode_kwargs_dictionary(kwargs))

    def error(self, msg, *args, **kwargs):
        self._log.error(to_unicode(msg), *to_unicode_list(args), **to_unicode_kwargs_dictionary(kwargs))

    def critical(self, msg, *args, **kwargs):
        self._log.critical(to_unicode(msg), *to_unicode_list(args), **to_unicode_kwargs_dictionary(kwargs))

    def log(self, msg, *args, **kwargs):
        self._log.log(to_unicode(msg), *to_unicode_list(args), **to_unicode_kwargs_dictionary(kwargs))

    def exception(self, msg, *args, **kwargs):
        self._log.exception(to_unicode(msg), *to_unicode_list(args), **to_unicode_kwargs_dictionary(kwargs))

# If str, convert it to Unicode - otherwise untouched
def to_unicode(x):
    if isinstance(x, str):
        return x.decode('utf-8')
    return x

def to_unicode_list(a_list):
    return [to_unicode(x) for x in a_list]

# Convert it to Unicode only the key (of the dictionary) that equals the filter - the rest of the keys stay untouched
def to_unicode_filter_dict(a_key, a_dictionary, a_filter):
    if a_key == a_filter:
        return to_unicode(a_dictionary[a_key])
    return a_dictionary[a_key]

# kwargs['extra'] might also have a non-Unicode encoding
def to_unicode_kwargs_dictionary(a_dictionary):
    retval = {}
    for x in a_dictionary.keys():
        retval[x] = to_unicode_filter_dict(x, a_dictionary, 'extra')
    return retval

