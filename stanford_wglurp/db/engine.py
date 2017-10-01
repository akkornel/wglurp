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
from sqlalchemy.orm import sessionmaker

from ..config import ConfigBoolean, ConfigOption
from . import schema


# Add Postgres-specific settings.
# First, require SSL from the server.
db_options = dict()
db_options['sslmode'] = 'require'

# If a CA is provided, add it to the configuration.
if ConfigOption['db']['capath'] != '':
    db_options['sslrootcert'] = ConfigOption['db-cert']['capath']

# If we are using client cert authentication, then add our client key and cert.
if ConfigBoolean['db-cert']['active'] is True:
    db_options['sslcert'] = ConfigOption['db-cert']['certpath']
    db_options['sslkey'] = ConfigOption['db-cert']['keypath']

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
                else ConfigOption['db-access']['password']),

    query = db_options
)


# Create an Engine for our URL.
DB = create_engine(db_url)

# Create a session factory, bound to our engine.
Session = sessionmaker(bind=DB)
AutoCommitSession = sessionmaker(bind=DB, autocommit=True)
