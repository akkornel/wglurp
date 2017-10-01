#!python
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 et

# wglurp database change messages.
#
# Refer to the AUTHORS file for copyright statements.


# Logging must always be imported first!
from .. import logging

# Get our configuration object
from ..config import ConfigOption

from . import engine
from . import schema
import json


class ChangeEntry(object):
    
    def __init__(self, change=None, **kwargs):
        """Create a new change entry.
        """

        # If we got a change object, then just use it!
        if change is not None:
            # Make sure we didn't get any parameters.
            if len(kwargs) > 0:
                raise Exception()

            # Make sure change is the write type.
            if type(change) is not schema.Changes:
                raise Exception()

            # Copy it in!
            self.change = change

        # If we did not get a change object, build one!
        else:
            if 'action' not in kwargs:
                raise Exception()
            if 'group' not in kwargs:
                raise Exception()
            if 'members' not in kwargs:
                raise Exception()

            # Construct a database object from what we got.
            # NOTE: We use worker #0 for now.
            self.change = schema.Changes(
                worker = 0,
                action = kwargs['action'],
                group  = kwargs['group'],
                data   = list(kwargs['members']),
            )

            # Mark that calculation has not been completed.
            self.calculated = False

        # That's it!
        return None


    def calculate_worker(self):
        if self.calculated is True:
            return

        if self.change in ('FLUSH_CHANGES', 'FLUSH_ALL', 'WAIT'):
            self.change.worker = 0
        else:
            # The worker is based on the group name, mod the number of workers.
            # Then, shift up one, so that worker #0 is reserved.
            self.change.worker = 1 + (hash(self.change.group) %
                                 int(ConfigOption['ldap']['workers']))

        self.calculated = True


    def add(self, session):
        self.calculate_worker()
        session.add(self.change)
