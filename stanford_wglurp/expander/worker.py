#!python
# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 et

# stanford-wglurp Expander main and metrics-recording code.
#
# Refer to the AUTHORS file for copyright statements.

# We have to load the logger first!
from ..logging import logger

import select
import signal
import sqlalchemy
import time

from ..config import ConfigOption
from ..db import engine
from ..db.schema import Changes


# Make a class to hold our "globals".
class Singleton:
    exiting = False


def run(number):
    logger.info('Worker number %d started!' % number)
    db_session = engine.Session()

    # Set up a stop handler
    def stop_handler(signal_number, frame):
        logger.warning('Worker stop handler has been called.')
        logger.info('The received signal was %d' % signal_number)
        Singleton.exiting = True
    signal.signal(signal.SIGHUP, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    # We will look forever, until told to exit.
    while Singleton.exiting is False:
        # Set up the query to get our next change
        logger.debug('Preparing query for next change')
        next_change_query = db_session.query(Changes).\
            filter(Changes.worker == number).\
            order_by(Changes.id).\
            limit(1)

        # Actually run the query!
        logger.debug('Querying for next change')
        next_change = next_change_query.one_or_none()

        # If we got a change, process it!
        if next_change is not None:
            logger.debug('Found a change')

            # For now, grab some info from the change.
            # TODO: Check for subscriptions, and make update messages.
            logger.info('Change found!  For group %s, action is %s.'
                        % (next_change.group, next_change.action)
            )
            time.sleep(0.25)

            # Mark the change for deletion, since we're processing it.
            logger.debug('Deleting change')
            db_session.delete(next_change)

            # Commit our changes!
            logger.debug('Committing!')
            db_session.commit()

        else:
            logger.debug('No change found.')

            # First, rollback our transaction to make sure nothing is saved.
            # That also releases DB resources.
            logger.debug('Rolling back for safety.')
            db_session.rollback()

            # Get ready to listen for messages on 'expanderX', for 60 seconds.
            # We do this outside of the session, because we don't want a
            # transaction.
            db_connection = engine.AutoCommitSession().connection()

            # Prepare our query, and trigger execution.
            logger.debug('Sleeping on NOTIFY expander%d...' % number)
            listen_query = sqlalchemy.text(
                    'LISTEN expander%d' % number
                )
            listen_result = db_connection.execute(listen_query)

            # Listen for up to 60 seconds for a notification.
            # We'll return early if a notification comes in, and when signalled.
            # TODO: This call doesn't exit early when signalled.
            select.select([db_connection.connection], [], [], 30)
            logger.debug('Sleep complete!')

            # Free up the listen result.
            listen_result.close()

            # We'll loop around again now!

    # At this point, we've hit the end of the while loop, and exiting is True.

    logger.info('Worker number %d exiting!' % number)
