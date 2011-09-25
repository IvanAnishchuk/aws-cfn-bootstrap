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

import pwd
import grp
import os
import logging
from cfnbootstrap.construction_errors import ToolError
    
def set_owner_and_group(filename, owner_name, group_name):
    owner_id = -1
    group_id = -1
    
    if owner_name:
        try:
            owner_id = pwd.getpwnam(owner_name)[2]
        except KeyError:
            raise ToolError("%s is not a valid user name" % owner_name)
    
    if group_name:
        try:
            group_id = grp.getgrnam(group_name)[2]
        except KeyError:
            raise ToolError("%s is not a valid group name" % group_name)
            
    if group_id != -1 or owner_id != -1:
        logging.debug("Setting owner %s and group %s for %s", owner_id, group_id, filename)
        os.lchown(filename, owner_id, group_id)