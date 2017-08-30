#!python
# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 et

# stanford-wglurp LDAP support code.
#
# Refer to the AUTHORS file for copyright statements.
#

# This file contains alot of misc. support code, which is called by the the
# Syncrepl callback code.  Basically, if the code would be duplicated in
# multiple callbacks, and the code in question isn't too long, then it should
# probably be refactored to here!


# We have to load the logger first!
from ..logging import logger


def add_user_to_group(cursor, user_tuple, group_name, encoding):
    """Add a user to a group.

    :param cursor: An active sqlite3 cursor.
    :type cursor: sqlite3.Cursor

    :param tuple user_tuple: A tuple containing unique ID and username.

    :param bytes group_name: The name of the group.

    :param str encoding: The expected encoding for the group name.

    :returns: None

    This method is a support method, used by some of the LDAP callbacks.  Given
    a user tuple (userid and username), and a group name, this adds the user to
    the group.  If the group_name doesn't already exist, it is created.

    .. note::

        This code does database operations, but transaction management is left
        to the caller.
    """
    # First, decode the group_name name to a string.
    try:
        group_name = group_name.decode(encoding)
    except UnicodeError:
        logger.error('Could not decode group_name name "%s"; '
                     'user %s (%s) is a member.  Skipping.'
                     % (group_name,
                        user_tuple[0]. user_tuple[1])
        )
        return None

    # Now, find out if the group_name already exists.
    cursor.execute('''
        SELECT COUNT(*)
          FROM workgroups
         WHERE name = ?
    ''', (group_name,))
    workgroup_name_count = cursor.fetchone()

    # If the list doesn't exist, create it.
    if workgroup_name_count[0] == 0:
        logger.info('Discovered group_name %s' % group_name)
        cursor.execute('''
            INSERT
              INTO workgroups
                   (name)
            VALUES (?)
        ''', (group_name,))

    # Now we can add the user to the workgroup_name!
    logger.debug('%s (%s) is a member of group_name %s'
                 % (user_tuple[0], user_tuple[1], group_name)
    )
    cursor.execute('''
        INSERT
          INTO workgroup_members
               (workgroup_name, member_id)
        VALUES (?, ?)
    ''', (group_name, user_tuple[0]))

    # All done!
    return None


def remove_user_from_group(cursor, user_tuple, group_name, encoding=None):
    """Remove a user from a group.

    :param cursor: An active sqlite3 cursor.
    :type cursor: sqlite3.Cursor

    :param tuple user_tuple: A tuple containing unique ID and username.

    :param group_name: The name of the group.
    :type group_name: bytes or str

    :param str encoding: The expected encoding for the group name, if group_name is bytes.

    :returns: None

    This method is a support method, used by some of the LDAP callbacks.  Given
    a user tuple (userid and username), and a group name, this removes the user
    from the group.  If the group_name is empty after this operation, it is
    deleted.

    .. note::

        This code does database operations, but transaction management is left
        to the caller.
    """
    # First, decode the group_name name to a string.
    try:
        if encoding is not None:
            group_name = group_name.decode(encoding)
    except UnicodeError:
        logger.error('Could not decode group_name name "%s"; '
                     'user %s (%s) is a member.  Skipping.'
                     % (group_name,
                        user_tuple[0]. user_tuple[1])
        )
        return None

    # Log, and then delete.
    logger.info('Removing user %s (%s) from group %s'
                % (user_tuple[0], user_tuple[1], group_name)
    )
    cursor.execute('''
        DELETE
          FROM workgroup_members
         WHERE workgroup_name = ?
           AND member_id = ?
    ''', (group_name, user_tuple[0]))

    # Is the group empty now?  If yes, then delete it.
    cursor.execute('''
        SELECT COUNT(*)
          FROM workgroup_members
         WHERE workgroup_name = ?
    ''', (group_name,))
    membership_count = cursor.fetchone()
    if membership_count[0] == 0:
        logger.info('Group %s is now empty.' % group)
        cursor.execute('''
            DELETE
              FROM workgroups
             WHERE name = ?
        ''', (group_name,))
