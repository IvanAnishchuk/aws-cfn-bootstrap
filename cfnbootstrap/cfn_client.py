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
CloudFormation client-related classes

Classes:
CloudFormationClient - an HTTP client that makes API calls against CloudFormation endpoints
StackResourceDetail  - detailed information about a StackResource

"""
import datetime
import urlparse
import urllib
import urllib2
import hashlib
import hmac
import base64
import logging
from cfnbootstrap import util
try:
    import simplejson as json
except ImportError:
    import json

log = logging.getLogger("cfn.client")

class CloudFormationClient(object):
    """
    Makes API calls against known CloudFormation endpoints.

    Notes:
    - Public methods of this class have a 1-to-1 equivalence to published CloudFormation APIs.
    - Calls are retried internally when appropriate; callers should not retry.

    """

    _regionToEndpoint = { "us-east-1" : "https://cloudformation.us-east-1.amazonaws.com",
                         "us-west-1" : "https://cloudformation.us-west-1.amazonaws.com",
                         "eu-west-1" : "https://cloudformation.eu-west-1.amazonaws.com",
                         "ap-southeast-1" : "https://cloudformation.ap-southeast-1.amazonaws.com",
                         "ap-northeast-1" : "https://cloudformation.ap-northeast-1.amazonaws.com" }

    _signatureVersion = 2;
    _apiVersion = "2010-05-15"

    def __init__(self, accessKey, secretKey, url=None):
        if not url:
            self.endpoint = CloudFormationClient._regionToEndpoint["us-east-1"]
        else:
            self.endpoint = url
        log.debug("Client initialized with endpoint %s", self.endpoint)
        self.accessKey = accessKey
        self.secretKey = secretKey

    @classmethod
    def endpointForRegion(cls, region):
        if not region in cls._regionToEndpoint:
            raise KeyError("%s is not a supported region" % region)

        return cls._regionToEndpoint[region]

    def describe_stack_resource(self, logicalResourceId, stackName):
        """
        Calls DescribeStackResource and returns a StackResourceDetail object.

        Throws an IOError on failure.
        """
        url = self._construct_url({"Action" : "DescribeStackResource", "LogicalResourceId" : logicalResourceId,
                                                      "StackName": stackName})

        log.debug("Describing resource %s in stack %s", logicalResourceId, stackName)

        return StackResourceDetail(util.urlopen_withretry(urllib2.Request(url, headers={"Accept" : "application/json"}),
                                                          http_error_extractor=self._extractErrorMessage))

    def _extractErrorMessage(self, e):
        try :
            eDoc = json.load(e)['Error']
            code = eDoc['Code']
            terminal = e.code < 500 and code != 'Throttling'
            return (terminal, "%s: %s" % (code, eDoc['Message']))
        except (TypeError, AttributeError, KeyError):
            return (e.code < 500, "Unknown Error: %s %s" % (e.code, e.msg))

    def _construct_url(self, inParams, verb="GET"):
        params = dict(inParams)

        params["SignatureVersion"] = str(CloudFormationClient._signatureVersion)
        params["Version"] = CloudFormationClient._apiVersion
        params["AWSAccessKeyId"] = self.accessKey
        params["Timestamp"] = datetime.datetime.utcnow().replace(microsecond=0).isoformat()
        params["SignatureMethod"] = "HmacSHA256"
        params["ContentType"] = "JSON"
        params["Signature"] = self._sign(verb, params)

        return self.endpoint + "/?" + '&'.join(urllib.quote(k) + '=' + urllib.quote(v) for k, v in params.iteritems())

    def _sign(self, verb, params):
        stringToSign = verb + '\n' + urlparse.urlsplit(self.endpoint)[1] + '\n/\n'

        stringToSign += '&'.join(urllib.quote(k, safe='~') + '=' + urllib.quote(v, safe='~') for k, v in sorted(params.iteritems()))

        return base64.b64encode(hmac.new(self.secretKey, stringToSign, hashlib.sha256).digest())

class StackResourceDetail(object):
    """Detailed information about a stack resource"""

    def __init__(self, xmlData):
        detail = json.load(xmlData)['DescribeStackResourceResponse']['DescribeStackResourceResult']['StackResourceDetail']

        self._description = detail.get('Description')
        self._lastUpdated = datetime.datetime.utcfromtimestamp(detail['LastUpdatedTimestamp'])
        self._logicalResourceId = detail['LogicalResourceId']

        _rawMetadata = detail.get('Metadata')
        self._metadata = json.loads(_rawMetadata) if _rawMetadata else None

        self._physicalResourceId = detail.get('PhysicalResourceId')
        self._resourceType = detail['ResourceType']
        self._resourceStatus = detail['ResourceStatus']
        self._resourceStatusReason = detail.get('ResourceStatusReason')
        self._stackId = detail.get('StackId')
        self._stackName = detail.get('StackName')

    @property
    def logicalResourceId(self):
        """The resource's logical resource ID"""
        return self._logicalResourceId

    @property
    def description(self):
        """The resource's description"""
        return self._description

    @property
    def lastUpdated(self):
        """The timestamp of this resource's last status change as a datetime object"""
        return self._lastUpdated

    @property
    def metadata(self):
        """The resource's metadata as python object (not as a JSON string)"""
        return self._metadata

    @property
    def physicalResourceId(self):
        """The resource's physical resource ID"""
        return self._physicalResourceId

    @property
    def resourceType(self):
        """The resource's type"""
        return self._resourceType

    @property
    def resourceStatus(self):
        """The resource's status"""
        return self._resourceStatus

    @property
    def resourceStatusReason(self):
        """The reason for this resource's status"""
        return self._resourceStatusReason

    @property
    def stackId(self):
        """The ID of the stack this resource belongs to"""
        return self._stackId

    @property
    def stackName(self):
        """The name of the stack this resource belongs to"""
        return self._stackName