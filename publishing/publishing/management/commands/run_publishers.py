"""Runs the publishing jobs: several `db_worker` processes, each running one job
at a time. A process that exits is started again. On SIGTERM or SIGINT (e.g.
docker stop) each process gets the signal once, finishes its current job and
exits, and this command waits for them."""

import logging
import signal
import subprocess
import sys
import time

from django.core.management.base import BaseCommand

logger = logging.getLogger("publishing")


class Command(BaseCommand):
    help = "Run the publishing jobs in several worker processes."

    def add_arguments(self, parser):
        parser.add_argument("--processes", type=int, default=4, help="Jobs run at the same time (default: 4).")

    def handle(self, *, processes, **options):
        command = [sys.executable, sys.argv[0], "db_worker", "--no-reload"]
        received = []
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda signum, frame: received.append(signum))

        def start():
            # own session: a Ctrl+C in the terminal reaches only this process,
            # which passes it on once (a second signal stops a job midway)
            return subprocess.Popen(command, start_new_session=True)

        children = [start() for _ in range(processes)]
        logger.info("Started %d publishing processes", processes)
        while not received:
            for index, child in enumerate(children):
                if child.poll() is not None:
                    logger.warning("Publishing process %d exited with %s, starting it again", child.pid, child.returncode)
                    children[index] = start()
            time.sleep(1)

        logger.info("Stopping the publishing processes after their current jobs")
        for child in children:
            if child.poll() is None:
                child.send_signal(received[0])
        for child in children:
            child.wait()
