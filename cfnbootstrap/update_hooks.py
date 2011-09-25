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
import logging
import os
import shelve
import contextlib
from cfnbootstrap.cfn_client import CloudFormationClient
from cfnbootstrap.util import ProcessHelper
import tempfile
from cfnbootstrap import util
try:
    import simplejson as json
except ImportError:
    import json

log = logging.getLogger("cfn.hup")

class UpdateError(Exception):

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg

class Hook(object):

    def __init__(self, name, triggers, path, action, runas):
        self._triggers = triggers[:]
        self._path = path
        self._action = action
        self._name = name
        self._runas = runas

    @property
    def triggers(self):
        return self._triggers

    @property
    def path(self):
        return self._path

    @property
    def action(self):
        return self._action

    @property
    def name(self):
        return self._name
    
    @property
    def runas(self):
        return self._runas

class HookProcessor(object):
    """Processes update hooks"""

    def __init__(self, hooks, stack_name, access_key, secret_key, url):
        """Takes a list of Hook objects and processes them"""
        self.hooks = hooks
        self.dir = '/var/lib/cfn-hup/data'
        if not os.path.isdir(self.dir):
            log.debug("Creating %s", self.dir)
            try:
                os.makedirs(self.dir)
            except OSError:
                log.error("Could not create %s; using temporary directory", self.dir)
                self.dir = tempfile.mkdtemp()

        self.client = CloudFormationClient(access_key, secret_key, url)
        self.stack_name = stack_name

    def process(self):
        with contextlib.closing(shelve.open('%s/metadata_db' % self.dir)) as shelf:
            self._resource_cache = {}
            for hook in self.hooks:
                try:
                    self._process_hook(hook, shelf)
                except UpdateError:
                    raise
                except Exception:
                    log.exception("Exception caught while running hook %s", hook.name)


    def _process_hook(self, hook, shelf):
        new_data = self._retrieve_path_data(hook.path)
        old_data = shelf.get(hook.name + "|" + hook.path, None)

        if 'post.add' in hook.triggers and not old_data and new_data:
            log.info("Previous state not found; action for %s will be run", hook.name)
        elif 'post.remove' in hook.triggers and old_data and not new_data:
            log.info('Path %s was removed; action for %s will be run', hook.path, hook.name)
        elif 'post.update' in hook.triggers and old_data and new_data and old_data != new_data:
            log.info("Data has changed from previous state; action for %s will be run", hook.name)
        else:
            log.debug("No change in path %s for hook %s", hook.path, hook.name)
            shelf[hook.name + '|' + hook.path] = new_data
            return

        log.info("Running action for %s", hook.name)
        action_env = dict(os.environ)
        if old_data:
            action_env['CFN_OLD_METADATA'] = self._as_string(old_data)
        if new_data:
            action_env['CFN_NEW_METADATA'] = self._as_string(new_data)

        action = hook.action
        if hook.runas:
            action = ['su', hook.runas, '-c', action]
        
        result = ProcessHelper(action, env=action_env).call()  
                
        if result.returncode:
            log.warn("Action for %s exited with %s; will retry on next iteration", hook.name, result.returncode)
        else:
            shelf[hook.name + '|' + hook.path] = new_data
        log.debug("Action for %s output: %s", hook.name, result.stdout if result.stdout else '<None>')

    def _as_string(self, obj):
        if isinstance(obj, basestring):
            return obj
        return json.dumps(obj)

    def _retrieve_path_data(self, path):
        parts = path.split('.', 3)
        if len(parts) < 3:
            raise UpdateError("Unsupported path: paths must be in the form Resources.<logical resource id>.Metadata(.<optional subkey>). Input: %s" % path)

        if parts[0].lower() != 'resources':
            raise UpdateError('Unsupported path: only changes to Resources are supported (path: %s)' % path)
        if parts[2].lower() != 'metadata':
            raise UpdateError('Unsupported path: only Metadata changes are supported (path: %s)' % path)

        logical_id = parts[1]
        subpath = ('' if len(parts) < 4 else parts[3])

        if logical_id not in self._resource_cache:
            self._resource_cache[logical_id] = self.client.describe_stack_resource(logical_id, self.stack_name)

        resource = self._resource_cache[logical_id]

        if not resource.metadata:
            log.warn("No metadata for %s in %s", logical_id, self.stack_name)
            return None
        
        return util.extract_value(resource.metadata, subpath)