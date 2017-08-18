#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 et

# stanford-wglurp installer code.
# 
# Refer to the AUTHORS file for copyright statements.
# 
# This file contains only factual information.
# Therefore, this file is likely not copyrightable.
# As such, this file is in the public domain.
# For locations where public domain does not exist, this file is licensed
# under the Creative Commons CC0 Public Domain Dedication, the text of which
# may be found in the file `LICENSE_others.md` that was included with this
# distribution, and also at
# https://github.com/stanford-rc/wglurp/blob/master/LICENSE_others.md

import re
import setuptools
from setuptools import setup, find_packages
from sys import version_info

# Check versions of Python and setuptools
if (version_info[0] <= 2):
    raise OSError('Python 2 is not supported.  Please try Python 3.')
if (version_info[0] > 3):
    raise OSError('This software has not been validated on Python 4+.')
if int(setuptools.__version__.split('.', 1)[0]) < 18:
    raise OSError('Please use setuptools 18 or later')

# Have code pull the version number from _version.py
def version():
    with open('stanford_wglurp/_version.py') as file:
        regex = r"^__version__ = '(.+)'$"
        matches = re.search(regex, file.read(), re.M)
        if matches:
            return matches.group(1)
        else:
            raise LookupError('Unable to find version number')


# Have code pull the long description from our README
def readme():
    with open('README.rst') as file:
        return file.read()

# Let setuptools handle the rest
setup(
    name = 'stanford-wglurp',
    version = version(),
    description = 'Stanford WorkGroup LDAP Update Reporting Program',
    long_description = readme(),

    keywords = 'ldap syncrepl workgroup stanford',

    author = 'A. Karl Kornel',
    author_email = 'akkornel@stanford.edu',

    url = 'http://github.com/stanford-rc/wglurp',

    packages = find_packages(),
    zip_safe = True,
    include_package_data = True,

    python_requires = '>2,<4,!=3.0.*',
    install_requires = [
        'pyldap',
        'syncrepl-client',
    ],
    provides = ['stanford_wglurp'],
    entry_points = {
        'console_scripts': [
            'wglurp-ldap = stanford_wglurp.ldap:main',
        ],
    },

    license = 'GPL v2 or later',

    classifiers = [
        'Development Status :: 1 - Planning',
        'Environment :: Console',
        'Environment :: No Input/Output (Daemon)',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
        'Operating System :: POSIX',
        'Operating System :: Unix',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: System :: Systems Administration :: Authentication/Directory :: LDAP'
    ]
)
