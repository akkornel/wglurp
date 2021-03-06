#!python
# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 et

# stanford-wglurp logger.


# WARNING: Do not import config until after the logger is ready to go!
import logging
import logging.handlers
from os import path
from stanford_wglurp._version import __version__
import sys
from sys import argv, platform, stdout
import traceback


# Begin to configure logging as soon as we are loaded
logger = logging.Logger(argv[0])

# Configure an initial handler, so we don't lose stuff.
logger.debug('Adding program-startup handler')
startup_handler = logging.StreamHandler()
logger.addHandler(startup_handler)
logger.debug('Added program-startup handler.  '
             'Log to stderr until early-start is complete.'
)

# Since we're configuring the handler, disable propagation
logger.debug('Disabling log propagation.')
logger.propagate = False

# Set up our default log entry format.
formatter_default = logging.Formatter(
        fmt='[%(process)d] [%(filename)s:%(lineno)d (%(funcName)s)] %(levelname)s: %(message)s'
)
startup_handler.setFormatter(formatter_default)

# Log our first message!
logger.info('stanford_wglurp (%s) version %s early startup...',
             path.basename(argv[0]),
             __version__
)


# Define a function to handle uncaught exceptions
def handle_exception(exception_type, exception_value, exception_traceback):
    # Before we handle this exception, we temporarily restore the original
    # exception handler.  That way, if we throw another exception, we don't get
    # stuck forever!
    sys.excepthook = sys.__excepthook__

    # Get the exception and traceback as an array of strings.
    exception_formatted = traceback.format_exception_only(
        exception_type, exception_value
    )
    exception_formatted.append('TRACEBACK (failing call last):')
    exception_formatted.extend(traceback.format_list(
        traceback.extract_tb(exception_traceback)
    ))

    # Begin outputting the exception
    logger.critical('UNCAUGHT EXCEPTION!')

    # Each array entry is one or more lines.  Strip trailing whitespace, and
    # then split individual lines for outputting.
    for line in exception_formatted:
        for real_line in line.rstrip().split("\n"):
            logger.critical(real_line)

    # Before we end, restore our exception handler.
    sys.excepthook = handle_exception

# Put our uncaught-exception handler in place
logger.debug('Installing custom last-resort exception-handler hook.')
sys.excepthook = handle_exception


# Now we can import our configuration!
# WARNING: This can create a dependency loop!
# WARNING: To resolve this loop, we must be loaded _first_.
# We bring in validation_* because we have to validate the logging configs.
from stanford_wglurp.config import ConfigOption, validation_error


# Now we can set up logging, destination first.

# Define a function to get the syslog log socket (which depends on the OS).
def syslog_dest():
    if platform.startswith('linux'):
        # Linux uses one socket path.
        logger.debug('Will use syslog socket at /dev/log')
        return '/dev/log'
    elif platform.startswith('darwin'):
        # macOS uses a different socket path.
        logger.debug('Will use syslog socket at /var/run/syslog')
        return '/var/run/syslog'
    else:
        # Fall back to syslog over UDP.
        logger.debug('Will log to localhost syslog port')
        return ('localhost', 514)

# Get and configure our log destination
destination = ConfigOption['logging']['target']
logger.debug('Configured log target is %s', destination)

# Next, configure the destination from configuration.
if destination == "LOCAL1":
    # All the syslog destinations to essentially the same thing.
    # * Create a syslog handler, going to the right destination for the OS.
    # * Set the handler's formatter to the default.
    # * Add the handler to the logger.
    # The only thing different between destinations is the facility used.
    logger.info('Will log to syslog, facility LOCAL1.')
    syslog_handler = logging.handlers.SysLogHandler(
        address=syslog_dest(),
        facility=LOG_LOCAL1
    )
    syslog_handler.setFormatter(formatter_default)
    logger.addHandler(syslog_handler)
elif destination == "LOCAL2":
    logger.info('Will log to syslog, facility LOCAL2.')
    syslog_handler = logging.handlers.SysLogHandler(
        address=syslog_dest(),
        facility=LOG_LOCAL2
    )
    syslog_handler.setFormatter(formatter_default)
    logger.addHandler(syslog_handler)
elif destination == "LOCAL3":
    logger.info('Will log to syslog, facility LOCAL3.')
    syslog_handler = logging.handlers.SysLogHandler(
        address=syslog_dest(),
        facility=LOG_LOCAL3
    )
    syslog_handler.setFormatter(formatter_default)
    logger.addHandler(syslog_handler)
elif destination == "LOCAL4":
    logger.info('Will log to syslog, facility LOCAL4.')
    syslog_handler = logging.handlers.SysLogHandler(
        address=syslog_dest(),
        facility='local4'
    )
    syslog_handler.setFormatter(formatter_default)
    logger.addHandler(syslog_handler)
elif destination == "LOCAL5":
    logger.info('Will log to syslog, facility LOCAL5.')
    syslog_handler = logging.handlers.SysLogHandler(
        address=syslog_dest(),
        facility=LOG_LOCAL5
    )
    syslog_handler.setFormatter(formatter_default)
    logger.addHandler(syslog_handler)
elif destination == "LOCAL6":
    logger.info('Will log to syslog, facility LOCAL6.')
    syslog_handler = logging.handlers.SysLogHandler(
        address=syslog_dest(),
        facility=LOG_LOCAL6
    )
    syslog_handler.setFormatter(formatter_default)
    logger.addHandler(syslog_handler)
elif destination == "LOCAL7":
    logger.info('Will log to syslog, facility LOCAL7.')
    syslog_handler = logging.handlers.SysLogHandler(
        address=syslog_dest(),
        facility=LOG_LOCAL7
    )
    syslog_handler.setFormatter(formatter_default)
    logger.addHandler(syslog_handler)

# For NT, we leverage native NT event logging
elif destination == "NT":
    logger.info('Will log to the NT event log.')
    import pywin32

    # We use the same format as the syslog handler. 
    nt_handler = logging.handlers.NTEventLogHandler(
        appname=argv[0]
    )
    nt_handler.setFormatter(formatter_default)
    logger.addHandler(nt_handler)

# For journald, we're a bit different, so we can leverage journald's stuff.
elif destination == "JOURNALD":
    logger.info('Will log to journald.')
    import systemd.journal

    # Our format is much simpler, because journald keeps track of all of the
    # other fields we normally have.
    formatter_journald = logging.Formatter(
        fmt='%(message)s'
    )

    # Now we can configure and add the handler.
    journald_handler = systemd.journal.JournalHandler()
    journald_handler.setFormatter(formatter_journald)
    logger.addHandler(journald_handler)

# Other strings are treated as filenames.
else:
    # We'll use the watched-filer handler, to cope with log-rotation.
    logger.info('Will log to file at path %s.', destination)
    file_handler = logging.handlers.WatchedFileHandler(
        destination,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter_default)
    logger.addHandler(file_handler)


# If running in the foreground, also log to stdout
if ('-f' in argv) or ('--foreground' in argv):
    logger.info('Running in foreground.  Logs will now go to stdout.  '
                '(The next entry will log to both stdout and stderr.)')
    stdout_handler = logging.StreamHandler(
        stream=stdout
    )
    stdout_handler.setFormatter(formatter_default)
    logger.addHandler(stdout_handler)

# Even if not running in the foreground, stop stderr logging now.
logger.info('Program-startup logging to stderr will now end.')
logger.removeHandler(startup_handler)
del startup_handler


# Re-log the banner, so it goes to the new streams.
logger.info('Welcome to stanford_wglurp (%s) version %s!',
             path.basename(argv[0]),
             __version__
)


# Set our log-level threshold.
logger.info('Logging threshold changed to %s', ConfigOption['logging']['level'])
logger.setLevel(ConfigOption['logging']['level'])


# That's it!  Clients can now log stuff through 'logger'.
