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
from cfnbootstrap.construction_errors import ToolError
import os.path
import tarfile
from tarfile import TarError
from cfnbootstrap import util
from zipfile import BadZipfile
import zipfile
import tempfile
import shutil
import re

log = logging.getLogger("cfn.init")

class SourcesTool(object):
    """
    Explodes sources (archives) into locations on disk

    """

    _github_pattern = re.compile(r'^https?://github.com/.*?/(zipball|tarball)/.*$')

    def apply(self, action):
        """
        Extract archives to their corresponding destination directories, returning directories which were updated.
        
        Arguments:
        action -- a dict of directory to archive location, which can be either a path or URL
        
        Exceptions:
        ToolError -- on expected failures
        """
        
        dirs_changed = []

        if not action:
            log.debug("No sources specified")
            return dirs_changed

        for (path, archive) in sorted(action.iteritems(), key=lambda pair: pair[0]):

            if archive.lower().startswith('http') or archive.lower().startswith('ftp'):
                archive_file = self._archive_from_url(archive)
            else:
                if not os.path.isfile(archive):
                    raise ToolError("%s does not exist" % archive)
                archive_file = file(archive, 'rb')

            if TarWrapper.is_compatible(archive_file):
                log.debug("Treating %s as a tarball", archive)
                archive_wrapper = TarWrapper(archive_file)
            elif ZipWrapper.is_compatible(archive_file):
                log.debug("Treating %s as a zip archive", archive)
                archive_wrapper = ZipWrapper(archive_file)
            else:
                raise ToolError("Unsupported source file (not zip or tarball): %s")

            log.debug("Checking to ensure that all archive members fall under path %s" % path)
            self._check_all_members_in_path(path, archive_wrapper)

            if SourcesTool._github_pattern.match(archive.lower()):
                log.debug("Attempting to magically strip GitHub parent directory from archive")
                archive_wrapper=self._perform_github_magic(archive_wrapper);

            log.debug("Expanding %s into %s", archive, path)
            archive_wrapper.extract_all(path)
            dirs_changed.append(path)
        
        return dirs_changed

    def _perform_github_magic(self, archive):
        """
        The tarballs that GitHub autogenerates via their HTTP API put the contents
        of the tree into a top-level directory that has no value or predictability.
        This essentially "strips" that top level directory -- unfortunately, python has no
        equivalent of tar's --strip-components.  So we unarchive it and then rearchive
        a subtree.
        """
        tempdir = tempfile.mkdtemp()
        try:
            archive.extract_all(tempdir)
            tempmembers = os.listdir(tempdir)
            if len(tempmembers) != 1:
                log.debug("GitHub magic is not possible; archive does not contain exactly one directory")
                return archive
            else:
                temparchive = tempfile.TemporaryFile()
                tf = tarfile.TarFile(fileobj=temparchive, mode='w')
                parent = os.path.join(tempdir, tempmembers[0])
                log.debug("Creating temporary tar from %s", parent)
                for member in os.listdir(parent):
                    tf.add(os.path.join(parent, member), arcname=member)
                tf.close()
                temparchive.seek(0, 0)
                return TarWrapper(temparchive)
        finally:
            shutil.rmtree(tempdir, True)

    def _check_all_members_in_path(self, path, archive):
        """
        This does a best-effort test to make sure absolute paths
        or ../../../../ nonsense in archives makes files "escape"
        their destination
        """

        normalized_parent = os.path.normcase(os.path.abspath(path))
        for member in archive.files():
            if os.path.isabs(member):
                prefix = os.path.commonprefix([os.path.normcase(os.path.normpath(member)), normalized_parent])
            else:
                prefix = os.path.commonprefix([os.path.normcase(os.path.normpath(os.path.join(normalized_parent, member))), normalized_parent])

            if prefix != normalized_parent:
                raise ToolError("%s is not a sub-path of %s" % (member, path))

    def _archive_from_url(self, archive):
        try:
            urlstream = util.urlopen_withretry(archive)
        except IOError, e:
            raise ToolError(e.strerror)

        tf = tempfile.TemporaryFile()
        shutil.copyfileobj(urlstream, tf)
        tf.seek(0, 0)
        return tf

class ZipWrapper(object):

    def __init__(self, f):
        self.file = zipfile.ZipFile(f, mode='r')

    @classmethod
    def is_compatible(cls, f):
        try:
            z = zipfile.ZipFile(f, mode='r')
            z.close()
            f.seek(0, 0)
            return True
        except BadZipfile:
            return False

    def files(self):
        return (info.filename for info in self.file.infolist())

    def extract_all(self, dest):
        self.file.extractall(dest)

class TarWrapper(object):

    def __init__(self, f):
        self.file = tarfile.open(fileobj = f, mode='r:*')

    @classmethod
    def is_compatible(cls, f):
        try:
            t = tarfile.open(fileobj = f, mode='r:*')
            t.close()
            f.seek(0, 0)
            return True
        except TarError:
            return False

    def files(self):
        return self.file.getnames()

    def extract_all(self, dest):
        self.file.extractall(dest)