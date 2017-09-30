#!python
# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 et

# stanford-wglurp LDAP callback code.
#
# Refer to the AUTHORS file for copyright statements.
#


# We have to load the logger first!
from ..logging import logger

# Now we can import _most_ of our other stuff.
import ldap
from ldapurl import LDAPUrl
import sqlite3
from syncrepl_client import Syncrepl, SyncreplMode
from syncrepl_client.callbacks import BaseCallback
from sys import exit

from ..config import ConfigBoolean, ConfigOption, parsed_ldap_url
from .support import *

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

    # Placeholders for the attribute names
    unique_attribute = None
    username_attribute = None
    groups_attribute = None

    # Placeholders for attribute encodings
    unique_encoding = None
    username_encoding = None
    groups_encoding = None


    @classmethod
    def bind_complete(cls, ldap, cursor):
        """Called to mark a successful bind to the LDAP server.

        :param ldap.LDAPObject ldap: The LDAP object.

        :return: None - any returned value is ignored.
        """
        logger.info('LDAP bind complete!  We are "%s".'
                    % ldap.whoami_s()
        )

        # Create database tables, if needed.
        logger.debug('Creating workgroup tables in Syncrepl database.')
        cursor.executescript('''
            CREATE TABLE IF NOT EXISTS workgroups (
                name VARCHAR(128) PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS members (
                dn       TEXT         PRIMARY KEY,
                uniqueid VARCHAR(128) UNIQUE,
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

        # Start going through all of the users.
        # Since this is the same as a single add, let's call that method.
        # We cache 
        logger.info('Building view of current workgroups...')
        add_method = cls.record_add_persist
        groups_created = set()
        for user in items:
            groups_modified = add_method(
                user, items[user], cursor, send_message=False
            )
            groups_created |= set(groups_modified)

        logger.info('%d LDAP records processed to populate %d groups.'
                    % (len(items), len(groups_created))
        )

        # The commit will happen as soon as the callback ends!

        # TODO: Send sync messages.

        # Now we can start doing stuff when an event comes in!
        logger.debug('Monkey-patching add, delete, and change records...')
        cls.record_add = cls.record_add_persist
        cls.record_delete = cls.record_delete_persist
        cls.record_change = cls.record_change_persist
        cls.record_rename = cls.record_rename_persist

        logger.info('Refresh-complete processing is complete!')


    @classmethod
    def record_add_persist(cls, dn, attrs, cursor, send_message=True):
        """Called to indicate the addition of a new LDAP record, in the persist
        phase.

        :param str dn: The DN of the added record.

        :param attrs: The record's attributes.
        :type attrs: Dict of lists of bytes

        :return: The list of workgroups modified.
        """
        # We do the following things, in order:
        # * Validate and decode the unique and username attributes.
        # * Add the user to the members table (if not already there).
        # * Decode the member group names.
        # * Add the group names to the groups table (if not already there).
        # * Add entries in the member-group mapping.

        # Get the unique ID and the username.
        # This catches cases where attributes are missing, or multi-valued.
        unique_username = list()
        for (attribute_name, attribute_encoding) in (
            (cls.unique_attribute, cls.unique_encoding),
            (cls.username_attribute, cls.username_encoding)
        ):
            # In one operation, we access the attribute list (can throw
            # KeyError), access the first item (can throw IndexError), and
            # decode it (can throw UnicodeError).  Saves us alot of checks!
            try:
                attribute_value_list = attrs[attribute_name]
                unique_username.append(
                    attribute_value_list[0].decode(attribute_encoding)
                )
            except (KeyError, IndexError):
                logger.warning('Entry "%s" is missing the required '
                               '\'%s\' attribute!' % (dn, attribute_name)
                )
                break
            except UnicodeError as e:
                logger.warning('Error %s decoding the \'%s\' of entry "%s": %s'
                               % (attribute_encoding, attribute_name,
                                  dn, str(e)
                                 )
                )
                break
            # Finally, catch if the attribute is multi-valued.
            if len(attribute_value_list) > 1:
                logger.error('Entry "%s" has a multi-valued '
                             '\'%s\' attribute!' % (dn, attribute_name)
                )
                break

        # If we didn't run through the for() loop twice, skip this user.
        # (The error/warning would have been logged already.
        if unique_username is None:
            return 0

        # Finally our uid and uname are known for this user!
        # Add them to the database.
        logger.debug('DN "%s"\'s unique ID / username is %s / %s'
                     % (dn, unique_username[0], unique_username[1])
        )
        cursor.execute('''
            INSERT
              INTO members
                  (dn, uniqueid, username)
            VALUES (?, ?, ?)
        ''', (dn, unique_username[0], unique_username[1]))

        # Our multivalued attribute is allowed to be missing/empty
        if cls.groups_attribute not in attrs:
            logger.warning('User ID %s (%s) has no groups.'
                           % (unique_username[0], unique_username[1])
            )
            groups = list()
        else:
            groups = attrs[cls.groups_attribute]

        # Go through each of the user's member groups.
        for group in groups:
            # add_user_to_group is from .support
            add_user_to_group(
                cursor,
                unique_username,
                group,
                cls.groups_encoding
            )

            # Also, send a message about the group addition.
            # NOTE: This is disabled if we are being called by refresh_done.
            if send_message is True:
                # TODO: Send "add" message.
                cls.records_count_lock.acquire()
                cls.records_added = cls.records_added + 1
                cls.records_count_lock.release()
                pass

        # Syncrepl will handle committing, once the callback ends!
        return groups


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
            logger.debug('DN %s: %s = %s' % (dn, attr, attrs[attr]))
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

        # Start by getting the unique ID and username for this user.
        cursor.execute('''
            SELECT uniqueid, username
              FROM members
             WHERE dn = ?
        ''', (dn,))
        member_info = cursor.fetchone()
        if (member_info is None):
            logger.error('Trying to delete nonexistant DN "%s"' % dn)
            return

        # Look up all of the member's groups
        cursor.execute('''
            SELECT workgroup_name
              FROM workgroup_members
             WHERE member_id = ?
        ''', (member_info[0],))
        groups_list = cursor.fetchall()

        # For each membership, remove the mapping and send a message.
        for group in [group_tuple[0] for group_tuple in groups_list]:
            remove_user_from_group(cursor, member_info, group)
            # TODO: Send "User removed from group" message.

        # Finally, delete the member entry entirely.
        logger.info('Removing deleted user %s (%s), who had DN "%s"'
                    % (member_info[0], member_info[1], dn)
        )
        cursor.execute('''
            DELETE
              FROM members
             WHERE dn = ?
        ''', (dn,))

        # All done!


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
    def record_rename_persist(cls, old_dn, new_dn, cursor):
        """Called to indicate the change of an LDAP record's DN.

        :param str old_dn: The old DN.

        :param str new_dn: The new DN.

        :return: None - any returned value is ignored.

        Since we track the DN in our database, we need to update it!
        """
        # Start by getting the unique ID and username for this user.
        cursor.execute('''
            SELECT uniqueid
              FROM members
             WHERE dn = ?
        ''', (old_dn,))
        member_info = cursor.fetchone()
        if (member_info is None):
            logger.error('Trying to change nonexistant DN "%s"' % dn)
            return

        # Update the DN in the DB.
        cursor.execute('''
            UPDATE members
               SET dn = ?
             WHERE uniqueid = ?
        ''', (new_dn, member_info[0]))

        # Let Syncrepl handle the transaction.
        # No stats tracking; the change callback will handle that!


    @classmethod
    def record_rename(cls, old_dn, new_dn, cursor):
        """Called to indicate the change of an LDAP record's DN.

        :param str old_dn: The old DN.

        :param str new_dn: The new DN.

        :return: None - any returned value is ignored.

        At the start, in the refresh phase, we don't do anything.
        Later on, we do stuff!
        """
        # No stats tracking; the change callback will handle that!
        pass


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

        # Get the user's _current_ user information.
        # (It might change in a moment, though...)
        cursor.execute('''
            SELECT uniqueid, username
              FROM members
             WHERE dn = ?
        ''', (dn,))
        unique_username = cursor.fetchone()
        if (unique_username is None):
            logger.error('Trying to change nonexistant DN "%s"' % dn)
            return

        # Let's start by looking at old_groups and new_groups.
        # We're going to be doing set stuff, so convert our lists.
        try:
            old_groups = set(old_attrs[cls.groups_attribute])
        except KeyError:
            old_groups = set()
        try:
            new_groups = set(new_attrs[cls.groups_attribute])
        except KeyError:
            logger.warning('User "%s" in not in any groups.' % dn)
            new_groups = set()

        # NOTE!!! We do not do any consitency checking right now, to see if
        # old_groups matches what we have in the DB.

        # Handle adding the user to groups, and removing the user from groups.
        # Set math makes this easy!
        for added_group in new_groups - old_groups:
            # Do the add, and send the message.
            # (Our method handles decoding, and creating the group.)
            # (It also does logging!)
            add_user_to_group(
                cursor,
                unique_username,
                added_group,
                cls.groups_encoding
            )
            # TODO: Send message.

        # Remove groups
        for removed_group in old_groups - new_groups:
            remove_user_from_group(
                cursor,
                unique_username,
                removed_group,
                cls.groups_encoding
            )
            # TODO: Send message.
        
        # Now that groups are in sync, check for a username or unique ID change.
        # TODO: See above.

        # All done!


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
