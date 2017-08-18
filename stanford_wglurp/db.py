#!python
# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 et

# stanford-wglurp database client code.
#
# Copyright © 2017 The Board of Trustees of the Leland Stanford Jr. University.
#
# LICENSE


import sqlite3

def connect():
    db = sqlite3.connect('/tmp/wglurp-db', check_same_thread=False)
    db.isolation_level = 'IMMEDIATE'

    db.execute('''
    CREATE TABLE IF NOT EXISTS workgroups (
        name VARCHAR(128) PRIMARY KEY
    )''')

    db.execute('''
    CREATE TABLE IF NOT EXISTS members (
        uniqueid VARCHAR(128) PRIMARY KEY,
        username VARCHAR(128) UNIQUE
    )''')

    db.execute('''
    CREATE TABLE IF NOT EXISTS workgroup_members (
        workgroup_name UNSIGNED INT REFERENCES workgroups (name),
        member_id VARCHAR(128) REFERENCES members (uniqueid)
    )''')

    db.isolation_level = None
    return db
