#!/usr/bin/env python

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

from distutils.core import setup
import sys

rpm_requires = ['python >= 2.5', 'python-daemon']
dependencies = ['daemon']
if sys.version_info[0] == 2 and sys.version_info[1] == 5:
    rpm_requires.append('python-simplejson')
    dependencies.append('simplejson')

name = 'aws-cfn-bootstrap'
version = '1.0'

setup(
    name=name,
    version=version,
    description='An EC2 bootstrapper for CloudFormation',
    long_description="Bootstraps EC2 instances by retrieving and processing the Metadata block of a CloudFormation resource.",
    author='AWS CloudFormation',
    url='http://aws.amazon.com/cloudformation/',
    license='Amazon Software License',
    packages=['cfnbootstrap'],
    package_data={'cfnbootstrap': ['logging.conf']},
    requires=dependencies,
    scripts=['bin/cfn-init', 'bin/cfn-signal', 'bin/cfn-get-metadata', 'bin/cfn-hup'],
    data_files=[('share/doc/%s-%s' % (name, version), ['NOTICE.txt', 'LICENSE.txt']),
                ('init/redhat', ['init/cfn-hup'])],
    options={
             'build_scripts': {
                               'executable': '/usr/bin/env python'
                               },
             'bdist_rpm' : { 'requires' : rpm_requires }
             }
)