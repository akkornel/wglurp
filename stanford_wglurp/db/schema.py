#!python
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 et

# wglurp database access.
#
# Refer to the AUTHORS file for copyright statements.


# Logging must always be loaded first!
from .. import logging

from sqlalchemy import Column, Enum, BigInteger, SmallInteger, String, Sequence
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declarative_base

BaseTable = declarative_base()


class ChangesTable(BaseTable):
    __tablename__ = 'changes'

    id = Column(
        BigInteger,
        Sequence('changes_id_sequence'),
        primary_key = True
    )
    worker = Column(
        SmallInteger,
        nullable = False
    )
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
    group = Column(
        String,
    )
    data = Column(
        JSON,
    )

