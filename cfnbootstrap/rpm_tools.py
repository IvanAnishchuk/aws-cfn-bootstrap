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

from cfnbootstrap.util import ProcessHelper
import logging
from cfnbootstrap.construction_errors import ToolError
import subprocess

log = logging.getLogger("cfn.init")

class YumTool(object):
    """
    Installs packages via Yum

    """

    def apply(self, action):
        """
        Install a set of packages via yum, returning the packages actually installed or updated.

        Arguments:
        action -- a dict of package name to version; version can be empty, a single string or a list of strings

        Exceptions:
        ToolError -- on expected failures (such as a non-zero exit code)
        """

        pkgs_changed = []

        if not action.keys():
            log.debug("No packages specified for yum")
            return pkgs_changed

        cache_result = ProcessHelper(['yum', '-y', 'makecache']).call()

        if cache_result.returncode:
            log.error("Yum makecache failed. Output: %s", cache_result.stdout)
            raise ToolError("Could not create yum cache", cache_result.returncode)

        pkg_specs = []

        for pkg_name in action:
            if action[pkg_name]:
                if isinstance(action[pkg_name], basestring):
                    pkg_keys = ['%s-%s' % (pkg_name, action[pkg_name])]
                else:
                    pkg_keys = ['%s-%s' % (pkg_name, ver) if ver else pkg_name for ver in action[pkg_name]]
            else:
                pkg_keys = [pkg_name]

            pkgs_filtered = [pkg_key for pkg_key in pkg_keys if self._pkg_filter(pkg_key)]
            if pkgs_filtered:
                pkg_specs.extend(pkgs_filtered)
                pkgs_changed.append(pkg_name)

        if not pkg_specs:
            log.debug("All yum packages were already installed")
            return []

        log.debug("Installing %s via yum", pkg_specs)

        result = ProcessHelper(['yum', '-y', 'install'] + pkg_specs).call()

        if result.returncode:
            log.error("Yum failed. Output: %s", result.stdout)
            raise ToolError("Could not successfully install yum packages", result.returncode)

        log.info("Yum installed %s", pkgs_changed)

        return pkgs_changed

    def _pkg_filter(self, pkg):
        if self._pkg_installed(pkg):
            log.debug("%s will not be installed as it is already present", pkg)
            return False
        elif not self._pkg_available(pkg):
            log.error("%s is not available to be installed", pkg)
            raise ToolError("Yum does not have %s available for installation" % pkg)
        else:
            return True

    def _pkg_installed(self, pkg):
        result = ProcessHelper(['yum', '-C', '-y', 'list', 'installed', pkg]).call()

        return result.returncode == 0

    def _pkg_available(self, pkg):
        result = ProcessHelper(['yum', '-C', '-y', 'list', 'available', pkg]).call()

        return result.returncode == 0

class RpmTool(object):

    def apply(self, action):
        """
        Install a set of packages via RPM, returning the packages actually installed or updated.

        Arguments:
        action -- a dict of package name to version; version can be empty, a single string or a list of strings

        Exceptions:
        ToolError -- on expected failures (such as a non-zero exit code)
        """

        pkgs_changed = []

        if not action.keys():
            log.debug("No packages installed for RPM")
            return pkgs_changed

        pkgs = []

        for pkg_name, loc in action.iteritems():
            pkgs_to_process = ([loc] if isinstance(loc, basestring) else loc)
            pkgs_filtered = [pkg_key for pkg_key in pkgs_to_process if self._package_filter(pkg_key)]
            if pkgs_filtered:
                pkgs.extend(pkgs_filtered)
                pkgs_changed.append(pkg_name)


        if not pkgs:
            log.info("All RPMs were already installed")
            return []

        log.debug("Installing %s via RPM", pkgs)

        result = ProcessHelper(['rpm', '-U', '--quiet', '--nosignature', '--replacepkgs'] + pkgs).call()

        if result.returncode:
            log.error("RPM failed. Output: %s", result.stdout)
            raise ToolError("Could not successfully install rpm packages", result.returncode)
        else:
            log.debug("RPM output: %s", result.stdout)

        return pkgs_changed

    def _package_filter(self, pkg):
        if not pkg:
            log.warn("RPM specified with no location")
            return False

        if self._is_installed(pkg):
            log.debug("Skipping RPM at %s as it is already installed", pkg)
            return False

        return True

    def _is_installed(self, pkg):
        # Use rpm -qp to extract the name, version, release and arch in rpm-standard format from the RPM
        # This works even for remote RPMs
        query_result = ProcessHelper(['rpm', '-qp', '--queryformat', '%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}', '--nosignature', pkg], stderr=subprocess.PIPE).call()

        if query_result.returncode:
            # If there's an error, assume we have to install it (a failure there will be terminal)
            log.error("Could not determine package contained by rpm at %s", pkg)
            log.debug("RPM output: %s", query_result.stderr)
            return True

        # The output from the command is just name-version-release.arch
        query_output = query_result.stdout.strip()

        # rpm -q will try to find the specific RPM in the local system
        # --quiet will reduce this command to just an exit code
        test_result = ProcessHelper(['rpm', '-q', '--quiet', query_output]).call()

        # if rpm -q returns 0, that means the package exists
        return test_result.returncode == 0