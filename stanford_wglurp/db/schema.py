#!python
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 et

# wglurp database access.
#
# Refer to the AUTHORS file for copyright statements.


# Logging must always be loaded first!
from .. import logging

from sqlalchemy import (BigInteger, Binary, Column, DateTime, Enum, ForeignKey,
                        Index, Integer, SmallInteger, String, Sequence)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.schema import MetaData

# Create our common metadata.  We do this because we set our own naming
# convention.  We'll give this to our base class momentarily!
# NOTE: Multi-column indexes must still be named explicitly, along with things
# like ENUMs.
BaseTableMetaData = MetaData(
    naming_convention={
        'pk': '%(table_name)s_pk',
        'ix': '%(table_name)s_%(column_0_name)s_idx',
        'uq': '%(table_name)s_%(column_0_name)s_uidx',
        'ck': '%(table_name)s_ck_%(constraint_name)s',
        'fk': '%(table_name)s_%(column_0_name)s_fk_%(referred_table_name)s_%(referred_column_0_name)s',
    },
)

# Create our declarative base class, using our prepared MetaData.
BaseTable = declarative_base(metadata=BaseTableMetaData)


class Changes(BaseTable):
    """The changes table.

    This table is a queue of group changes.  The queue is written to by the
    Syncrepl client (a single process).  The queue is read by multiple workers.
    """
    __tablename__ = 'changes'

    # The unique ID of the queue entry.  The closer this entry is to the head
    # of a worker's queue, the lower the value.
    changes_id_seq = Sequence('changes_id_seq',
        metadata=BaseTable.metadata,
    )
    id = Column(
        BigInteger,
        changes_id_seq,
        server_default=changes_id_seq.next_value(),
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
    destinations_id_seq = Sequence('destinations_id_seq',
        metadata=BaseTable.metadata,
    )
    id = Column(
        Integer,
        destinations_id_seq,
        server_default=destinations_id_seq.next_value(),
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


class Challenges(BaseTable):
    __tablename__ = 'challenges'

    # The unique ID of the challenge.
    challenges_id_seq = Sequence('challenges_id_seq',
        metadata=BaseTable.metadata,
    )
    id = Column(
        BigInteger,
        challenges_id_seq,
        server_default=challenges_id_seq.next_value(),
        primary_key = True
    )

    # The unique ID of the destination.
    destination_id = Column(
        Integer,
        ForeignKey('destinations.id', onupdate='CASCADE', ondelete='CASCADE'),
        nullable = False
    )

    # A reference back to the parent Destination row.
    destination = relationship('Destinations')

    # A 256-bit (32-byte) nonce, to prevent DoS attacks.
    nonce = Column(
        Binary(
            length = 32
        ),
        nullable = False
    )

    # The 512-bit (64-byte) challenge value.
    challenge = Column(
        Binary(
            length = 64
        ),
        nullable = False
    )

    # The challenge expiration date & time.
    expiration = Column(
        DateTime,
        nullable = False,
        index = True
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


class Updates(BaseTable):
    """The updates which are waiting to go out.

    This table is a queue of updates, which are waiting to go out to various
    destination.

    This queue only contains updates for active destinations.  Destinations
    which are DEFERRED will have their updates in a separate queue.
    Destinations which are DISABLED won't have updates in this queue at all.
    """
    __tablename__ = 'updates'

    # The unique ID of the queue entry.  The closer this entry is to the head
    # of a worker's queue, the lower the value.
    updates_id_seq = Sequence('updates_id_seq',
        metadata=BaseTable.metadata,
    )
    id = Column(
        BigInteger,
        updates_id_seq,
        server_default = updates_id_seq.next_value(),
        primary_key = True
    )

    # The unique ID of the destination.
    destination_id = Column(
        Integer,
        ForeignKey('destinations.id', onupdate='CASCADE', ondelete='CASCADE')
    )

    # A reference back to the parent Destination row.
    destination = relationship('Destinations')

    # The message to pass to the destination.
    message = Column(
        JSON,
        nullable = False
    )


# Create an index on the worker ID and change ID.
Index('updates_destination_id_idx', Updates.destination_id, Updates.id)
