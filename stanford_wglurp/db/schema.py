#!python
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 et

# wglurp database access.
#
# Refer to the AUTHORS file for copyright statements.


# Logging must always be loaded first!
from .. import logging

from sqlalchemy import (BigInteger, Binary, Column, Enum, ForeignKey,
                        Index, Integer, SmallInteger, String, Sequence)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

BaseTable = declarative_base()


class Changes(BaseTable):
    """The changes table.

    This table is a queue of group changes.  The queue is written to by the
    Syncrepl client (a single process).  The queue is read by multiple workers.
    """
    __tablename__ = 'changes'

    # The unique ID of the queue entry.  The closer this entry is to the head
    # of a worker's queue, the lower the value.
    id = Column(
        BigInteger,
        Sequence('changes_id_sequence'),
        primary_key = True
    )

    # The ID of the worker whose queue this is in.
    # Worker #0 is special, and is used for FLUSH_CHANGES, FLUSH_ALL, and WAIT.
    worker = Column(
        SmallInteger,
        nullable = False
    )

    # The change to be made.
    # * ADD and REMOVE indicate that one or more people are being added/removed
    # from a group.
    # * SYNC indicates the group membership list is being replaced.
    # * FLUSH_CHANGES, FLUSH_ALL, and WAIT are all to be defined.
    action = Column(
        Enum(
            'ADD',
            'REMOVE',
            'SYNC',
            'FLUSH_CHANGES',
            'FLUSH_ALL',
            'WAIT',
            name = 'changes_action_enum',
        ),
        nullable = False
    )

    # The name of the group being changed.
    # For FLUSH_CHANGES, FLUSH_ALL, and WAIT, this is undefined.
    group = Column(
        String,
    )

    # The contents of the change:
    # * For ADD and REMOVE, this is a JSON list of people to add to/remove from
    # the group.
    # * For SYNC, this is a JSON list of people who are in the group.
    # * For FLUSH_CHANGES, FLUSH_ALL, and WAIT, this is undefined.
    data = Column(
        JSON,
    )


# Create an index on the worker ID and change ID.
Index('changes_worker_id_idx', Changes.worker, Changes.id)


class Destinations(BaseTable):
    __tablename__ = 'destinations'

    # The unique ID of the destination.
    id = Column(
        Integer,
        Sequence('destination_sequence'),
        primary_key = True
    )

    # The status of the destination.  Can be...
    # * ACTIVE: This destination is receiving messages.
    # * DEFERRED: All messages to this destination are queued.
    # * DISABLED: All messages to this destination are silently discarded.
    status = Column(
        Enum(
            'ACTIVE',
            'DEFER',
            'DISABLE',
            name = 'destinations_status_enum',
        ),
        nullable = False,
        index = True
    )

    # The reason why the destination is in DEFER or DISABLE state.
    reason = Column(
        String
    )

    # A 256-bit (32-byte) random value, which—when mixed with the challenge
    # base key—forms the key used for all challenges.
    # NOTE: Not all destinations use challenges, and so in some cases this
    # won't be used.
    challenge_seed = Column(
        Binary(
            length=32
        ),
        nullable = False
    )


class SQSDestinations(BaseTable):
    __tablename__ = 'destinations_sqs'

    # The unique ID of the parent Destination row.
    id = Column(
        Integer,
        ForeignKey('destinations.id', onupdate='CASCADE', ondelete='CASCADE'),
        primary_key = True
    )

    # A reference back to the parent Destination row.
    destination = relationship('Destinations')

    # The SQS URL.
    url = Column(
        String,
        nullable = False
    )
