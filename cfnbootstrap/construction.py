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
"""
A library for building an installation from metadata

Classes:
Contractor - orchestrates the build process
Carpenter - does the concrete work of applying metadata to the installation
Tool - performs a specific task on an installation
ToolError - a base exception type for all tools

CloudFormationCarpenter - Orchestrates a non-delegated installation
YumTool - installs packages via yum

"""
from __future__ import with_statement
from cfnbootstrap.construction_errors import BuildError
from cfnbootstrap.service_tools import SysVInitTool
from cfnbootstrap.apt_tool import AptTool
from cfnbootstrap.file_tool import FileTool
from cfnbootstrap.rpm_tools import RpmTool, YumTool
from cfnbootstrap.lang_package_tools import PythonTool, GemTool
from cfnbootstrap.sources_tool import SourcesTool
import collections
import logging

log = logging.getLogger("cfn.init")

class CloudFormationCarpenter(object):
    """
    Takes a model and uses tools to make it reality
    """

    _packageTools = { "yum" : YumTool,
                      "rubygems" : GemTool,
                      "python" : PythonTool,
                      "rpm" : RpmTool,
                      "apt" : AptTool }

    _pkgOrder = ["dpkg", "rpm", "apt", "yum"]

    _serviceTools = { "sysvinit" : SysVInitTool }

    @staticmethod
    def _pkgsort(x, y):
        order = CloudFormationCarpenter._pkgOrder
        if x[0] in order and y[0] in order:
            return cmp(order.index(x[0]), order.index(y[0]))
        elif x[0] in order:
            return -1
        elif y[0] in order:
            return 1
        else:
            return cmp(x[0].lower(), y[0].lower())

    def __init__(self, files, packages, services, sources):
        self._files = files
        self._packages = packages
        self._services = services
        self._sources = sources

    def build(self):
        changes = collections.defaultdict(list)
        
        changes['packages'] = collections.defaultdict(list)
        if self._packages:
            for manager, packages in sorted(self._packages.iteritems(), cmp=CloudFormationCarpenter._pkgsort):
                if manager in CloudFormationCarpenter._packageTools:
                    changes['packages'][manager] = CloudFormationCarpenter._packageTools[manager]().apply(packages)
                else:
                    log.warn('Unsupported package manager: %s', manager)
        else:
            log.debug("No packages specified")

        if self._sources:
            changes['sources'] = SourcesTool().apply(self._sources)
        else:
            log.debug("No sources specified")

        if self._files:
            changes['files'] = FileTool().apply(self._files)
        else:
            log.debug("No files specified")

        if self._services:
            for manager, services in self._services.iteritems():
                if manager in CloudFormationCarpenter._serviceTools:
                    CloudFormationCarpenter._serviceTools[manager]().apply(services, changes)
                else:
                    log.warn("Unsupported service manager: %s", manager)
        else:
            log.debug("No services specified")
    

class Contractor(object):
    """
    Takes in a metadata model and forces the environment to match it.
    Returns the "output" key as a string on success, if it exists

    """

    _configKey = "AWS::CloudFormation::Init"

    def __init__(self, model):
        initModel = model[Contractor._configKey]
        if not initModel:
            raise ValueError("Model does not contain '%s'" % Contractor._configKey)

        config = initModel.get("config", dict())
        self._files = config.get("files")
        self._packages = config.get("packages")
        self._services = config.get("services")
        self._sources = config.get("sources")

    def build(self):
        """Does the work described by the model"""

        try:
            CloudFormationCarpenter(self._files, self._packages, self._services, self._sources).build()
        except BuildError, e:
            log.exception("Error encountered during build: %s", str(e))
            raise

    @classmethod
    def metadataValid(cls, metadata):
        return metadata and cls._configKey in metadata and metadata[cls._configKey]


