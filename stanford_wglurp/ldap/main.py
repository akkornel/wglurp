#!python
# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 et

# stanford-wglurp LDAP main and metrics-recording code.
#
# Refer to the AUTHORS file for copyright statements.
#


# Daemon threading requires Python 3.3+

# We have to load the logger first!
from ..logging import logger

# Now we can import _most_ of our other stuff.
import fcntl
import ldap
from ldapurl import LDAPUrl
from os import fsync, path
import signal
from syncrepl_client import Syncrepl, SyncreplMode
from sys import exit
import threading
import time

from ..config import ConfigBoolean, ConfigOption, parsed_ldap_url
from .callback import LDAPCallback


#
# METRICS WRITER
#

def write_metrics(metrics_file, stats_class, finish_event):
    # Loop as long as finish_event has not been triggered
    while not finish_event.is_set():

        # Get lock on file and on stats
        logger.debug('Metrics writer acquiring records lock.')
        stats_class.records_count_lock.acquire()
        logger.debug('Metrics writer acquiring file lock.')
        fcntl.lockf(metrics_file, fcntl.LOCK_EX)

        # Write out stats
        logger.debug('Metrics writer updating stats.')
        metrics_file.seek(0)
        metrics_file.truncate(0)
        print('records.last_updated', round(time.time()),
            sep='=', file=metrics_file
        )
        print('records.added', stats_class.records_added,
            sep='=', file=metrics_file
        )
        print('records.modified', stats_class.records_modified,
            sep='=', file=metrics_file
        )
        print('records.deleted', stats_class.records_deleted,
            sep='=', file=metrics_file
        )

        # Flush file, release locks, and either sleep or end.
        # Note we don't actually release the lock, we downgrade it.
        logger.debug('Metrics writer releasing locks.')
        metrics_file.flush()
        fsync(metrics_file.fileno())
        fcntl.lockf(metrics_file, fcntl.LOCK_SH)
        stats_class.records_count_lock.release()

        # If finish hasn't already triggered, then sleep.
        if not finish_event.is_set():
            logger.debug('Metrics writer sleeping...')
            time.sleep(1)
    logger.debug('Metrics writer exiting!')


#
# MAIN BLOCK
#

def main():

    # Building the LDAP URL (including our attributes list) took place as part
    # of config. validation.

    # If doing metrics, open our metrics file.
    if ConfigBoolean['metrics']['active'] is True:
        logger.debug('Enabling metrics.')
        metrics_file_path = path.join(
            ConfigOption['metrics']['path'],
            'ldap'
        )
        logger.info('Metrics will write to "%s"' % metrics_file_path)
        try:
            metrics_file = open(metrics_file_path,
                mode='w+',
                encoding='utf-8'
            )
        except Exception as e:
            logger.critical('Unable to open metrics file "%s"!'
                            % metrics_file_path
            )
            logger.critical('--> %s' % e)
            exit(1)
        fcntl.lockf(metrics_file, fcntl.LOCK_SH)

    # Store the LDAP attribute names in the callback.
    LDAPCallback.unique_attribute = ConfigOption['ldap-attributes']['unique']
    LDAPCallback.username_attribute = ConfigOption['ldap-attributes']['username']
    LDAPCallback.groups_attribute = ConfigOption['ldap-attributes']['groups']
    LDAPCallback.unique_encoding = ConfigOption['ldap-encodings']['unique']
    LDAPCallback.username_encoding = ConfigOption['ldap-encodings']['username']
    LDAPCallback.groups_encoding = ConfigOption['ldap-encodings']['groups']
    logger.info('unique / username / groups attributes are %s / %s / %s'
                % (LDAPCallback.unique_attribute,
                   LDAPCallback.username_attribute,
                   LDAPCallback.groups_attribute
                  )
    )
    logger.info('unique / username / groups encodings are %s / %s / %s'
                % (LDAPCallback.unique_encoding,
                   LDAPCallback.username_encoding,
                   LDAPCallback.groups_encoding
                  )
    )

    # Set up our Syncrepl client
    try:
        logger.info('LDAP URL is %s' % parsed_ldap_url.unparse())
        logger.debug('Connecting to LDAP server...')
        client = Syncrepl(
                data_path = ConfigOption['ldap']['data'],
                callback  = LDAPCallback,
                ldap_url  = parsed_ldap_url,
                mode      = SyncreplMode.REFRESH_AND_PERSIST,
        )
        logger.debug('Connection complete!')
    except ldap.FILTER_ERROR:
        logger.critical('The LDAP filter string "%s" is invalid.'
                        % parsed_ldap_url.filterstr
        )
        exit(1)
    except ldap.INVALID_CREDENTIALS:
        logger.critical('The LDAP credentials provided were invalid.')
        exit(1)
    except ldap.LOCAL_ERROR as e:
        logger.critical('A local error occurred connecting to the LDAP server.')
        logger.critical('--> %s' % e)
        exit(1)
    except ldap.SERVER_DOWN:
        logger.critical('The server at "%s" refused our connection or is down.'
                        % parsed_ldap_url.hostport
        )
        exit(1)
    except ldap.STRONG_AUTH_REQUIRED:
        logger.critical('TLS is required by the LDAP server.'
                        'Either use ldaps, or set [ldap] \'starttls\' to true.'
        )
        exit(1)
    except ldap.TIMEOUT:
        logger.critical('Connection to "%s" timed out.'
                        % parsed_ldap_url.hostport
        )
        exit(1)


    # Set up a stop handler.
    def stop_handler(signal, frame):
        logger.warning('LDAP client stop handler has been called.')
        logger.info('The received signal was %d' % signal)
        logger.debug('Calling please_stop')
        client.please_stop()

    # Start our Syncrepl thread, and intercept signals.
    logger.debug('Spawning client thread...')
    client_thread = threading.Thread(
        name='LDAP client',
        target=client.run,
        daemon=True
    )
    logger.debug('Now installing signal handler.')
    signal.signal(signal.SIGHUP, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    client_thread.start()
    logger.info('LDAP client thread #%d launched!' % client_thread.ident)

    # Start our metrics thread
    if ConfigBoolean['metrics']['active'] is True:
        metrics_event = threading.Event()
        metrics_thread = threading.Thread(
            name='LDAP metrics',
            target=write_metrics,
            daemon=True,
            args=(metrics_file, LDAPCallback, metrics_event)
        )
        metrics_thread.start()
        logger.info('LDAP metrics thread #%d launched!' % metrics_thread.ident)


    # Wait for the thread to end
    while client_thread.is_alive() is True:
        client_thread.join(timeout=5.0)
    logger.info('LDAP client thread has exited!')

    # If metrics are running, signal them to stop.
    # Before closing, write out zeroes, to prevent fake stats being collected.
    if ConfigBoolean['metrics']['active'] is True:
        logger.debug('Signaling metrics thread to exit.')
        metrics_event.set()
        metrics_thread.join()
        logger.info('Metrics thread has exited!')
        logger.debug('Doing final metrics write...')
        fcntl.lockf(metrics_file, fcntl.LOCK_EX)
        metrics_file.seek(0)
        metrics_file.truncate(0)
        print('records.last_updated', round(time.time()),
            sep='=', file=metrics_file
        )
        print('records.added=0', 'records.modified=0',
              'records.deleted=0',
                sep="\n", file=metrics_file
        )
        logger.debug('Flushing and closing metrics file.')
        metrics_file.flush()
        fsync(metrics_file.fileno())
        fcntl.lockf(metrics_file, fcntl.LOCK_UN)
        metrics_file.close()

    # Unbind, cleanup, and exit.
    logger.info('Unbinding & disconnecting from the LDAP server.')
    client.db_reconnect()
    client.unbind()
    logger.info('Go Tree!')
    exit(0)

    # TODO: Handle join result
    # TODO: Systemd link-up


if __name__ == 'main':
    main()
