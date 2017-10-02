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

# Json format related operations are wrapped in this module to make moking of those operations easier

import os
import copy
import collections
import stat
import time
import datetime
import decimal

try:
    import simplejson as json
except ImportError:
    import json

def setSafeMode(directory, filename):
    fullname = os.path.join(directory, filename)
    currentFileMode = stat.S_IMODE(os.stat(fullname).st_mode)
    currentFileMode = currentFileMode & 0600
    os.chmod(fullname, currentFileMode)

def create(directory, filename):
    if not os.path.isfile(os.path.join(directory, filename)):
        open(os.path.join(directory, filename), 'w').close()
    setSafeMode(directory, filename)
    
def read(directory, filename):
    try:
        with open(os.path.join(directory, filename), 'r') as fp:
            metadata = json.load(fp)
    except:
        metadata = {}
    return metadata

def write(directory, filename, metadata):
    with open(os.path.join(directory, filename), 'w') as fp:
        json.dump(metadata, fp)
    setSafeMode(directory, filename)

# JSON doesn't serialize deques and user defined types. Defining here our own conversion.
class Converter():
    def __init__(self, userDefinedTypes):
        # Markers for the manually serialized types
        # collection.deque is treated specially
        # datetime.datetime is also treated specially
        # User defined types are all treated uniformly
        self._userDefinedTypes = userDefinedTypes
        self._deque_marker = '_deque: special_serialization: not_regular_json_'
        self._datetime_marker = '_datetime: special_serialization: not_regular_json_'
        self._markers = {}
        for t in self._userDefinedTypes:
            self._markers[t] = '_' + t.__name__ + ': special_serialization: not_regular_json_'
        # The format used to serialize datetime
        self._datetime_format = '"%Y-%m-%dT%H:%M:%S.%f"'

    def serialize(self, data):
        raw = copy.deepcopy(data)
        if isinstance(raw, collections.deque):
            retval = [self.serialize(v) for v in raw]
            return {self._deque_marker : retval}
        elif isinstance(raw, datetime.datetime):
            retval = self._datetime2str(raw)
            return {self._datetime_marker : retval}
        else:
            for t in self._userDefinedTypes:
                if isinstance(raw, t):
                    return raw.serialize(self._markers[t])
            return raw

    def deserialize(self, data):
        serialized = copy.deepcopy(data)
        if not isinstance(serialized, dict):
            return serialized
        if self._deque_marker in serialized:
            serialized = serialized[self._deque_marker]
            return collections.deque([self.deserialize(v) for v in serialized])
        elif self._datetime_marker in serialized:
            serialized = serialized[self._datetime_marker]
            return self._str2datetime(serialized)
        else:
            for t in self._userDefinedTypes:
                if self._markers[t] in serialized:
                    serialized = serialized[self._markers[t]]
                    return t.from_json(serialized)
            return serialized

    def _datetime2str(self, d):
        return unicode(d.strftime(self._datetime_format))

    def _str2datetime(self, t):
        return datetime.datetime.strptime(t, self._datetime_format)

