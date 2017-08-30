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


