#!python
# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 et

# stanford-wglurp subscription-related code.
#
# Refer to the AUTHORS file for copyright statements.

# We have to load the logger first!
from .logging import logger

from sqlalchemy.sql.expression import bindparam
from .db import engine
from .db.schema import Destinations, Subscriptions


def subscriptions_for_group(group_name):
    """Get a list of subscriptions for a group name.

    :param str group_name: The name of the group involved.

    :returns: list

    When given a group name, this queries the database to get a list of
    subscriptions that are matched by specific group.

    The returned list of subscriptions will be de-duplicated, but it might not
    be sorted, and it may also be empty.
    """

    db_session = engine.Session()

    logger.debug('Looking up subscriptions for group %s' % group_name)

    # This is one query that's kindof complex.
    # We want all Subscriptions matching either/both of the following...
    # * (type = SINGLE) AND (string = group_name)
    # * (type = PREFIX) AND (group_name LIKE string || '%')
    lookup_query = db_session.query(Subscriptions).filter((
        (Subscriptions.type == 'SINGLE') &
        (Subscriptions.string == group_name)
    ) | (
        (Subscriptions.type == 'PREFIX') &
        bindparam('group_name', group_name).like(
            Subscriptions.string.concat('%')
        )
    ))

    return lookup_query.all()


def destinations_for_group(group_name):
    """Get a list of destinations for a group name.

    :param str group_name: The name of the group involved.

    :returns: list

    When given a group name, this queries the database to get a list of
    destinations that are interested in this specific group; or that are
    interested in a prefix, which this group happens to match.

    The returned list of destinations will be de-duplicated, but it might not
    be sorted, and it may also be empty.
    """

    db_session = engine.Session()

    logger.debug('Looking up destinations for group %s' % group_name)

    # This query is very similar to the one used in `subscriptions_for_group`,
    # above.  The difference is that we are querying Destinations.  Since we
    # took the time to inform SQLAlchemy about the link between Subscriptions
    # and Destinations, we can tell SQLAlchemy to do the join for us!
    lookup_query = db_session.query(Destinations).distinct().\
    join(Subscriptions.destination).filter((
        (Subscriptions.type == 'SINGLE') &
        (Subscriptions.string == group_name)
    ) | (
        (Subscriptions.type == 'PREFIX') &
        bindparam('group_name', group_name).like(
            Subscriptions.string.concat('%')
        )
    ))

    return lookup_query.all()
