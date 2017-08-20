#!python
# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 et

# stanford-wglurp config loader.
#
#

# Mapping protocol pushes our minimum Python version up to 3.2.

# We can only be imported if the logging module is already imported.
import sys
if 'stanford_wglurp.logging' not in sys.modules:
    raise ImportError('stanford_wglurp.logging must be imported first!')

# Now we can import everything!
# (Except for sys, which was imported so we could do our import check.)
import configparser
from glob import glob
from os import path
from stanford_wglurp.logging import logger


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
ConfigOption = configparser.ConfigParser(
    delimiters = ('=',),
    comment_prefixes = ('#',),
)


#
# DEFAULT CONFIGURATION
#


logger.debug('Setting configuration defaults.')

# General options
ConfigOption['general'] = {}
ConfigOption['general']['systemd'] = 'False'

# Logging options
ConfigOption['logging'] = {}
ConfigOption['logging']['target'] = 'LOCAL4'
ConfigOption['logging']['level'] = 'INFO'

# Metrics options
ConfigOption['metrics'] = {}
ConfigOption['metrics']['active'] = 'False'
ConfigOption['metrics']['path'] = ''

# LDAP options
ConfigOption['ldap'] = {}
ConfigOption['ldap']['data'] = '/var/lib/wglurp/ldap-'
ConfigOption['ldap']['url'] = 'ldaps://ldap.stanford.edu:636'
ConfigOption['ldap']['starttls'] = 'False'
ConfigOption['ldap']['bind-method'] = 'anonymous'
ConfigOption['ldap']['dn'] = 'dc=stanford,dc=edu'
ConfigOption['ldap']['scope'] = 'sub'
ConfigOption['ldap']['filter'] = '(objectClass=*)'

ConfigOption['ldap-simple'] = {}
ConfigOption['ldap-simple']['dn'] = 'cn=wglurp,dc=stanford,dc=edu'
ConfigOption['ldap-simple']['password'] = 'slurpglurp'

ConfigOption['ldap-attributes'] = {}
ConfigOption['ldap-attributes']['unique'] = 'suRegId'
ConfigOption['ldap-attributes']['username'] = 'uid'
ConfigOption['ldap-attributes']['groups'] = 'memberOf'


# Read in configuration files, if present.
ConfigObject.read(find_config_files(), encoding='utf-8')


#
# CONFIG VALIDATION
#

# 
