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
            attribute_value_list = attrs[attribute_name]
            try:
                unique_username.append(
                    attribute_value_list[0].decode(attribute_encoding)
                )
            except (KeyError, IndexError):
                logger.warning('Entry "%s" is missing the required '
                               '\'%s\' attribute!' % (user, attribute_name)
                )
                break
            except UnicodeError as e:
                logger.warning('Error %s decoding the \'%s\' of entry "%s": %s'
                               % (attribute_encoding, attribute_name,
                                  user, str(e)
                                 )
                )
                break
            # Finally, catch if the attribute is multi-valued.
            if len(attribute_value_list) > 1:
                logger.error('Entry "%s" has a multi-valued '
                             '\'%s\' attribute!' % (user, attribute_name)
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
            logger.info('Removing user %s (%s) from group %s'
                        % (member_info[0], member_info[1], group)
            )
            cursor.execute('''
                DELETE
                  FROM workgroup_members
                 WHERE workgroup_name = ?
                   AND member_id = ?
            ''', (group, member_info[0]))

            # Is the group empty now?  If yes, then delete it.
            cursor.execute('''
                SELECT COUNT(*)
                  FROM workgroup_members
                 WHERE workgroup_name = ?
            ''', (group,))
            membership_count = cursor.fetchone()
            if membership_count[0] == 0:
                logger.info('Group %s is now empty.' % group)
                cursor.execute('''
                    DELETE
                      FROM workgroups
                     WHERE name = ?
                ''', (group,))

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

        """
        # Go through each of the user's member groups.
        for group in groups:
            # First, decode the group name to a string.
            try:
                group = group.decode(groups_encoding)
            except UnicodeError:
                logger.error('Could not decode group name "%s"; '
                             'user %s (%s) is a member.  Skipping.'
                             % (group,
                                unique_username[0]. unique_username[1])
                )
                break

            # Now, find out if the group already exists.
            cursor.execute('''
                SELECT COUNT(*)
                  FROM workgroups
                 WHERE name = ?
            ''', (group,))
            workgroup_count = cursor.fetchone()

            # If the list doesn't exist, create it.
            if workgroup_count[0] == 0:
                logger.info('Discovered group %s' % group)
                cursor.execute('''
                    INSERT
                      INTO workgroups
                           (name)
                    VALUES (?)
                ''', (group,))

            # Now we can add the user to the workgroup!
            logger.debug('%s (%s) is a member of group %s'
                         % (unique_username[0], unique_username[1], group)
            )
            cursor.execute('''
                INSERT
                  INTO workgroup_members
                       (workgroup_name, member_id)
                VALUES (?, ?)
            ''', (group, unique_username[0]))

            # Also, send a message about the group addition.
            # NOTE: This is disabled if we are being called by refresh_done.
            if send_message is True:
                # TODO: Send "add" message.
                cls.records_count_lock.acquire()
                cls.records_added = cls.records_added + 1
                cls.records_count_lock.release()
                pass

        # Start by getting the unique ID and username for this user.
        # NOTE: If a DN change happened, the callback already took place.
        cursor.execute('''
            SELECT uniqueid, username
              FROM members
             WHERE dn = ?
        ''', (dn,))
        member_info = cursor.fetchone()
        if (member_info is None):
            logger.error('Trying to change nonexistant DN "%s"' % dn)
            return

        # First, let's check out group membership.

        # Get the user's current group membership.
        cursor.execute('''
            SELECT workgroup_name
              FROM workgroup_members
             WHERE member_id = ?
        ''', (member_info[0],))
        old_groups = cursor.fetchall()

        # Pull the new groups from the attributes
        if groups_attribute not in new_attrs:
            logger.warning('User %s (%s) is not in any groups.'
                           % (member_info[0], member_info[1])
            )
            new_groups = list()
        else:
            new_groups = new_attrs[groups_attribute]

        # Convert the list-of-tuples and list into sets
        old_groups = set([group_tuple[0] for group_tuple in old_groups])
        new_groups = set(new_groups)

        # Now it's now really easy to work out the changes!

        # Add groups
        for added_group in new_groups - old_groups:
            # TODO: Send "User added to group" message.

        # Remove groups
        for removed_group in old_groups - new_groups:
            logger.info('Removing user %s (%s) from group %s'
                        % (member_info[0], member_info[1], removed_group)
            )
            cursor.execute('''
                DELETE
                  FROM workgroup_members
                 WHERE workgroup_name = ?
                   AND member_id = ?
            ''', (removed_group, member_info[0]))

            # Is the group empty now?  If yes, then delete it.
            cursor.execute('''
                SELECT COUNT(*)
                  FROM workgroup_members
                 WHERE workgroup_name = ?
            ''', (removed_group,))
            membership_count = cursor.fetchone()
            if membership_count[0] == 0:
                logger.info('Group %s is now empty.' % removed_group)
                cursor.execute('''
                    DELETE
                      FROM workgroups
                     WHERE name = ?
                ''', (removed_group,))

            # TODO: Send "User removed from group" message.

        # Now that groups are in sync, check for a username or unique ID change.


        # All done!
        """

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
