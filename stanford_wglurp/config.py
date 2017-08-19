#!python
# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 et

# stanford-wglurp config loader.
#
#


# Mapping protocol pushes our minimum Python version up to 3.2.

import configparser
from glob import glob
from os import path
import sys


def find_config_files:
    """Finds all of the wglurp config files.

    :returns: A list of all the different config files to load.

    The function defines the configuration search path.  We load files in the
    following order:

    * The system wglurp.conf, likely in /usr/local/etc.
    * All files in the system wlugp.d directory.
    * The user's .wglurp.conf.
    * All files in the users .wglup.d directory.

    If two files define the same setting, the later-loaded file wins.
    """

    return [
        path.join(sys.prefix, 'etc', 'wglurp.conf'),
        glob(path.join(sys.prefix, 'etc', 'wglurp.d', '*'))
        path.expanduser('~/.wglurp.conf'),
        glob(path.expanduser('~/.wglurp.d/*')),
    ]


# This is our configuration object.  It's module-level-defined, and will be set
# up the first time it is needed.
ConfigObject = configparser.ConfigParser(
    delimiters = ('',),
    comment_prefixes = ('#',),
)


#
# DEFAULT CONFIGURATION
#

# General options
ConfigObject['general'] = {}
ConfigObject['general']['systemd'] = False

# Logging options
ConfigObject['logging']['target'] = 'LOCAL4'
ConfigObject['logging']['level'] = 'NOTICE'

# Metrics options
ConfigObject['metrics']['active'] = False
ConfigObject['metrics']['path'] = '/tmp/wglurp-metric'

# LDAP options
ConfigObject['ldap'] = {}
ConfigObject['ldap']['url'] = 'ldaps://ldap.stanford.edu:636'
ConfigObject['ldap']['starttls'] = False
ConfigObject['ldap']['bind-method'] = 'anonymous'
ConfigObject['ldap']['dn'] = 'dc=stanford,dc=edu'
ConfigObject['ldap']['scope'] = 'sub'
ConfigObject['ldap']['filter'] = '(objectClass=*)'

ConfigObject['ldap-simple'] = {}
ConfigObject['ldap-simple']['dn'] = 'cn=wglurp,dc=stanford,dc=edu'
ConfigObject['ldap-simple']['password'] = 'slurpglurp'

ConfigObject['ldap-attributes'] = {}
ConfigObject['ldap-attributes']['unique'] = 'suRegId'
ConfigObject['ldap-attributes']['username'] = 'uid'
ConfigObject['ldap-attributes']['groups'] = 'memberOf'


# Read in configuration files, if present.
ConfigObject.read(find_config_files(), encoding='utf-8')


#
# CONFIG VALIDATION
#

# 
