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
from ldapurl import LDAPUrl
import signal
from stanford_wglurp.config import ConfigOption, parsed_ldap_url
import stanford_wglurp.db
from syncrepl_client import Syncrepl, SyncreplMode
from syncrepl_client.callbacks import BaseCallback
from sys import exit

# We also need threading, which might not be present.
try:
    import threading
except ImportError:
    logger.alert('This Python is not built with thread support.')
    logger.alert('The LDAP client daemon requires threading to operate.')
    exit(1)


class LDAPCallback(BaseCallback):
    # Track the number of records that we've seen
    records_count_lock = threading.Lock()
    records_added = 0
    records_modified = 0
    records_deleted = 0

    @classmethod
    def bind_complete(cls, ldap):
        """Called to mark a successful bind to the LDAP server.

        :param ldap.LDAPObject ldap: The LDAP object.

        :return: None - any returned value is ignored.
        """
        logger.info('LDAP bind complete!  We are "%s"' % ldap.whoami_s())


    @classmethod
    def refresh_done(cls, items):
        """Called to mark the end of the refresh phase.

        :param dict items: The items currently in the directory.

        :return: None -- any returned value is ignored.
        """

        logger.info('LDAP server refresh complete!')
        logger.info('Building view of current workgroups...')

        # Store the LDAP attribute names locally, to avoid lookups in-loop.
        unique_attribute = ConfigOption['ldap-attributes']['unique']
        username_attribute = ConfigOption['ldap-attributes']['username']
        groups_attribute = ConfigOption['ldap-attributes']['groups']
        logger.info('unique / username / groups attributes are %s / %s / %s'
                     % (unique_attribute, username_attribute, groups_attribute)
        )

        # Begin building our mapping of workgroups to users.
        workgroups = dict()
        for user in items:
            logger.debug('Reading group membership of DN "%s"...' % user)
            uid    = items[user][unique_attribute][0].decode('ascii')
            uname  = items[user][username_attribute][0].decode('ascii')
            groups = items[user][groups_attribute]
            logger.debug('DN "%s" has unique ID / username is %s / %s'
                         % (user, uid, uname)
            )

            # Go through each of the user's member groups.
            for group in groups:
                group = group.decode('ascii')

                # If the list doesn't exist, create it.
                # Then add the user.
                if group not in workgroups:
                    logger.info('Discovered group %s' % group)
                    workgroups[group] = list()
                logger.debug('%s is a member of group %s'
                             % (uname, group)
                )
                workgroups[group].append((uid, uname)) # Yes, a tuple.

        logger.info('%d LDAP records processed to populate %d groups.'
                    % (len(items), len(workgroups))
        )

        # Now we have our workgroups, update the database!
        cls.db.execute('BEGIN TRANSACTION')
        cls.db.execute('DELETE FROM workgroup_members')
        cls.db.execute('DELETE FROM workgroups')
        cls.db.execute('DELETE FROM members')
        for workgroup in workgroups:
            cls.db.execute('''
                INSERT INTO workgroups (name) VALUES (?)
                ''',
                (workgroup,)
            )
            for data in workgroups[workgroup]:
                cls.db.execute('''
                    INSERT OR IGNORE INTO members
                    (uniqueid, username)
                    VALUES (?, ?)
                    ''',
                    data
                )
                cls.db.execute('''
                    INSERT INTO workgroup_members
                    (workgroup_name, member_id)
                    VALUES (?, ?)
                    ''',
                    (workgroup, data[0], )
                )

        # Finish our DB changes
        cls.db.commit()
        cls.db.close()

        # Now we can start doing stuff when an event comes in!
        logger.debug('Monkey-patching add, delete, and change records...')
        cls.record_add = cls.record_add_persist
        cls.record_delete = cls.record_delete_persist
        cls.record_change = cls.record_change_persist

        logger.info('Refresh-complete processing is complete!')


    @classmethod
    def record_add_persist(cls, dn, attrs):
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
    def record_add(cls, dn, attrs):
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
    def record_delete_persist(cls, dn):
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
    def record_delete(cls, dn):
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
    def record_change_persist(cls, dn, old_attrs, new_attrs):
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
    def record_change(cls, dn, old_attrs, new_attrs):
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


def main():


    # Building the LDAP URL (including our attributes list) took place as part
    # of config. validation.

    # Connect to our database
    db = stanford_wglurp.db.connect()
    LDAPCallback.db = db

    # Set up our Syncrepl client
        logger.info('LDAP URL is %s' % parsed_ldap_url.unparse())
        logger.debug('Connecting to LDAP server...')
        client = Syncrepl(
                data_path = ConfigOption['ldap']['data'],
                callback  = LDAPCallback,
                ldap_url  = parsed_ldap_url,
                mode      = SyncreplMode.REFRESH_ONLY,
        )
        logger.debug('Connection complete!')

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

    # Wait for the thread to end
    while client_thread.is_alive() is True:
        client_thread.join(timeout=5.0)
        LDAPCallback.records_count_lock.acquire()
        print('%d / %d / %d records added/modified/deleted'
              % (LDAPCallback.records_added, LDAPCallback.records_modified,
                 LDAPCallback.records_deleted)
        )
        LDAPCallback.records_count_lock.release()


    # Unbind and exit
    logger.debug('Unbinding & disconnecting from the LDAP server.')
    client.unbind()
    exit(0)

    # TODO: Put in stats-gathering code
    # TODO: Handle join result
    # TODO: Systemd link-up


if __name__ == 'main':
    main()
