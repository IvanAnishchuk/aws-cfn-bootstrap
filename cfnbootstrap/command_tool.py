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
import logging
from cfnbootstrap.construction_errors import ToolError
from cfnbootstrap.util import ProcessHelper, interpret_boolean
import os.path

log = logging.getLogger("cfn.init")

class CommandTool(object):
    """
    Executes arbitrary commands
    """

    def apply(self, action):
        """
        Execute a set of commands, returning a list of commands that were executed.

        Arguments:
        action -- a dict of command to attributes, where attributes has keys of:
            command: the command to run (a string or list)
            cwd: working directory (a string)
            env: a dictionary of environment variables
            test: a commmand to run; if it returns zero, the command will run
            ignoreErrors: if true, ignore errors

        Exceptions:
        ToolError -- on expected failures
        """

        commands_run = []

        if not action:
            log.debug("No commands specified")
            return commands_run

        for name in sorted(action.keys()):
            log.debug("Running command %s", name)

            attributes = action[name]

            if not "command" in attributes:
                log.error("No command specified for %s", name)
                raise ToolError("%s does not specify the 'command' attribute, which is required" % name)

            cwd = os.path.expanduser(attributes["cwd"]) if "cwd" in attributes else None
            env = attributes.get("env", None)

            if "test" in attributes:
                log.debug("Running test for command %s", name)
                test = attributes["test"]
                testResult = ProcessHelper(test, env=env, cwd=cwd).call()
                if testResult.returncode:
                    log.info("Test failed with code %s", testResult.returncode)
                    continue
                else:
                    log.debug("Test for command %s passed", name)
                log.debug("Test command output: %s", testResult.stdout)
            else:
                log.debug("No test for command %s", name)

            commandResult = ProcessHelper(attributes["command"], env=env, cwd=cwd).call()

            if commandResult.returncode:
                log.error("Command %s (%s) failed", name, attributes["command"])
                log.debug("Command %s output: %s", name, commandResult.stdout)
                if interpret_boolean(attributes.get("ignoreErrors")):
                    log.info("ignoreErrors set to true, continuing build")
                else:
                    raise ToolError("Command %s failed" % name)
            else:
                log.info("Command %s succeeded", name)
                log.debug("Command %s output: %s", name, commandResult.stdout)
                commands_run.append(name)

        return commands_run
