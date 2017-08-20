#!python
# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 et

# stanford-wglurp config loader.
#
#

# Mapping protocol pushes our minimum Python version up to 3.2.

# Make absolutely sure that logging is set up before we do anything.
from stanford_wglurp.logging import logger

# Now we can add our other imports!
import configparser
from glob import glob
from os import path
import sys


def find_config_files():
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

    system_config = path.join(sys.prefix, 'etc', 'wglurp.conf')
    file_load_order = [system_config]

    system_config_d = glob(path.join(sys.prefix, 'etc', 'wglurp.d', '*'))
    if len(system_config_d) > 0:
        file_load_order.extend(system_config_d)

    user_config = path.expanduser('~/.wglurp.conf')
    file_load_order.append(user_config)

    user_config_d = glob(path.expanduser('~/.wglurp.d/*'))
    if len(user_config_d) > 0:
        file_load_order.extend(user_config_d)

    logger.debug('Will load config files in the following order: %s' %
                 file_load_order)
    return file_load_order


# This is our configuration object.  It's module-level-defined, and will be set
# up the first time it is needed.
ConfigObject = configparser.ConfigParser(
    delimiters = ('=',),
    comment_prefixes = ('#',),
)


#
# DEFAULT CONFIGURATION
#

# General options
ConfigObject['general'] = {}
ConfigObject['general']['systemd'] = 'False'

# Logging options
ConfigObject['logging'] = {}
ConfigObject['logging']['target'] = 'LOCAL4'
ConfigObject['logging']['level'] = 'INFO'

# Metrics options
ConfigObject['metrics'] = {}
ConfigObject['metrics']['active'] = 'False'
ConfigObject['metrics']['path'] = ''

# LDAP options
ConfigObject['ldap'] = {}
ConfigObject['ldap']['url'] = 'ldaps://ldap.stanford.edu:636'
ConfigObject['ldap']['starttls'] = 'False'
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
