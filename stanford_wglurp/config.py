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
import re


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
logger.debug('Reading configuration files...')
try:
    ConfigOption.read(find_config_files(), encoding='utf-8')
except configparser.DuplicateSectionError as e:
    logger.critical('Configuration error detected!')
    logger.critical('In file "%s", line #%d' % (e.source, e.lineno))
    logger.critical('--> Section [%s] was already defined in this file.'
                    % e.section)
    logger.critical('(Other errors may exist, but we have to stop here.)')
    logger.critical('Configuration problems detected.  Exiting now.')
    exit(1)
except configparser.DuplicateOptionError as e:
    logger.critical('Configuration error detected!')
    logger.critical('In file "%s", line #%d, section [%s]'
                    % (e.source, e.lineno, e.section))
    logger.critical('--> Option \'%s\' was already defined in this file.'
                    % e.option)
    logger.critical('(Other errors may exist, but we have to stop here.)')
    logger.critical('Configuration problems detected.  Exiting now.')
    exit(1)
except configparser.ParsingError as e:
    logger.critical('Configuration error detected!')
    logger.critical('--> Unable to parse file "%s"' % e.source)
    logger.critical('(Other errors may exist, but we have to stop here.)')
    logger.critical('Configuration problems detected.  Exiting now.')
    exit(1)


#
# CONFIG VALIDATION
#

logger.debug('Valdating read configuration...')

# We need to define a class here, because we want to set validation_passed
# inside of validation_error.  But, validation_passed is a boolean, which means
# setting it inside of a function localizes it!  So, to keep the value global,
# we create a singleton class, which exists outside of validation_error.
class ValidationResult:
    validation_passed = True

def validation_error(section, option, problem):
    logger.critical('Configuration error detected!')
    logger.critical('Section: [%s], Option: %s' % (section, option))
    logger.critical('--> %s' % problem)
    ValidationResult.validation_passed = False


# First, let's check all our boolean values

ConfigBoolean = {}
boolean_validation_successful = True

for section, option in [
    ('general', 'systemd'),
    ('metrics', 'active'),
    ('ldap', 'starttls'),
]:
    try:
        # Parse the boolean value, then store it into a dict for later access.
        boolean_value = ConfigOption[section].getboolean(option)

        # We're doing two-level dicts, so make sure the 2nd level is ready.
        if section not in ConfigBoolean:
            ConfigBoolean[section] = {}
        ConfigBoolean[section][option] = boolean_value
    except ValueError:
        validation_error(section, option,
            'This setting must be a boolean (true/false/yes/no/1/0) value.'
        )
        boolean_validation_successful = False

# If there were any boolean problems, stop now.
if boolean_validation_successful is False:
    logger.critical('(Other errors may exist, but we have to stop here.)')
    logger.critical('Configuration problems detected.  Exiting now.')
    exit(1)
del(boolean_validation_successful)

# General validation

# Systemd needs the systemd module
if ConfigBoolean['general']['systemd'] is True:
    try:
        import systemd
    except ImportError:
        validation_error('general', 'systemd',
            'The systemd module is required when this setting is True.'
        )


# Logging validation

# Target checks first

# NT requires the pywin32 module
if ConfigOption['logging']['target'] is 'NT':
    try:
        import pywin32
    except ModuleNotFoundError:
        validation_error('logging', 'target',
            'For "NT" logging, the pywin32 module must be installed.'
        )

# JOURNALD needs a couple of checks.
if ConfigOption['logging']['target'] == "JOURNALD":
    # We need [general] systemd to be true.
    if ConfigBoolean['general']['systemd'] is False:
        validation_error('logging', 'target',
            'For "JOURNALD" logging, the [general] \'systemd\' setting '
            'must be True.'
        )

    # Make sure the systemd.journal module is available.
    try:
        import systemd.journal
    except ModuleNotFoundError:
        validation_error('logging', 'target',
            'For "JOURNALD" logging, the systemd.journal module is needed.'
        )

# Other non-LOCAL values need a path to a valid directory.
if (
    ConfigOption['logging']['target'] not in ['NT', 'JOURNALD']
    and not re.fullmatch('^LOCAL[0-7]$', ConfigOption['logging']['target'])
):
    target_dir = path.dirname(ConfigOption['logging']['target'])
    if not path.isdir(target_dir):
        validation_error('logging', 'target',
            '"%s" is not a valid directory.' % target_dir
        )

# Now check the level.

# This is simple; there are only a few valid values.
if ConfigOption['logging']['level'] not in [
    'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
]:
    validation_error('logging', 'level',
        '"%s" is not a valid level.  Valid values are "DEBUG", "INFO", '
        '"WARNING", "ERROR", and "CRITICAL".'
        % ConfigOption['logging']['level']
    )
# At the very end, if any part of the validation did not pass, exit.
if ValidationResult.validation_passed is False:
    logger.critical('Configuration files fully parsed.  '
                    'One or more errors detected.  Exiting now.'
    )
    exit(1)

# We're (FINALLY) done!  Clients can access configuration via ConfigOption.
# Booleans can also be accessed via ConfigBoolean.
# The parsed LDAP URL is available at parsed_ldap_url.
