#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
certs.py
~~~~~~~~

This module returns the preferred default CA certificate bundle.

If you are packaging Requests, e.g., for a Linux distribution or a managed
environment, you can change the definition of where() to return a separately
packaged CA bundle.
"""

import os.path
import sys
import imp


def where():
    """Return the preferred certificate bundle."""

    # Modification for compilation by py2exe:
    if (hasattr(sys, "frozen") or  # new py2exe
            hasattr(sys, "importers")  # old py2exe
            or imp.is_frozen("__main__")):  # tools/freeze
        return os.path.join(os.path.dirname(sys.executable), 'cacert.pem')
    # end py2exe

    # vendored bundle inside Requests
    return os.path.join(os.path.dirname(__file__), 'cacert.pem')

if __name__ == '__main__':
    print(where())
