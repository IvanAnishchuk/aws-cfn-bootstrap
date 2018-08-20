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
from resources import documents
import urlparse
import re

S3_PATTERN = r'https://s3([\.-][a-z0-9-]+)\.amazonaws\.com(.*)$'
S3_WITH_BUCKET_PATTERN = r'https://([a-z0-9-\.]+)[\.-]s3([\.-][a-z0-9-]+)\.amazonaws\.com(.*)$'
SQS_PATTERN = r'https://sqs\.([\w-]+)\.amazonaws\.com(.*)$'
SQS_LEGACY_PATTERN = r'https://([\w-]+)\.queue.amazonaws\.com(.*)$'

S3_FORMAT = 's3%s.amazonaws.com%s'
SQS_FORMAT = 'sqs.%s.amazonaws.com%s'
SQS_LEGACY_FORMAT = '%s.queue.amazonaws.com%s'

_endpoint_data = documents.get_endpoint_data()

def get_endpoints_for_service(service):
    """Returns unique service endpoints for special regions."""

    return [Endpoint.from_data(e) for e in _endpoint_data["Services"][service]["Endpoints"]]

def is_service_url(service, unparsed_url):
    return get_endpoint_for_url(service, unparsed_url) is not None

def get_endpoint_for_url(service, unparsed_url):
    for endpoint in get_endpoints_for_service(service):
        if endpoint.matches_url(unparsed_url):
            return endpoint
    if service == "AmazonS3":
        m = re.match(S3_WITH_BUCKET_PATTERN, unparsed_url)
        if m:
            return Endpoint.from_region(S3_FORMAT, m.group(2))
        else:
            m = re.match(S3_PATTERN, unparsed_url)
            if m:
                return Endpoint.from_region(S3_FORMAT, m.group(1))
    elif service == "AmazonSQS":
        m = re.match(SQS_PATTERN, unparsed_url)
        if m:
            return Endpoint.from_region(SQS_FORMAT, m.group(1))
        else:
            m = re.match(SQS_LEGACY_PATTERN, unparsed_url)
            if m:
                return Endpoint.from_region(SQS_LEGACY_FORMAT, m.group(1))

    return None

class Endpoint(object):
    """
    Represents an AWS service endpoint
    """

    @classmethod
    def from_data(cls, endpoint_data):
        is_default = False
        if "Default" in endpoint_data:
            is_default = bool(endpoint_data["Default"])
        return cls(endpoint_data["Region"], endpoint_data["Hostname"], is_default)

    @classmethod
    def from_region(cls, endpoint_format, region):
        if region[:1] not in ['.', '-']:
            region = '.' + region
        return cls(region[1:], endpoint_format % (region, '.cn' if region.startswith('cn') else ''))

    def __init__(self, region, hostname, is_default=False):
        if region is None:
            raise ValueError("region is required")
        if hostname is None:
            raise ValueError("hostname is required")

        self.region = region
        self.hostname = hostname
        self.is_default = is_default

    def matches_url(self, unparsed_url):
        return urlparse.urlparse(unparsed_url).netloc.lower().endswith(self.hostname)

    def get_subdomain_prefix(self, unparsed_url):
        netloc = urlparse.urlparse(unparsed_url).netloc.lower()
        if not netloc.endswith(self.hostname):
            return None
        return netloc.rpartition(self.hostname)[0]
