import unittest

from publishing.celery import app


class CeleryAppTestCase(unittest.TestCase):
    def test_uses_valkey_and_stores_no_results(self):
        self.assertTrue(app.conf.broker_url.startswith("redis://"))
        self.assertTrue(app.conf.task_ignore_result)

    def test_fetched_jobs_of_a_dead_worker_come_back_after_30_minutes(self):
        self.assertEqual(app.conf.broker_transport_options["visibility_timeout"], 1800)
