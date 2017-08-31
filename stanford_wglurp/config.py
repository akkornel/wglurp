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
import codecs
import configparser
from glob import glob
from IPy import IP
import ldapurl
from os import path
from stanford_wglurp.logging import logger
import re
import socket


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

ConfigOption['ldap-encodings'] = {}
ConfigOption['ldap-encodings']['unique'] = 'ascii'
ConfigOption['ldap-encodings']['username'] = 'ascii'
ConfigOption['ldap-encodings']['groups'] = 'ascii'

# Database options
ConfigOption['db'] = {}
ConfigOption['db']['host'] = ''
ConfigOption['db']['port'] = '5432'
ConfigOption['db']['database'] = ''

ConfigOption['db-access'] = {}
ConfigOption['db-access']['username'] = 'postgres'
ConfigOption['db-access']['password'] = ''


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


# Metrics validation!

# active was already checked, since it's a boolean.

# Now check the path.

# If active is true, then path must point to a directory.
if (
    ConfigBoolean['metrics']['active'] is True
    and not path.isdir(ConfigOption['metrics']['path'])
):
    validation_error('metrics', 'path',
        '"%s" does not refer to a valid directory.'
        % ConfigOption['metrics']['path']
    )


# LDAP validation (including ldap-simple and ldap-attributes)!

# First check data.
ldap_dir = path.dirname(ConfigOption['ldap']['data'])
if not path.isdir(ldap_dir):
    validation_error('ldap', 'data',
        '"%s" is not a valid directory.' % ldap_dir
    )
del(ldap_dir)

# Now check url.

# First we validate the LDAP URL by building it.
try:
    parsed_ldap_url = ldapurl.LDAPUrl(ConfigOption['ldap']['url'])
except ValueError:
    validation_error('ldap', 'url',
        '"%s" is missing the URL scheme and/or :// separator'
        % ConfigOption['ldap']['url']
    )
    logger.critical('Warning: Some [ldap] section checks may pass or fail '
            'incorrectly.  Fix this problem and re-run to be sure.')
    parsed_ldap_url = ldapurl.LDAPUrl('ldaps://localhost')

# We've caught basic format and scheme issues.  Now check hostport.
if parsed_ldap_url.hostport == '':
    validation_error('ldap', 'url',
        'LDAP URL must contain at least a valid hostname or IP address.'
    )

(ldap_host, ldap_port) = parsed_ldap_url.hostport.split(':')

# Check host is a valid IP, or a resolvable name.
try:
    IP(ldap_host)
except:
    try:
        socket.gethostbyname(ldap_host)
    except socket.gaierror:
        validation_error('ldap', 'uri',
            '"%s" is either a bad IP, or an unresolveable hostname or FQDN.'
            % ldap_host
        )

# Check port is a number in the right range.
try:
    ldap_port = int(ldap_port)
    if ldap_port < 1 or ldap_port >= 65535:
        validation_error('ldap', 'url',
            'Port number "%s" is out of range.' % ldap_port
        )
except:
    validation_error('ldap', 'url',
        'Port "%s" is not a valid number.' % ldap_port
    )

# Done checking LDAP host & port (finally!)
del(ldap_host)
del(ldap_port)

# Make sure other attributes weren't put into the URL.
if (
    len(parsed_ldap_url.dn) > 0
    or parsed_ldap_url.filterstr is not None
    or parsed_ldap_url.scope is not None
    or parsed_ldap_url.attrs is not None
    or len(parsed_ldap_url.extensions) > 0
):
    validation_error('ldap', 'url',
        'Please do not add extra contents.  Just the scheme and hostport.')

# Now check starttls.

# STARTTLS makes no sense when using ldaps or ldapi.
if (
    ConfigBoolean['ldap']['starttls'] is True
    and parsed_ldap_url.urlscheme == 'ldaps'
):
    validation_error('ldap', 'starttls',
        'Setting this to true makes no sense when using the "ldaps" scheme: '
        'TLS is already being activated.'
    )
if (
    ConfigBoolean['ldap']['starttls'] is True
    and parsed_ldap_url.urlscheme == 'ldapi'
):
    validation_error('ldap', 'starttls',
        'Setting this to true makes no sense when using the "ldapi" scheme: '
        'UNIX domain sockets do not have a proper hostname to validate.'
    )

# Now check bind-method.

# bind-method can be "anonymous", "simple", or "GSSAPI".
if ConfigOption['ldap']['bind-method'] not in [
    'anonymous', 'simple', 'GSSAPI'
]:
    validation_error('ldap', 'bind-method',
        'Method "%s" is invalid.  Valid values are "anonymous", "simple", '
        'and "GSSAPI".' % ConfigOption['ldap']['bind-method']
    )

# Add the bind method into the parsed URL.
if ConfigOption['ldap']['bind-method'] == 'simple':
    parsed_ldap_url.who = ConfigOptions['ldap-simple']['dn']
    parsed_ldap_url.cred = ConfigOptions['ldap-simple']['password']
elif ConfigOption['ldap']['bind-method'] == 'GSSAPI':
    parsed_ldap_url.who = 'GSSAPI'

# There are no real checks to do for dn.

# Add DN to the URL.
parsed_ldap_url.dn = ConfigOption['ldap']['dn']

# Now check scope.

# There are three possible values.
# We check for a valid value and update the parsed URL in one go.
if ConfigOption['ldap']['scope'] == 'one':
    parsed_ldap_url.scope = ldapurl.LDAP_SCOPE_ONELEVEL
elif ConfigOption['ldap']['scope'] == 'base':
    parsed_ldap_url.scope = ldapurl.LDAP_SCOPE_BASE
elif ConfigOption['ldap']['scope'] == 'sub':
    parsed_ldap_url.scope = ldapurl.LDAP_SCOPE_SUBTREE
else:
    validation_error('ldap', 'scope',
        'Scope "%s" is not valid.  Valid values are "one", "sub", and "base".'
        % ConfigOption['ldap']['scope']
    )

# There are no real checks to do for the filer.
# TODO: Maybe there are real checks to do for the filter?

# Add filter to the URL.
parsed_ldap_url.filterstr = ConfigOption['ldap']['filter']

# There are no real checks to do for the ldap-simple items.

# The ldap-simple items were also already added to the parsed URL.

# Now check the ldap-attributes.

# Each attribute must be alphanumeric only.
# Also, add each attribute to the parsed URL.
parsed_ldap_url.attrs = []
attribute_regex = re.compile(r'^[a-z][a-z0-9-]*$', re.I)
for attribute in ['unique', 'username', 'groups']:
    if not attribute_regex.fullmatch(ConfigOption['ldap-attributes'][attribute]):
        validation_error('ldap-attributes', attribute,
            'Value "%s" is not a valid attribute name.'
            % ConfigOption['ldap-attributes'][attribute]
        )
    if attribute not in parsed_ldap_url.attrs:
        parsed_ldap_url.attrs.append(ConfigOption['ldap-attributes'][attribute])

# Now check ldap-encodings.

# There are three keys, one for each attribute.
# For each attribute, make sure it's a known encoding.
for attribute in ['unique', 'username', 'groups']:
    try:
        codecs.lookup(ConfigOption['ldap-encodings'][attribute])
    except LookupError:
        validation_error('ldap-encodings', attribute,
            'Encoding "%s" (for attribute \'%s\') is not recognized.'
            % (ConfigOption['ldap-encodings'][attribute], attribute)
        )

# Now check db.

# host should be either a valid IP, or a valid hostname/FQDN.
db_host=ConfigOption['db']['host']
try:
    IP(db_host)
except:
    try:
        socket.gethostbyname(db_host)
    except socket.gaierror:
        validation_error('db', 'host',
            '"%s" is either a bad IP, or an unresolveable hostname or FQDN.'
            % db_host
        )
del(db_host)

# Check port is a number in the right range.
db_port=ConfigOption['db']['port']
try:
    db_port = int(db_port)
    if db_port < 1 or db_port >= 65535:
        validation_error('db', 'port',
            'Port number "%s" is out of range.' % db_port
        )
except:
    validation_error('db', 'port',
        'Port "%s" is not a valid number.' % db_port
    )
del(db_port)

# There are no real checks to do for the database name.

# There are no real checks to do for the db-access items.

# At the very end, if any part of the validation did not pass, exit.
if ValidationResult.validation_passed is False:
    logger.critical('Configuration files fully parsed.  '
                    'One or more errors detected.  Exiting now.'
    )
    exit(1)

# We're (FINALLY) done!  Clients can access configuration via ConfigOption.
# Booleans can also be accessed via ConfigBoolean.
# The parsed LDAP URL is available at parsed_ldap_url.
