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
import datetime
import base64
import hmac
import urllib2
import hashlib
from urllib2 import BaseHandler, HTTPBasicAuthHandler,\
    HTTPPasswordMgrWithDefaultRealm
import re
import urlparse

log = logging.getLogger("cfn.init")

class S3Signer(object):

    def __init__(self, access_key, secret_key):
        self._access_key = access_key
        self._secret_key = secret_key

    def signRequest(self, req):
        if not req.has_header('Date'):
            req.add_header('X-Amz-Date', datetime.datetime.utcnow().replace(microsecond=0).strftime("%a, %d %b %Y %H:%M:%S GMT"))

        stringToSign = req.get_method() + '\n' + \
                       req.get_header('Content-md5', '') + '\n' + \
                       req.get_header('Content-type', '') + '\n' + \
                       req.get_header('Date', '') + '\n' + \
                       self._canonicalize_headers(req) + '\n' + \
                       self._canonicalize_resource(req)

        signed = base64.encodestring(hmac.new(self._secret_key.encode('utf-8'), stringToSign.encode('utf-8'), hashlib.sha1).digest()).strip()

        req.add_header('Authorization', 'AWS %s:%s' % (self._access_key, signed))

        return req

    def _canonicalize_headers(self, req):
        """Does a lazy canonicalization of the headers; it would be difficult to have two headers with the same key given the internals of urllib2.Request"""
        return '\n'.join([hdr.lower() + ':' + val for hdr, val in sorted(req.header_items()) if hdr.lower().startswith('x-amz')])

    def _canonicalize_resource(self, req):
        """Does a lazy canonicalization of the resource; will not detect ?acl or ?torrent"""
        return urlparse.urlparse(req.get_full_url()).path

class S3DefaultHandler(BaseHandler):

    def __init__(self):
        self._bucketToSigner = {}

    def add_creds_for_bucket(self, bucket, access_key, secret_key):
        self._bucketToSigner[bucket] = S3Signer(access_key, secret_key)

    def http_request(self, req):
        bucket = self._extract_bucket(req)
        if bucket and bucket in self._bucketToSigner:
            return self._bucketToSigner[bucket].signRequest(req)
        return req

    def https_request(self, req):
        bucket = self._extract_bucket(req)
        if bucket and bucket in self._bucketToSigner:
            return self._bucketToSigner[bucket].signRequest(req)
        return req

    def _extract_bucket(self, req):
        url = urlparse.urlparse(req.get_full_url())
        match = re.match(r'^([^\.]+\.)?s3(-[\w\d-]+)?.amazonaws.com$', url.netloc)
        if not match:
            # Not an S3 URL, skip
            return None
        elif match.group(1):
            # Subdomain-style S3 URL
            return match.group(1).rstrip('.')
        else:
            # This means that we're using path-style buckets
            # lop off the first / and return everything up to the next /
            return url.path[1:].partition('/')[0]

class S3Handler(BaseHandler):

    def __init__(self, access_key, secret_key):
        self._signer = S3Signer(access_key, secret_key)

    def http_request(self, req):
        return self._signer.signRequest(req)

    def https_request(self, req):
        return self._signer.signRequest(req)


class BasicHandler(BaseHandler):

    def __init__(self, username, password):
        self._username = username
        self._password = password

    def http_request(self, req):
        self._signRequest(req)

    def https_request(self, req):
        self._signRequest(req)

    def _signRequest(self, req):
        req.add_header('Authorization',  'Basic ' + base64.encodestring('%s:%s' % (self._username, self._password)).strip())


class AuthenticationConfig(object):

    def __init__(self, model):

        self._openers = {}

        s3Handler = S3DefaultHandler()
        basicHandler = HTTPBasicAuthHandler(HTTPPasswordMgrWithDefaultRealm())

        for key, config in model.iteritems():
            configType = config.get('type', '')
            if 's3' == configType.lower():
                self._openers[key] = urllib2.build_opener(S3Handler(config.get('accessKeyId'), config.get('secretKey')))
                if 'buckets' in config:
                    buckets = [config['buckets']] if isinstance(config['buckets'], basestring) else config['buckets']
                    for bucket in buckets:
                        s3Handler.add_creds_for_bucket(bucket, config.get('accessKeyId'), config.get('secretKey'))
            elif 'basic' == configType.lower():
                self._openers[key] = urllib2.build_opener(BasicHandler(config.get('username'), config.get('password')))
                if 'uris' in config:
                    basicHandler.add_password(None, config['uris'], config.get('username'), config.get('password'))
            else:
                log.warn("Unrecognized authentication type: %s", configType)

        self._defaultOpener = urllib2.build_opener(s3Handler, basicHandler)

    def get_opener(self, key):
        if not key or not key in self._openers:
            return self._defaultOpener

        return self._openers[key]
