#!python
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 et

# wglurp helper for AWS
#
# Refer to the AUTHORS file for copyright statements.


# Logging must always be loaded first!
from .. import logging

import boto3

from ..config import ConfigBoolean, ConfigOption

if ConfigBoolean['aws']['enabled'] is True:
    # This is the boto3 session that we will be using for all our stuff.
    session = boto3.session.Session(
        aws_access_key_id = ConfigOption['aws']['access-key'],
        aws_secret_access_key = ConfigOption['aws']['secret-key'],
        region_name = 'us-east-1',
    )


def client(service_name, region_name=None):
    """Get a boto3 client, using our credentials.

    :param str service_name: The name of the service to request

    :param str region_name: Optionally, the name of the region to target requests.

    Returns a boto3 client for the requested service, initialized using our
    credentials.

    .. note:
        In many cases, the region name is not required, because for some
        things, the region is encoded into the entity's identifier.

    .. warning:
        If AWS support has not been enabled, this will throw an exception.
        Before calling, make sure :obj:`~stanford_wglurp.config.ConfigOption`
        key `aws`/`enabled` is :obj:`True`!
    """
    return session.client(service_name=service_name, region_name=region_name)
