#!python
# -*- coding: utf-8 -*-
# vim: sw=4 ts=4 et

# stanford-wglurp Expander main and metrics-recording code.
#
# Refer to the AUTHORS file for copyright statements.


# We have to load the logger first!
from ..logging import logger

import multiprocessing
from os import kill
import signal
import sys

from . import worker
from ..config import ConfigOption
from ..db import engine, schema


# The dictionary of workers, and the program status (Singleton.exiting or not) is global.
class Singleton(object):
    worker_processes = dict()
    exiting = False


def prepare_worker(worker_number):
    logger.debug('Preparing worker #%d' % worker_number)
    process = multiprocessing.Process(
        name='expander%d' % worker_number,
        target=worker.run,
        args=(worker_number,),
        daemon=True,
    )
    Singleton.worker_processes[worker_number] = process


def start_worker(worker_number):
    logger.debug('Starting worker #%d' % worker_number)
    Singleton.worker_processes[worker_number].start()
    logger.info('Worker #%d started with PID %d' %
        (worker_number, Singleton.worker_processes[worker_number].pid)
    )


def main():
    # Set us up to use forkserver
    logger.info('Preparing forkserver')
    multiprocessing.set_start_method('forkserver')

    # Set up a stop handler.
    def stop_handler(signal_number, frame):
        logger.warning('Expander stop handler has been called.')
        logger.info('The received signal was %d' % signal_number)
        Singleton.exiting = True
        for (number, process) in Singleton.worker_processes.items():
            logger.info('Signalling worker #%d PID %d' %
                (number, process.pid)
            )
            kill(process.pid, signal.SIGTERM)

    # Prepare our workers
    worker_count = int(ConfigOption['ldap']['workers'])
    for worker_number in range(1, 1 + worker_count):
        prepare_worker(worker_number)

    # Put the stop handler in place
    signal.signal(signal.SIGHUP, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    signal.signal(signal.SIGTERM, stop_handler)

    # Start our workers
    logger.info('Starting workers!')
    for number in Singleton.worker_processes.keys():
        start_worker(number)

    # At this point, we wait (possibly for a very long time) for workers to
    # exit.

    # Wait for workers to exit, either expectedly or not.
    # This loop iterates once each time a process exits, giving us the chance
    # to either restart it or clean it up.
    while len(Singleton.worker_processes) > 0:
        # TODO: Worker 0 stuff.

        # Wait for a process to exit.
        logger.info('Waiting for a worker to exit (this will be a while)...')
        multiprocessing.connection.wait(
            [process.sentinel for process in Singleton.worker_processes.values()],
            timeout=None
        )
        logger.info('At least one sentinel has triggered!')

        # Go through each worker to see which one exited.
        # NOTE: We force the .items() iterator to run before we loop, because
        # we will be changing the dict inside the loop.
        for (number, process) in list(Singleton.worker_processes.items()):
            logger.debug('Checking worker #%d (PID %d)' % (number, process.pid))

            # Try to join the process.  If it has an exitcode, it exited.
            process.join(0)
            if process.exitcode is None:
                continue
            logger.info('Worker #%d (PID %d) exited with code %d' %
                        (number, process.pid, process.exitcode)
            )

            # Remove the worker from the dict.
            del Singleton.worker_processes[number]

            # If we are not exiting, then something went wrong!
            if Singleton.exiting is False:
                logger.error('Worker #%d (PID %d) exited unexpectedly!' %
                             (number, process.pid)
                )
                logger.info('Re-launching worker #%d' % number)
                prepare_worker(number)
                start_worker(number)

            # TODO: Catch workers failing more than 3x in 1 minute.

    # There are no more workers left.
    logger.info('No more workers remaining.  Exiting now.')
    logger.info('Go Tree!')
    sys.exit(0)

    # TODO: Metrics!
