#!python
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 et

# wglurp database access.
#
# Refer to the AUTHORS file for copyright statements.


# Logging must always be imported first!
from .. import logging

import psycopg2
from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL

from ..config import ConfigOption
from . import schema


# Construct our databse URL.
# ConfigOption can't hold non-strings, so we need to convert empty strings to
# None.  Also, for the port number, we convert that to an int.
db_url = URL('postgresql',
    host = (None if ConfigOption['db']['host'] == ''
            else ConfigOption['db']['host']),

    port = (None if ConfigOption['db']['port'] == ''
            else int(ConfigOption['db']['port'])),

    database = (None if ConfigOption['db']['database'] == ''
                else ConfigOption['db']['database']),

    username = (None if ConfigOption['db-access']['username'] == ''
                else ConfigOption['db-access']['username']),

    password = (None if ConfigOption['db-access']['password'] == ''
                else ConfigOption['db-access']['password'])
)


# Create an Engine for our URL.
db = create_engine(db_url)
