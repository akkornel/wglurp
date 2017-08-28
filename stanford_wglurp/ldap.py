#!python
# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 et

# stanford-wglurp LDAP client.
#
# Refer to the AUTHORS file for copyright statements.
#


# Daemon threading requires Python 3.3+

# We have to load the logger first!
from stanford_wglurp.logging import logger

# Now we can import _most_ of our other stuff.
import fcntl
import ldap
from ldapurl import LDAPUrl
from os import fsync, path
import signal
import sqlite3
from syncrepl_client import Syncrepl, SyncreplMode
from syncrepl_client.callbacks import BaseCallback
from sys import exit
import time

from .config import ConfigBoolean, ConfigOption, parsed_ldap_url

# We also need threading, which might not be present.
# This is our last import (whew!).
try:
    import threading
except ImportError:
    logger.critical('This Python is not built with thread support.')
    logger.critical('The LDAP client daemon requires threading to operate.')
    exit(1)


#
# LDAP CALLBACK CLASS
#


class LDAPCallback(BaseCallback):
    # Track the number of records that we've seen
    records_count_lock = threading.Lock()
    records_added = 0
    records_modified = 0
    records_deleted = 0

    @classmethod
    def bind_complete(cls, ldap, cursor):
        """Called to mark a successful bind to the LDAP server.

        :param ldap.LDAPObject ldap: The LDAP object.

        :return: None - any returned value is ignored.
        """
        logger.info('LDAP bind complete!  We are "%s". Beginning refresh...'
                    % ldap.whoami_s()
        )

        # Create database tables, if needed.
        logger.debug('Creating workgroup tables in Syncrepl database.')
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS workgroups (
                name VARCHAR(128) PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS members (
                uniqueid VARCHAR(128) PRIMARY KEY,
                username VARCHAR(128) UNIQUE
            );

            CREATE TABLE IF NOT EXISTS workgroup_members (
                workgroup_name UNSIGNED INT REFERENCES workgroups (name),
                member_id VARCHAR(128) REFERENCES members (uniqueid)
            );
        ''')

        logger.info('Beginning refresh...')


    @classmethod
    def refresh_done(cls, items, cursor):
        """Called to mark the end of the refresh phase.

        :param dict items: The items currently in the directory.

        :return: None -- any returned value is ignored.
        """

        logger.info('LDAP server refresh complete!')

        logger.info('Clearing database...')
        cursor.executescript('''
            DELETE FROM workgroup_members;
            DELETE FROM workgroups;
            DELETE FROM members;
        ''')

        logger.info('Building view of current workgroups...')

        # Store the LDAP attribute names locally, to avoid lookups in-loop.
        unique_attribute = ConfigOption['ldap-attributes']['unique']
        username_attribute = ConfigOption['ldap-attributes']['username']
        groups_attribute = ConfigOption['ldap-attributes']['groups']
        logger.info('unique / username / groups attributes are %s / %s / %s'
                     % (unique_attribute, username_attribute, groups_attribute)
        )

        # Start going through all of the users.
        # We do the following things, in order:
        # * Validate and decode the unique and username attributes.
        # * Add the user to the members table (if not already there).
        # * Decode the member group names.
        # * Add the group names to the groups table (if not already there).
        # * Add entries in the member-group mapping.
        for user in items:
            logger.debug('Reading group membership of DN "%s"...' % user)

            # Catch cases where attributes are missing, or multi-valued.
            unique_username = []
            for attribute_name in (unique_attribute, username_attribute):
                # In one operation, we access the attribute list (can throw
                # KeyError), access the first item (can throw IndexError), and
                # decode it (can throw UnicodeError).  Saves us alot of checks!
                attribute_value_list = items[user][attribute_name]
                try:
                    unique_username.append(
                        attribute_value_list[0].decode('ascii')
                    )
                except (KeyError, IndexError):
                    logger.warning('Entry "%s" is missing the required '
                                   '\'%s\' attribute!' % (user, attribute_name)
                    )
                    break
                except UnicodeError as e:
                    logger.warning('Error decoding the \'%s\' of entry "%s": %s'
                                   % (attribute_name, user, str(e))
                    )
                    break
                # Finally, catch if the attribute is multi-valued.
                if len(attribute_value_list) > 1:
                    logger.error('Entry "%s" has a multi-valued '
                                 '\'%s\' attribute!' % (user, attribute_name)
                    )
                    break

            # If we didn't run through the for() loop twice; skip this user.
            if len(unique_username) != 2:
                break

            # Finally our uid and uname are known for this user!
            # Add them to the database.
            logger.debug('DN "%s"\'s unique ID / username is %s / %s'
                         % (user, unique_username[0], unique_username[1])
            )
            cursor.execute('''
                INSERT
                  INTO members
                      (uniqueid, username)
                VALUES (?, ?)
            ''', tuple(unique_username))

            # Our multivalued attribute is allowed to be missing/empty
            if groups_attribute not in items[user]:
                logger.warning('User ID %s (%s) has no groups.'
                               % (unique_username[0], unique_username[1])
                )
                groups = list()
            else:
                groups = items[user][groups_attribute]

            # Go through each of the user's member groups.
            for group in groups:
                try:
                    group = group.decode('ascii')
                except UnicodeError:
                    logger.error('Could not decode group name "%s"; '
                                 'user %s (%s) is a member.  Skipping.'
                                 % (group,
                                    unique_username[0]. unique_username[1])
                    )
                    break

                # If the list doesn't exist, create it.
                if group not in workgroups:
                    logger.info('Discovered group %s' % group)
                    cursor.execute('''
                        INSERT
                          INTO workgroups
                               (name)
                        VALUES (?)
                    ''', (group,))

                # Now we can add the user to the workgroup!
                logger.debug('%s is a member of group %s'
                             % (unique_username[1], group)
                )
                cursor.execute('''
                    INSERT
                      INTO workgroup_members
                           (workgroup_name, member_id)
                    VALUES (?, ?)
                ''', (group, unique_username[0]))

        logger.info('%d LDAP records processed to populate %d groups.'
                    % (len(items), len(workgroups))
        )

        # The commit will happen as soon as the callback ends!

        # TODO: Send sync messages.

        # Now we can start doing stuff when an event comes in!
        logger.debug('Monkey-patching add, delete, and change records...')
        cls.record_add = cls.record_add_persist
        cls.record_delete = cls.record_delete_persist
        cls.record_change = cls.record_change_persist

        logger.info('Refresh-complete processing is complete!')


    @classmethod
    def record_add_persist(cls, dn, attrs, cursor):
        """Called to indicate the addition of a new LDAP record, in the persist
        phase.

        :param str dn: The DN of the added record.

        :param attrs: The record's attributes.
        :type attrs: Dict of lists of bytes

        :return: None - any returned value is ignored.
        """
        logger.debug('New record %s' % dn)
        for attr in attrs:
            logger.debug('--> %s = %s' % (attr, attrs[attr]))
        cls.records_count_lock.acquire()
        cls.records_added += 1
        cls.records_count_lock.release()


    @classmethod
    def record_add(cls, dn, attrs, cursor):
        """Called to indicate the addition of a new LDAP record.

        :param str dn: The DN of the added record.

        :param attrs: The record's attributes.
        :type attrs: Dict of lists of bytes

        :return: None - any returned value is ignored.

        At the start, in the refresh phase, we don't do anything.
        Later on, we do stuff!
        """
        logger.debug('New record %s' % dn)
        for attr in attrs:
            logger.debug('--> %s = %s' % (attr, attrs[attr]))
        cls.records_count_lock.acquire()
        cls.records_added = cls.records_added + 1
        cls.records_count_lock.release()


    @classmethod
    def record_delete_persist(cls, dn, cursor):
        """Called to indicate the deletion of an LDAP record, in the persist
        phase.

        :param str dn: The DN of the deleted record.

        :return: None - any returned value is ignored.
        """
        logger.debug('Deleting record %s' % dn)
        cls.records_count_lock.acquire()
        cls.records_deleted = cls.records_deleted + 1
        cls.records_count_lock.release()


    @classmethod
    def record_delete(cls, dn, cursor):
        """Called to indicate the deletion of an LDAP record.

        :param str dn: The DN of the deleted record.

        :return: None - any returned value is ignored.

        At the start, in the refresh phase, we don't do anything.
        Later on, we do stuff!
        """
        logger.debug('Deleting record %s' % dn)
        cls.records_count_lock.acquire()
        cls.records_deleted = cls.records_deleted + 1
        cls.records_count_lock.release()


    @classmethod
    def record_change_persist(cls, dn, old_attrs, new_attrs, cursor):
        """Called when a record changes in the persist phase.

        :param str dn: The DN of the changed record.

        :param old_attrs: The old attributes.
        :type old_attrs: Dict of lists of bytes

        :param new_attrs: The new attributes.
        :type new_attrs: Dict of lists of bytes
        """
        logger.debug('Record %s modified' % dn)
        cls.records_count_lock.acquire()
        cls.records_modified = cls.records_modified + 1
        cls.records_count_lock.release()



    @classmethod
    def record_change(cls, dn, old_attrs, new_attrs, cursor):
        """Called when a record changes.

        :param str dn: The DN of the changed record.

        :param old_attrs: The old attributes.
        :type old_attrs: Dict of lists of bytes

        :param new_attrs: The new attributes.
        :type new_attrs: Dict of lists of bytes

        At the start, in the refresh phase, we don't do anything.
        Later on, we do stuff!
        """
        logger.debug('Record %s modified' % dn)
        cls.records_count_lock.acquire()
        cls.records_modified = cls.records_modified + 1
        cls.records_count_lock.release()


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

    # Set up our Syncrepl client
    try:
        logger.info('LDAP URL is %s' % parsed_ldap_url.unparse())
        logger.debug('Connecting to LDAP server...')
        client = Syncrepl(
                data_path = ConfigOption['ldap']['data'],
                callback  = LDAPCallback,
                ldap_url  = parsed_ldap_url,
                mode      = SyncreplMode.REFRESH_ONLY,
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

    # If metrics are running, signal them to stop.
    # Before closing, write out zeroes, to prevent fake stats being collected.
    if ConfigBoolean['metrics']['active'] is True:
        logger.debug('Signaling metrics thread to exit.')
        metrics_event.set()
        metrics_thread.join()
        fcntl.lockf(metrics_file, fcntl.LOCK_EX)
        print('records.added=0', 'records.modified=0',
              'records.deleted=0',
                sep="\n", file=metrics_file
        )
        metrics_file.flush()
        fsync(metrics_file.fileno())
        fcntl.lockf(metrics_file, fcntl.LOCK_UN)
        metrics_file.close()

    # Unbind, cleanup, and exit.
    logger.debug('Unbinding & disconnecting from the LDAP server.')
    client.db_reconnect()
    client.unbind()
    exit(0)

    # TODO: Handle join result
    # TODO: Systemd link-up


if __name__ == 'main':
    main()
