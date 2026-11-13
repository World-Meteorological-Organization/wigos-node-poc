"""Tests of the publishing job, which need Django and the database. Not found by
the plain unittest discovery of this package; run them with:
python manage.py test publishing.django_tests"""

import base64
import copy
import hashlib
import json
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django_tasks_db.models import DBTaskResult
from rest_framework.test import APITestCase

from api import stations
from api.models import Station, WIGOSNodeGroup, WIGOSNodeUser

from . import tasks
from .base import DefaultPublisher, Location, MessageGenerator, Operation, PublishError, Step, TransportLayer
from .generators.wmdr2 import RecordFileGenerator
from .generators.wnm import WNMGenerator
from .publishers import get_publishers
from .transports.mqtt import MQTTTransport
from .transports.s3 import S3Transport

Status = Station.PublicationStatus

with open("/test_data/test_wmdrv2.json") as f:
    BASE_RECORD = json.load(f)


def record(wsi, updated="2026-11-05T10:00:00Z", title="Publishing station"):
    data = copy.deepcopy(BASE_RECORD)
    data["id"] = wsi
    data["properties"]["title"] = title
    data["properties"]["updated"] = updated
    return data


def queued():
    """(station id, operation) of the queued publishing jobs, oldest first."""
    jobs = DBTaskResult.objects.order_by("enqueued_at")
    return [(job.args_kwargs["args"][0], job.args_kwargs["args"][2]) for job in jobs]


class MemoryStorage(TransportLayer):
    def __init__(self):
        super().__init__()
        self.files = {}
        self.fail_remove = False

    def send(self, message):
        url = f"mem://store/{message.name}"
        self.files[url] = message.body
        return Location(url)

    def remove(self, location):
        if self.fail_remove:
            raise PublishError("storage down")
        del self.files[location.url]


class MemoryBroker(TransportLayer):
    def __init__(self):
        super().__init__()
        self.sent = []
        self.failures = 0
        self.opened = 0
        self.closed = 0
        self.before_send = None

    def open(self):
        self.opened += 1

    def close(self):
        self.closed += 1

    def send(self, message):
        if self.before_send:
            self.before_send()
        if self.failures:
            self.failures -= 1
            raise PublishError("broker down")
        self.sent.append(json.loads(message.body))


class BrokenGenerator(MessageGenerator):
    def generate(self, event, deliveries):
        raise RuntimeError("boom")


class JobTestCase(TestCase):
    def setUp(self):
        self.storage = MemoryStorage()
        self.broker = MemoryBroker()
        self.publisher = DefaultPublisher(
            "wis2",
            [
                Step("storage", RecordFileGenerator(centre_id="io-test"), self.storage),
                Step("wnm", WNMGenerator(centre_id="io-test"), self.broker),
            ],
        )
        self.use_publishers(self.publisher)

        self.user = WIGOSNodeUser.objects.create_superuser(username="job_admin", email="job_admin@example.com", password="pw")

    def use_publishers(self, *publishers):
        patcher = mock.patch.object(tasks, "opened_publishers", return_value=list(publishers))
        patcher.start()
        self.addCleanup(patcher.stop)

    def station(self, wsi="0-756-0-job1", **kwargs):
        """A new station; its job stays queued."""
        return stations.create_station(self.user, record(wsi, **kwargs))

    def change(self, station, **kwargs):
        station = Station.objects.get(pk=station.pk)
        stations.update_station(self.user, station, record(station.wigos_identifier, **kwargs))

    def status_of(self, station):
        return Station.objects.values_list("publication_status", flat=True).get(pk=station.pk)

    def run_queued(self):
        """Run the oldest queued job here instead of in a worker."""
        job = DBTaskResult.objects.order_by("enqueued_at").first()
        job.delete()
        tasks.publish_station.call(*job.args_kwargs["args"])

    def publish_again(self, station):
        """The job the retry endpoint queues, run here."""
        tasks.publish_station.call(station.pk, Station.objects.get(pk=station.pk).wmdrv2, Operation.UPDATE)

    def test_an_out_of_date_job_publishes_but_leaves_the_station_alone(self):
        station = self.station()
        first = Station.objects.get(pk=station.pk).wmdrv2
        self.change(station, updated="2026-11-05T11:00:00Z", title="Changed")

        tasks.publish_station.call(station.pk, first, Operation.CREATE)  # the first save's job, run late

        self.assertEqual((len(self.storage.files), len(self.broker.sent)), (1, 1))
        self.assertEqual(self.status_of(station), Status.PENDING)  # left to the newer save's job

    def test_a_job_that_became_out_of_date_while_running_leaves_the_station_alone(self):
        station = self.station()
        self.run_queued()  # published once

        def saved_meanwhile():
            self.broker.before_send = None
            self.change(station, updated="2026-11-05T11:00:00Z", title="Changed")

        self.broker.before_send = saved_meanwhile
        self.broker.failures = 1  # this job fails, but the newer save's job decides the outcome
        with self.assertLogs("publishing", "ERROR"):
            self.publish_again(station)

        self.assertEqual(self.status_of(station), Status.PENDING)

    def test_publishes_the_file_then_its_wnm(self):
        station = self.station()

        self.run_queued()

        self.assertEqual(self.status_of(station), Status.PROCESSED)
        [url] = self.storage.files
        [wnm] = self.broker.sent
        self.assertEqual((wnm["links"][0]["href"], wnm["links"][0]["rel"]), (url, "canonical"))
        digest = base64.b64encode(hashlib.sha512(self.storage.files[url]).digest()).decode()
        self.assertEqual(wnm["properties"]["integrity"]["value"], digest)
        self.assertEqual(queued(), [])

    def test_the_next_publication_is_an_update(self):
        station = self.station()
        self.run_queued()

        self.change(station, updated="2026-11-05T11:00:00Z", title="Changed")
        self.run_queued()

        self.assertEqual([w["links"][0]["rel"] for w in self.broker.sent], ["canonical", "update"])

    def test_only_the_save_that_created_the_station_announces_it_as_new(self):
        station = self.station()
        self.broker.failures = 1
        with self.assertLogs("publishing", "ERROR"):
            self.run_queued()

        self.change(station, updated="2026-11-05T11:00:00Z", title="Changed")
        self.run_queued()

        [wnm] = self.broker.sent
        self.assertEqual(wnm["links"][0]["rel"], "update")

    def test_pubtime_is_the_records_updated_value_on_every_attempt(self):
        station = self.station(updated="2026-11-05T10:00:00Z")
        self.broker.failures = 1
        with self.assertLogs("publishing", "ERROR"):
            self.run_queued()
        self.assertEqual(self.status_of(station), Status.FAILED)

        self.publish_again(station)

        [wnm] = self.broker.sent
        self.assertEqual(wnm["properties"]["pubtime"], "2026-11-05T10:00:00Z")
        self.assertEqual(self.status_of(station), Status.PROCESSED)

    def test_a_failure_is_logged_and_undoes_the_stored_file(self):
        station = self.station()
        self.broker.failures = 1

        with self.assertLogs("publishing", "ERROR") as logs:
            self.run_queued()

        self.assertEqual(self.status_of(station), Status.FAILED)
        self.assertEqual(self.storage.files, {})
        self.assertIn("wis2:wnm: broker down", "\n".join(logs.output))

    def test_a_failure_keeps_the_last_success_and_its_file(self):
        station = self.station()
        self.run_queued()
        [url] = self.storage.files

        self.change(station, updated="2026-11-05T11:00:00Z", title="Changed")
        self.broker.failures = 1
        with self.assertLogs("publishing", "ERROR"):
            self.run_queued()

        self.assertEqual(self.status_of(station), Status.FAILED)
        self.assertEqual(list(self.storage.files), [url])  # the failed version's file is removed

    def test_a_failed_undo_is_logged_and_the_file_stays(self):
        station = self.station()
        self.broker.failures = 1
        self.storage.fail_remove = True
        with self.assertLogs("publishing", "ERROR") as logs:
            self.run_queued()

        self.assertEqual(self.status_of(station), Status.FAILED)
        output = "\n".join(logs.output)
        self.assertIn("wis2:wnm: broker down\nundo wis2: storage down", output)
        [url] = self.storage.files
        self.assertIn(url, output)  # so someone can remove it

    def test_a_save_during_the_job_is_left_to_its_own_job(self):
        station = self.station()

        def saved_meanwhile():
            self.broker.before_send = None
            self.change(station, updated="2026-11-05T11:00:00Z", title="Changed")

        self.broker.before_send = saved_meanwhile
        self.run_queued()

        self.assertEqual(self.status_of(station), Status.PENDING)
        self.assertEqual(queued(), [(station.pk, "update")])  # the save's own job

        self.run_queued()
        self.assertEqual(self.status_of(station), Status.PROCESSED)
        self.assertEqual(len(self.broker.sent), 2)

    def test_publishing_the_same_record_again_sends_it_again(self):
        station = self.station()
        self.run_queued()
        self.publish_again(station)
        self.assertEqual([w["links"][0]["rel"] for w in self.broker.sent], ["canonical", "update"])
        self.assertEqual(self.status_of(station), Status.PROCESSED)

    def test_a_deleted_station_is_ignored(self):
        tasks.publish_station.call(999999, record("0-756-0-gone"), Operation.CREATE)
        self.assertEqual(self.broker.sent, [])

    def test_a_crashed_job_fails_the_station_and_the_job(self):
        station = self.station()
        with mock.patch.object(tasks, "opened_publishers", side_effect=RuntimeError("boom")):
            with self.assertLogs("publishing", "ERROR"), self.assertRaises(RuntimeError):
                self.run_queued()
        self.assertEqual(self.status_of(station), Status.FAILED)

    def test_publishers_are_independent(self):
        other_storage = MemoryStorage()
        other = DefaultPublisher("other", [Step("storage", BrokenGenerator(), other_storage)])
        self.use_publishers(other, self.publisher)
        station = self.station()

        with self.assertLogs("publishing", "ERROR") as logs:
            self.run_queued()

        self.assertEqual(self.status_of(station), Status.FAILED)
        self.assertEqual(len(self.broker.sent), 1)  # wis2 still published
        self.assertIn("other:storage: boom", "\n".join(logs.output))

    def test_a_record_that_cant_be_published_fails(self):
        station = self.station()
        wmdrv2 = record("0-756-0-job1")
        del wmdrv2["properties"]["updated"], wmdrv2["properties"]["created"]
        Station.objects.filter(pk=station.pk).update(wmdrv2=wmdrv2)

        with self.assertLogs("publishing", "ERROR") as logs:
            self.publish_again(station)

        self.assertEqual(self.status_of(station), Status.FAILED)
        self.assertIn("properties.updated", "\n".join(logs.output))


class PublishersTestCase(SimpleTestCase):
    def test_the_wis2_publisher_stores_then_announces(self):
        [publisher] = get_publishers()
        storage, wnm = publisher.steps
        self.assertEqual((publisher.name, storage.name, wnm.name), ("wis2", "storage", "wnm"))
        self.assertIsInstance(storage.generator, RecordFileGenerator)
        self.assertIsInstance(storage.transport, S3Transport)
        self.assertIsInstance(wnm.generator, WNMGenerator)
        self.assertFalse(wnm.generator.skip_missing)
        self.assertIsInstance(wnm.transport, MQTTTransport)

    def test_publishers_are_built_once(self):
        self.assertIs(get_publishers()[0], get_publishers()[0])

    def test_wnms_can_be_switched_off(self):
        get_publishers.cache_clear()  # built once per process otherwise
        self.addCleanup(get_publishers.cache_clear)
        with override_settings(WIS2_PUBLISH_WNM=False):
            [publisher] = get_publishers()
        self.assertEqual([step.name for step in publisher.steps], ["storage"])



class OpenedPublishersTestCase(TestCase):
    def setUp(self):
        self.addCleanup(setattr, tasks, "_opened", None)
        tasks._opened = None

    def test_open_once_per_process_and_closed_on_shutdown(self):
        broker = MemoryBroker()
        publisher = DefaultPublisher("wis2", [Step("wnm", WNMGenerator(centre_id="io-test"), broker)])

        with mock.patch.object(tasks, "get_publishers", return_value=[publisher]):
            self.assertEqual(tasks.opened_publishers(), [publisher])
            self.assertEqual(tasks.opened_publishers(), [publisher])
        self.assertEqual(broker.opened, 1)

        tasks.close_publishers()
        self.assertEqual(broker.closed, 1)
        tasks.close_publishers()  # nothing open any more
        self.assertEqual(broker.closed, 1)


class EnqueueTestCase(APITestCase):
    """The explicit call in api.stations."""

    def setUp(self):
        self.member = WIGOSNodeUser.objects.create_user(username="enq_member", email="enq_member@example.com", password="pw")
        self.member.groups.add(WIGOSNodeGroup.objects.get(issuer_identifier=756).group)
        self.admin = WIGOSNodeUser.objects.create_superuser(username="enq_admin", email="enq_admin@example.com", password="pw")

    def test_a_create_is_pending_names_the_user_and_enqueues(self):
        station = stations.create_station(self.member, record("0-756-0-enq1"))

        self.assertEqual(queued(), [(station.pk, "create")])
        station.refresh_from_db()
        self.assertEqual(station.publication_status, Status.PENDING)
        self.assertEqual(station.last_changed_by, self.member)
        self.assertEqual(station.owner, self.member)

    def test_an_update_by_a_colleague_changes_who_but_not_the_owner(self):
        colleague = WIGOSNodeUser.objects.create_user(username="enq_other", email="enq_other@example.com", password="pw")
        colleague.groups.add(WIGOSNodeGroup.objects.get(issuer_identifier=756).group)
        station = stations.create_station(self.member, record("0-756-0-enq2"))
        Station.objects.filter(pk=station.pk).update(publication_status=Status.PROCESSED)
        station.refresh_from_db()
        DBTaskResult.objects.all().delete()

        stations.update_station(colleague, station, record("0-756-0-enq2", title="New"))

        station.refresh_from_db()
        self.assertEqual(station.publication_status, Status.PENDING)
        self.assertEqual(station.last_changed_by, colleague)
        self.assertEqual(station.owner, self.member)
        self.assertEqual(queued(), [(station.pk, "update")])

    def test_a_save_that_only_changes_updated_and_the_self_link_changes_nothing(self):
        station = stations.create_station(self.member, record("0-756-0-enq9"))
        Station.objects.filter(pk=station.pk).update(publication_status=Status.PROCESSED)
        station.refresh_from_db()
        DBTaskResult.objects.all().delete()
        colleague = WIGOSNodeUser.objects.create_user(username="enq_same", email="enq_same@example.com", password="pw")
        colleague.groups.add(WIGOSNodeGroup.objects.get(issuer_identifier=756).group)
        same = record("0-756-0-enq9", updated="2026-11-06T09:00:00Z")
        same["links"] = [{"rel": "self", "href": "http://elsewhere/api/wmdrv2/wsi/0-756-0-enq9"}, *same.get("links", [])]

        stations.update_station(colleague, station, same)

        station.refresh_from_db()
        self.assertEqual(station.wmdrv2["properties"]["updated"], "2026-11-05T10:00:00Z")
        self.assertEqual((station.publication_status, station.last_changed_by), (Status.PROCESSED, self.member))
        self.assertEqual(queued(), [])

    def test_a_save_whose_job_cant_be_queued_isnt_saved(self):
        with mock.patch.object(stations, "request_publication", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                stations.create_station(self.member, record("0-756-0-enq8"))
        self.assertFalse(Station.objects.filter(wigos_identifier="0-756-0-enq8").exists())

    def test_superusers_are_not_named(self):
        station = stations.create_station(self.admin, record("0-756-0-enq3"))
        station.refresh_from_db()
        self.assertIsNone(station.last_changed_by)

    def test_a_rejected_save_enqueues_nothing(self):
        first = stations.create_station(self.member, record("0-756-0-enq4"))
        with self.assertRaises(stations.StationError):
            stations.create_station(self.member, record("0-756-0-enq4"))  # WSI taken
        self.assertEqual(queued(), [(first.pk, "create")])

    def post_batch(self, updates, dry_run=False):
        self.client.force_authenticate(self.member)
        return self.client.post(reverse("wmdrv2-batch"), {"dry_run": dry_run, "updates": updates}, format="json")

    def test_a_batch_dry_run_enqueues_nothing(self):
        station = stations.create_station(self.member, record("0-756-0-enq5"))
        DBTaskResult.objects.all().delete()
        response = self.post_batch([{"station_id": station.pk, "wmdrv2": record("0-756-0-enq5", title="New")}], dry_run=True)
        self.assertEqual(response.json()["summary"], {"ok": 1, "error": 0})
        self.assertEqual(queued(), [])

    def test_a_batch_enqueues_only_the_accepted_updates(self):
        ok = stations.create_station(self.member, record("0-756-0-enq6"))
        other = stations.create_station(self.member, record("0-756-0-enq7"))
        DBTaskResult.objects.all().delete()
        response = self.post_batch([
            {"station_id": ok.pk, "wmdrv2": record("0-756-0-enq6", title="New")},
            {"station_id": other.pk, "wmdrv2": record("0-756-0-enq6", title="Clash")},  # WSI of the first station
        ])
        self.assertEqual(response.json()["summary"], {"ok": 1, "error": 1})
        self.assertEqual(queued(), [(ok.pk, "update")])
