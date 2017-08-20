#!python
# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 et

# stanford-wglurp LDAP client.
#
# Refer to the AUTHORS file for copyright statements.
#


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
    raise OSError('This Python is not built with thread support.  Sorry!')




class LDAPCallback(BaseCallback):
    records_processed_lock = threading.Lock()
    records_processed = 0

    @classmethod
    def bind_complete(cls, ldap):
        """Called to mark a successful bind to the LDAP server.

        :param ldap.LDAPObject ldap: The LDAP object.

        :return: None - any returned value is ignored.
        """
        pass


    @classmethod
    def refresh_done(cls, items):
        """Called to mark the end of the refresh phase.

        :param dict items: The items currently in the directory.

        :return: None -- any returned value is ignored.
        """

        # Reset our counter, to track the number of users processed
        cls.records_processed_lock.acquire()
        cls.records_processed = 0
        cls.records_processed_lock.release()
        # Store the LDAP attribute names locally, to avoid lookups in-loop.
        unique_attribute = ConfigOption['ldap-attributes']['unique']
        username_attribute = ConfigOption['ldap-attributes']['username']
        groups_attribute = ConfigOption['ldap-attributes']['groups']

        # Begin building our mapping of workgroups to users.
        workgroups = dict()
        for user in items:
            cls.records_processed_lock.acquire()
            cls.records_processed = cls.records_processed + 1
            cls.records_processed_lock.release()

            uid    = items[user][unique_attribute][0]
            uname  = items[user][username_attribute][0]
            groups = items[user][groups_attribute]

            # Go through each of the user's member groups.
            for group in groups:
                group = group.decode('ascii')

                # If the list doesn't exist, create it.
                # Then add the user.
                if group not in workgroups:
                    workgroups[group] = list()
                workgroups[group].append(
                    (uid.decode('ascii'),
                    uname.decode('ascii'),)
                )

        # Reset our counter once again
        cls.records_processed_lock.acquire()
        cls.records_processed = 0
        cls.records_processed_lock.release()

        # Now we have our workgroups, update the database!
        cls.db.execute('BEGIN TRANSACTION')
        cls.db.execute('DELETE FROM workgroup_members')
        cls.db.execute('DELETE FROM workgroups')
        cls.db.execute('DELETE FROM members')
        for workgroup in workgroups:
            cls.records_processed_lock.acquire()
            cls.records_processed = cls.records_processed + 1
            cls.records_processed_lock.release()

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
        cls.record_add = cls.record_add_persist
        cls.record_delete = cls.record_delete_persist
        cls.record_change = cls.record_change_persist


    @classmethod
    def record_add_persist(cls, dn, attrs):
        """Called to indicate the addition of a new LDAP record, in the persist
        phase.

        :param str dn: The DN of the added record.

        :param attrs: The record's attributes.
        :type attrs: Dict of lists of bytes

        :return: None - any returned value is ignored.
        """
        pass


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
        cls.records_processed_lock.acquire()
        cls.records_processed = cls.records_processed + 1
        cls.records_processed_lock.release()


    @classmethod
    def record_delete_persist(cls, dn):
        """Called to indicate the deletion of an LDAP record, in the persist
        phase.

        :param str dn: The DN of the deleted record.

        :return: None - any returned value is ignored.
        """
        pass


    @classmethod
    def record_delete(cls, dn):
        """Called to indicate the deletion of an LDAP record.

        :param str dn: The DN of the deleted record.

        :return: None - any returned value is ignored.

        At the start, in the refresh phase, we don't do anything.
        Later on, we do stuff!
        """
        pass


    @classmethod
    def record_change_persist(cls, dn, old_attrs, new_attrs):
        """Called when a record changes in the persist phase.

        :param str dn: The DN of the changed record.

        :param old_attrs: The old attributes.
        :type old_attrs: Dict of lists of bytes

        :param new_attrs: The new attributes.
        :type new_attrs: Dict of lists of bytes
        """
        pass


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
        pass


def main():


    # Building the LDAP URL (including our attributes list) took place as part
    # of config. validation.

    # Connect to our database
    db = stanford_wglurp.db.connect()
    LDAPCallback.db = db

    # Set up our Syncrepl client
        client = Syncrepl(
                data_path = ConfigOption['ldap']['data'],
                callback  = LDAPCallback,
                ldap_url  = parsed_ldap_url,
                mode      = SyncreplMode.REFRESH_ONLY,
        )

    # Set up a stop handler.
    def stop_handler(signal, frame):
        client.please_stop()

    # Start our Syncrepl thread, and intercept signals
    client_thread = threading.Thread(target = client.run)
    signal.signal(signal.SIGHUP, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)
    client_thread.start()

    # Wait for the thread to end
    while client_thread.is_alive() is True:
        client_thread.join(timeout=5.0)
        LDAPCallback.records_processed_lock.acquire()
        print('Records processed:', LDAPCallback.records_processed)
        LDAPCallback.records_processed_lock.release()


    # Unbind and exit
    client.unbind()
    exit(0)

    # TODO: Put in stats-gathering code
    # TODO: Handle join result
    # TODO: Systemd link-up


if __name__ == 'main':
    main()
