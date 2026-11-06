"""Tests of the publishing job, which need Django and the database. Not found by
the plain unittest discovery of this package; run them with:
python manage.py test publishing.django_tests"""

import base64
import copy
import hashlib
import json
from unittest import mock

import redis
from django.conf import settings
from django.core.checks.registry import registry
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from kombu.exceptions import OperationalError
from rest_framework.test import APITestCase

from api import stations
from api.models import Station, WIGOSNodeGroup, WIGOSNodeUser

from . import state, tasks
from .base import DefaultPublisher, Delivery, Location, Message, MessageGenerator, PublishError, Step, TransportLayer
from .checks import check_publishers
from .generators.wmdr2 import RecordFileGenerator
from .generators.wnm import WNMGenerator
from .publishers import get_publishers
from .registry import ConfigurationError
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


class FakeLock:
    def __init__(self, held, name):
        self.held = held
        self.name = name

    def acquire(self):
        if self.name in self.held:
            return False
        self.held.add(self.name)
        return True

    def release(self):
        self.held.discard(self.name)

    def locked(self):
        return self.name in self.held


class FakeValkey:
    def __init__(self):
        self.values = {}
        self.held = set()

    def get(self, key):
        return self.values.get(key)

    def mget(self, keys):
        return [self.values.get(key) for key in keys]

    def set(self, key, value):
        self.values[key] = value

    def lock(self, name, **kwargs):
        return FakeLock(self.held, name)


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


class MemoryPublisher(DefaultPublisher):
    def __init__(self, *args, storage, **kwargs):
        super().__init__(*args, **kwargs)
        self.storage = storage

    def retrieve(self, location):
        return self.storage.files[location.url]


class BrokenGenerator(MessageGenerator):
    def generate(self, event, deliveries):
        raise RuntimeError("boom")


class JobTestCase(TestCase):
    def setUp(self):
        self.valkey = FakeValkey()
        patcher = mock.patch.object(state, "client", return_value=self.valkey)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.delay = mock.patch.object(tasks.publish_station, "delay").start()
        self.addCleanup(mock.patch.stopall)

        self.storage = MemoryStorage()
        self.broker = MemoryBroker()
        self.publisher = MemoryPublisher(
            "wis2",
            [
                Step("storage", RecordFileGenerator(centre_id="io-test"), self.storage),
                Step("wnm", WNMGenerator(centre_id="io-test"), self.broker),
            ],
            storage=self.storage,
        )
        self.use_publishers(self.publisher)

        self.user = WIGOSNodeUser.objects.create_superuser(username="job_admin", email="job_admin@example.com", password="pw")

    def use_publishers(self, *publishers):
        patcher = mock.patch.object(tasks, "opened_publishers", return_value=list(publishers))
        patcher.start()
        self.addCleanup(patcher.stop)

    def station(self, wsi="0-756-0-job1", **kwargs):
        return stations.create_station(self.user, record(wsi, **kwargs))

    def status_of(self, station):
        return Station.objects.values_list("publication_status", flat=True).get(pk=station.pk)

    def test_publishes_the_file_then_its_wnm(self):
        station = self.station()

        tasks.publish_station(station.pk)

        self.assertEqual(self.status_of(station), Status.PROCESSED)
        [url] = self.storage.files
        [wnm] = self.broker.sent
        self.assertEqual((wnm["links"][0]["href"], wnm["links"][0]["rel"]), (url, "canonical"))
        digest = base64.b64encode(hashlib.sha512(self.storage.files[url]).digest()).decode()
        self.assertEqual(wnm["properties"]["integrity"]["value"], digest)

        saved = state.load(station.pk)
        self.assertEqual([d["step"] for d in saved["deliveries"]], ["storage", "wnm"])
        self.assertEqual(saved["deliveries"][0]["url"], url)
        self.assertEqual((saved["error"], saved["leftovers"]), ("", []))
        self.assertIsNotNone(saved["finished_at"])
        self.assertFalse(state.is_locked(station.pk))
        self.delay.assert_not_called()

    def test_the_next_publication_is_an_update(self):
        station = self.station()
        tasks.publish_station(station.pk)

        stations.update_station(self.user, station, record("0-756-0-job1", updated="2026-11-05T11:00:00Z"))
        tasks.publish_station(station.pk)

        self.assertEqual([w["links"][0]["rel"] for w in self.broker.sent], ["canonical", "update"])

    def test_pubtime_is_the_records_updated_value_on_every_attempt(self):
        station = self.station(updated="2026-11-05T10:00:00Z")
        self.broker.failures = 1
        tasks.publish_station(station.pk)
        self.assertEqual(self.status_of(station), Status.FAILED)

        Station.objects.filter(pk=station.pk).update(publication_status=Status.PENDING)
        tasks.publish_station(station.pk)

        [wnm] = self.broker.sent
        self.assertEqual(wnm["properties"]["pubtime"], "2026-11-05T10:00:00Z")

    def test_a_failure_is_recorded_and_undoes_the_stored_file(self):
        station = self.station()
        self.broker.failures = 1

        tasks.publish_station(station.pk)

        self.assertEqual(self.status_of(station), Status.FAILED)
        self.assertEqual(self.storage.files, {})
        saved = state.load(station.pk)
        self.assertEqual(saved["error"], "wis2:wnm: broker down")
        self.assertEqual(saved["deliveries"], [])

    def test_a_create_that_failed_is_still_announced_as_canonical(self):
        station = self.station()
        self.broker.failures = 1
        tasks.publish_station(station.pk)

        stations.update_station(self.user, station, record("0-756-0-job1", updated="2026-11-05T11:00:00Z"))
        tasks.publish_station(station.pk)

        [wnm] = self.broker.sent
        self.assertEqual(wnm["links"][0]["rel"], "canonical")

    def test_a_failure_keeps_the_last_success_and_its_file(self):
        station = self.station()
        tasks.publish_station(station.pk)
        [url] = self.storage.files

        # the same `updated`, so the same file name
        Station.objects.filter(pk=station.pk).update(publication_status=Status.PENDING)
        self.broker.failures = 1
        tasks.publish_station(station.pk)

        self.assertEqual(self.status_of(station), Status.FAILED)
        self.assertIn(url, self.storage.files)
        self.assertEqual(state.load(station.pk)["deliveries"][0]["url"], url)

    def test_a_failed_undo_leaves_a_leftover_removed_on_the_next_attempt(self):
        station = self.station()
        self.broker.failures = 1
        self.storage.fail_remove = True
        tasks.publish_station(station.pk)

        saved = state.load(station.pk)
        self.assertEqual(saved["error"], "wis2:wnm: broker down\nundo wis2: storage down")
        [leftover] = saved["leftovers"]
        self.assertIn(leftover["url"], self.storage.files)

        stations.update_station(self.user, station, record("0-756-0-job1", updated="2026-11-05T11:00:00Z"))
        self.storage.fail_remove = False
        tasks.publish_station(station.pk)

        self.assertEqual(self.status_of(station), Status.PROCESSED)
        self.assertNotIn(leftover["url"], self.storage.files)
        self.assertEqual(state.load(station.pk)["leftovers"], [])

    def test_a_leftover_that_still_cant_be_removed_is_kept(self):
        station = self.station()
        self.broker.failures = 1
        self.storage.fail_remove = True
        tasks.publish_station(station.pk)
        [leftover] = state.load(station.pk)["leftovers"]

        stations.update_station(self.user, station, record("0-756-0-job1", updated="2026-11-05T11:00:00Z"))
        with self.assertLogs("publishing", "ERROR"):
            tasks.publish_station(station.pk)

        self.assertEqual(self.status_of(station), Status.PROCESSED)
        self.assertEqual(state.load(station.pk)["leftovers"], [leftover])

    def test_a_save_during_the_job_stays_pending_and_gets_a_new_job(self):
        station = self.station()

        def saved_meanwhile():
            self.broker.before_send = None
            stations.update_station(self.user, Station.objects.get(pk=station.pk), record("0-756-0-job1", updated="2026-11-05T11:00:00Z"))

        self.broker.before_send = saved_meanwhile
        tasks.publish_station(station.pk)

        self.assertEqual(self.status_of(station), Status.PENDING)
        self.delay.assert_called_once_with(station.pk)
        self.assertFalse(state.is_locked(station.pk))  # or the new job would stop at it

    def test_a_job_finding_the_station_locked_stops(self):
        station = self.station()
        self.assertTrue(state.station_lock(station.pk).acquire())

        tasks.publish_station(station.pk)

        self.assertEqual(self.status_of(station), Status.PENDING)
        self.assertEqual(self.broker.sent, [])
        self.assertTrue(state.is_locked(station.pk))  # still the first job's

    def test_a_second_job_finds_nothing_to_do(self):
        station = self.station()
        tasks.publish_station(station.pk)
        tasks.publish_station(station.pk)
        self.assertEqual(len(self.broker.sent), 1)
        self.delay.assert_not_called()

    def test_a_deleted_station_is_ignored(self):
        tasks.publish_station(999999)
        self.assertEqual(self.broker.sent, [])

    def test_a_crashed_job_releases_the_lock(self):
        station = self.station()
        with mock.patch.object(tasks, "_publish", side_effect=RuntimeError("valkey down")):
            with self.assertRaises(RuntimeError):
                tasks.publish_station(station.pk)
        self.assertFalse(state.is_locked(station.pk))
        self.assertEqual(self.status_of(station), Status.PROCESSING)  # a user's retry takes it from here

    def test_publishers_are_independent(self):
        other_storage = MemoryStorage()
        other = MemoryPublisher("other", [Step("storage", BrokenGenerator(), other_storage)], storage=other_storage)
        self.use_publishers(other, self.publisher)
        station = self.station()

        with self.assertLogs("publishing", "ERROR"):
            tasks.publish_station(station.pk)

        self.assertEqual(self.status_of(station), Status.FAILED)
        self.assertEqual(len(self.broker.sent), 1)  # wis2 still published
        saved = state.load(station.pk)
        self.assertEqual(saved["error"], "other:storage: boom")
        self.assertEqual({d["publisher"] for d in saved["deliveries"]}, {"wis2"})

    def test_a_record_that_cant_be_published_fails(self):
        station = self.station()
        wmdrv2 = record("0-756-0-job1")
        del wmdrv2["properties"]["updated"], wmdrv2["properties"]["created"]
        Station.objects.filter(pk=station.pk).update(wmdrv2=wmdrv2)

        with self.assertLogs("publishing", "ERROR"):
            tasks.publish_station(station.pk)

        self.assertEqual(self.status_of(station), Status.FAILED)
        self.assertIn("properties.updated", state.load(station.pk)["error"])


LOG = "publishing.transports.log.LogTransport"
BROKEN = [
    {"NAME": "files", "STEPS": [
        {"NAME": "store", "GENERATOR": {"CLASS": "publishing.generators.wmdr2.RecordFileGenerator"}, "TRANSPORT": {"CLASS": LOG}},
    ]},
    {"NAME": "files", "STEPS": [
        {"NAME": "store", "GENERATOR": {"CLASS": "nowhere.Generator"}, "TRANSPORT": {"CLASS": LOG}},
    ]},
]


class PublishersSettingTestCase(SimpleTestCase):
    def test_configured_publishers_build(self):
        self.assertEqual(check_publishers(None), [])
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

    def test_the_check_is_registered(self):
        self.assertIn(check_publishers, registry.get_checks())

    @override_settings(PUBLISHERS=BROKEN)
    def test_check_reports_every_problem(self):
        errors = check_publishers(None)
        self.assertEqual([e.id for e in errors], ["publishing.E001", "publishing.E001"])
        self.assertIn("centre_id", errors[0].msg)
        self.assertIn("NAME is used more than once", errors[1].msg)
        with self.assertRaises(ConfigurationError):
            get_publishers()

    def test_changed_setting_rebuilds(self):
        default = get_publishers()
        with override_settings(PUBLISHERS=[]):
            self.assertEqual(get_publishers(), [])
        self.assertEqual([p.name for p in get_publishers()], [p.name for p in default])

    @override_settings()
    def test_missing_setting_means_no_publishers(self):
        del settings.PUBLISHERS
        # deleting a setting sends no setting_changed, so reset by hand
        get_publishers.cache_clear()
        self.addCleanup(get_publishers.cache_clear)
        self.assertEqual(check_publishers(None), [])
        self.assertEqual(get_publishers(), [])


class ReadBackReceiptsTestCase(SimpleTestCase):
    def test_a_read_back_receipt_has_no_body(self):
        delivery = Delivery("wis2", Message(b"secret", "text/plain", name="f"), Location("http://f"), step="storage")
        loaded = state.load_delivery(state.dump_delivery(delivery))
        self.assertIsNone(loaded.message.body)
        self.assertEqual(loaded.location, delivery.location)
        self.assertEqual((loaded.publisher, loaded.step, loaded.message.name), ("wis2", "storage", "f"))


class OpenedPublishersTestCase(TestCase):
    def setUp(self):
        self.addCleanup(setattr, tasks, "_opened", None)
        tasks._opened = None

    def test_open_once_per_process_and_closed_on_shutdown(self):
        storage = MemoryStorage()
        broker = MemoryBroker()
        publisher = MemoryPublisher("wis2", [Step("wnm", WNMGenerator(centre_id="io-test"), broker)], storage=storage)

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
        self.delay = mock.patch.object(tasks.publish_station, "delay").start()
        self.addCleanup(mock.patch.stopall)
        self.member = WIGOSNodeUser.objects.create_user(username="enq_member", email="enq_member@example.com", password="pw")
        self.member.groups.add(WIGOSNodeGroup.objects.get(issuer_identifier=756).group)
        self.admin = WIGOSNodeUser.objects.create_superuser(username="enq_admin", email="enq_admin@example.com", password="pw")

    def test_a_create_is_pending_names_the_user_and_enqueues_after_commit(self):
        with self.captureOnCommitCallbacks() as callbacks:
            station = stations.create_station(self.member, record("0-756-0-enq1"))
        self.delay.assert_not_called()

        for callback in callbacks:
            callback()

        self.delay.assert_called_once_with(station.pk)
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

        with self.captureOnCommitCallbacks(execute=True):
            stations.update_station(colleague, station, record("0-756-0-enq2", title="New"))

        station.refresh_from_db()
        self.assertEqual(station.publication_status, Status.PENDING)
        self.assertEqual(station.last_changed_by, colleague)
        self.assertEqual(station.owner, self.member)
        self.delay.assert_called_once_with(station.pk)

    def test_a_failure_to_enqueue_is_logged_and_keeps_the_change(self):
        self.delay.side_effect = OSError("valkey down")
        with self.assertLogs("django.test", "ERROR"):  # where the test helper logs it
            with self.captureOnCommitCallbacks(execute=True):
                station = stations.create_station(self.member, record("0-756-0-enq8"))
        station.refresh_from_db()
        self.assertEqual(station.publication_status, Status.PENDING)

    def test_after_the_broker_fails_only_the_first_save_tries_for_a_while(self):
        self.addCleanup(setattr, tasks, "_broker_down_until", 0.0)
        self.delay.side_effect = OperationalError("valkey down")

        with self.assertLogs("publishing", "ERROR"):
            tasks.request_publication(1)
        with self.assertLogs("publishing", "WARNING"):
            tasks.request_publication(2)
        self.delay.assert_called_once_with(1)

        # the window is over and the broker is back
        tasks._broker_down_until = 0.0
        self.delay.side_effect = None
        self.delay.reset_mock()
        tasks.request_publication(3)
        self.delay.assert_called_once_with(3)

    def test_superusers_are_not_named(self):
        station = stations.create_station(self.admin, record("0-756-0-enq3"))
        station.refresh_from_db()
        self.assertIsNone(station.last_changed_by)

    def test_a_rejected_save_enqueues_nothing(self):
        stations.create_station(self.member, record("0-756-0-enq4"))
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with self.assertRaises(stations.StationError):
                stations.create_station(self.member, record("0-756-0-enq4"))  # WSI taken
        self.assertEqual(callbacks, [])

    def post_batch(self, updates, dry_run=False):
        self.client.force_authenticate(self.member)
        return self.client.post(reverse("wmdrv2-batch"), {"dry_run": dry_run, "updates": updates}, format="json")

    def test_a_batch_dry_run_enqueues_nothing(self):
        station = stations.create_station(self.member, record("0-756-0-enq5"))
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.post_batch([{"station_id": station.pk, "wmdrv2": record("0-756-0-enq5", title="New")}], dry_run=True)
        self.assertEqual(response.json()["summary"], {"ok": 1, "error": 0})
        self.assertEqual(callbacks, [])

    def test_a_batch_enqueues_only_the_accepted_updates(self):
        ok = stations.create_station(self.member, record("0-756-0-enq6"))
        other = stations.create_station(self.member, record("0-756-0-enq7"))
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_batch([
                {"station_id": ok.pk, "wmdrv2": record("0-756-0-enq6", title="New")},
                {"station_id": other.pk, "wmdrv2": record("0-756-0-enq6", title="Clash")},  # WSI of the first station
            ])
        self.assertEqual(response.json()["summary"], {"ok": 1, "error": 1})
        self.delay.assert_called_once_with(ok.pk)


class PublicationsApiTestCase(APITestCase):
    """Real stations saved through the API, nothing set by hand apart from how
    their jobs ended, then what each kind of user sees and can do."""

    def setUp(self):
        self.valkey = FakeValkey()
        mock.patch.object(state, "client", return_value=self.valkey).start()
        self.delay = mock.patch.object(tasks.publish_station, "delay").start()
        self.addCleanup(mock.patch.stopall)

        self.author = self.user("uc_author", 756)
        self.colleague = self.user("uc_colleague", 756)  # same group, didn't make the change
        self.foreigner = self.user("uc_foreigner", 76)
        self.outsider = self.user("uc_outsider")
        self.admin = WIGOSNodeUser.objects.create_superuser(username="uc_admin", email="uc_admin@example.com", password="pw")

    def user(self, name, *issuers):
        user = WIGOSNodeUser.objects.create_user(username=name, email=f"{name}@example.com", password="pw")
        for issuer in issuers:
            user.groups.add(WIGOSNodeGroup.objects.get(issuer_identifier=issuer).group)
        return user

    def create(self, wsi, user=None, **kwargs):
        return self.create_record(record(wsi, **kwargs), user)

    def create_record(self, data, user=None):
        self.client.force_authenticate(user or self.author)
        response = self.client.post(reverse("wmdrv2"), data, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return Station.objects.get(pk=response.json()["station_id"])

    def update(self, station, data, user=None):
        self.client.force_authenticate(user or self.author)
        response = self.client.put(reverse("wmdrv2", args=[station.pk]), data, format="json")
        self.assertEqual(response.status_code, 200, response.content)

    def set_status(self, station, status):
        Station.objects.filter(pk=station.pk).update(publication_status=status)

    def status_of(self, station):
        return Station.objects.values_list("publication_status", flat=True).get(pk=station.pk)

    def listed(self, user=None, **params):
        self.client.force_authenticate(user or self.author)
        response = self.client.get(reverse("publications"), params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["results"]

    def seen(self, user=None, **params):
        return [row["wigos_identifier"] for row in self.listed(user, **params)]

    def retry(self, station, user=None):
        self.client.force_authenticate(user or self.author)
        return self.client.post(reverse("publication-retry", args=[station.pk]))

    def test_login_is_required(self):
        station = self.create("0-756-0-uc0")
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(reverse("publications")).status_code, (401, 403))
        self.assertIn(self.client.post(reverse("publication-retry", args=[station.pk])).status_code, (401, 403))

    def test_those_who_can_edit_the_station_see_it_and_the_rest_dont(self):
        self.create("0-756-0-uc1")
        for user in (self.author, self.colleague, self.admin):
            self.assertEqual(self.seen(user), ["0-756-0-uc1"], user.username)
        for user in (self.foreigner, self.outsider):
            self.assertEqual(self.seen(user), [], user.username)

    def test_one_row_per_station_however_many_changes(self):
        station = self.create("0-756-0-uc2")
        self.update(station, record("0-756-0-uc2", title="New"), self.colleague)
        self.assertEqual(self.seen(), ["0-756-0-uc2"])

    def test_a_wsi_moved_to_another_issuer_shows_only_to_the_new_group(self):
        station = self.create("0-756-0-uc3", self.admin)
        self.update(station, record("0-76-0-uc3"), self.admin)
        self.assertEqual(self.seen(self.foreigner), ["0-76-0-uc3"])
        self.assertEqual(self.seen(self.colleague), [])

    def test_an_additional_wsi_of_another_issuer_needs_both_groups(self):
        both = self.user("uc_both", 756, 76)
        data = record("0-756-0-uc4")
        data["properties"]["additionalIds"] = ["0-76-0-uc4"]
        self.create_record(data, both)
        self.assertEqual(self.seen(both), ["0-756-0-uc4"])
        self.assertEqual(self.seen(self.colleague), [])
        self.assertEqual(self.seen(self.foreigner), [])

    def test_leaving_the_group_takes_the_station_away(self):
        self.create("0-756-0-uc5")
        self.colleague.groups.clear()
        self.assertEqual(self.seen(self.colleague), [])

    def test_a_station_never_queued_isnt_listed(self):
        station = self.create("0-756-0-uc6")
        self.set_status(station, "")
        self.assertEqual(self.seen(), [])
        self.assertEqual(self.retry(station).status_code, 404)

    def test_latest_version_first(self):
        self.create("0-756-0-old", updated="2026-11-01T10:00:00Z")
        self.create("0-756-0-new", updated="2026-11-03T10:00:00Z")
        self.create("0-756-0-mid", updated="2026-11-02T10:00:00Z")
        self.assertEqual(self.seen(), ["0-756-0-new", "0-756-0-mid", "0-756-0-old"])

    def test_the_status_filter_is_how_failures_are_counted(self):
        failed = self.create("0-756-0-uc7")
        self.create("0-756-0-uc8")
        self.set_status(failed, Status.FAILED)
        self.assertEqual(self.seen(status="failed"), ["0-756-0-uc7"])

        self.client.force_authenticate(self.author)
        body = self.client.get(reverse("publications"), {"status": "failed", "limit": 1}).json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(self.seen(self.foreigner, status="failed"), [])

    def test_is_paginated(self):
        for i in range(3):
            self.create(f"0-756-0-page{i}")
        self.client.force_authenticate(self.author)
        body = self.client.get(reverse("publications"), {"limit": 2}).json()
        self.assertEqual((body["count"], len(body["results"])), (3, 2))
        self.assertIsNotNone(body["next"])

    def saved_failure(self, station):
        state.save(station.pk, {
            "deliveries": [
                {"publisher": "wis2", "step": "storage", "name": "f", "media_type": "t", "topic": None,
                 "url": "https://public/f", "internal_url": "http://minio:9000/secret/f"},
                {"publisher": "wis2", "step": "wnm", "name": None, "media_type": "t", "topic": None,
                 "url": None, "internal_url": None},
            ],
            "leftovers": [],
            "error": "wis2:wnm: broker down",
            "finished_at": "2026-11-05T10:00:05+00:00",
        })

    def test_a_row_says_who_and_what_without_internals(self):
        station = self.create("0-756-0-uc9", updated="2026-11-05T10:00:00Z", title="Ninth")
        self.update(station, record("0-756-0-uc9", updated="2026-11-05T10:00:00Z", title="Ninth"), self.colleague)
        self.set_status(station, Status.FAILED)
        self.saved_failure(station)

        [row] = self.listed()

        self.assertEqual(row, {
            "station_id": station.pk,
            "wigos_identifier": "0-756-0-uc9",
            "name": "Ninth",
            "status": "failed",
            "updated": "2026-11-05T10:00:00Z",
            "changed_by": "uc_colleague",
            "finished_at": "2026-11-05T10:00:05+00:00",
            "last_error": "wis2:wnm: broker down",
            "files": ["https://public/f"],
            "can_retry": True,
        })
        self.assertNotIn("minio", json.dumps(row))

    def test_a_newer_save_hides_the_old_error_but_keeps_the_files(self):
        station = self.create("0-756-0-uc10")
        self.saved_failure(station)

        [row] = self.listed()

        self.assertEqual((row["status"], row["last_error"], row["finished_at"]), ("pending", "", None))
        self.assertEqual(row["files"], ["https://public/f"])

    def test_an_administrators_change_shows_no_user_name(self):
        self.create("0-756-0-uc11", self.admin)
        [row] = self.listed(self.colleague)
        self.assertIsNone(row["changed_by"])

    def test_the_list_works_without_valkey(self):
        station = self.create("0-756-0-uc12")
        self.set_status(station, Status.FAILED)
        with mock.patch.object(self.valkey, "mget", side_effect=redis.ConnectionError("down")):
            with self.assertLogs("publishing", "ERROR"):
                [row] = self.listed()
        self.assertEqual((row["status"], row["last_error"], row["files"]), ("failed", "", []))

    def test_only_a_processed_station_cant_be_retried(self):
        rows = {}
        for status in (Status.PENDING, Status.PROCESSING, Status.FAILED, Status.PROCESSED):
            station = self.create(f"0-756-0-{status}")
            self.set_status(station, status)
            rows[status] = station
        flags = {row["status"]: row["can_retry"] for row in self.listed()}
        self.assertEqual(flags, {"pending": True, "processing": True, "failed": True, "processed": False})

        response = self.retry(rows[Status.PROCESSED])
        self.assertEqual(response.status_code, 409)
        self.assertIn("already published", response.json()["detail"])
        self.assertEqual(self.status_of(rows[Status.PROCESSED]), Status.PROCESSED)
        self.delay.assert_not_called()

        for status in (Status.PENDING, Status.PROCESSING, Status.FAILED):
            self.assertEqual(self.retry(rows[status]).status_code, 200, status)
            self.assertEqual(self.status_of(rows[status]), Status.PENDING)
            self.delay.assert_called_with(rows[status].pk)

    def test_a_colleague_can_retry_but_someone_who_cant_edit_cant(self):
        station = self.create("0-756-0-uc13")
        self.set_status(station, Status.FAILED)

        for user in (self.foreigner, self.outsider):
            self.assertEqual(self.retry(station, user).status_code, 404, user.username)
        self.assertEqual(self.status_of(station), Status.FAILED)
        self.delay.assert_not_called()

        response = self.retry(station, self.colleague)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "pending")

    def test_superusers_can_retry_anything(self):
        station = self.create("0-756-0-uc14")
        self.set_status(station, Status.FAILED)
        self.assertEqual(self.retry(station, self.admin).status_code, 200)

    def test_a_station_that_doesnt_exist_is_not_found(self):
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(reverse("publication-retry", args=[999999])).status_code, 404)

    def test_only_post_retries(self):
        station = self.create("0-756-0-uc15")
        self.client.force_authenticate(self.author)
        self.assertEqual(self.client.get(reverse("publication-retry", args=[station.pk])).status_code, 405)

    def test_a_retry_while_locked_is_refused(self):
        station = self.create("0-756-0-uc16")
        self.set_status(station, Status.PROCESSING)
        self.assertTrue(state.station_lock(station.pk).acquire())

        response = self.retry(station)

        self.assertEqual(response.status_code, 409)
        self.assertIn("may still be running", response.json()["detail"])
        self.assertEqual(self.status_of(station), Status.PROCESSING)
        self.delay.assert_not_called()

    def test_a_retry_without_valkey_says_so_and_changes_nothing(self):
        station = self.create("0-756-0-uc17")
        self.set_status(station, Status.FAILED)
        with mock.patch.object(state, "is_locked", side_effect=redis.ConnectionError("down")):
            with self.assertLogs("publishing", "ERROR"):
                response = self.retry(station)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.status_of(station), Status.FAILED)

    def test_a_retry_that_cant_enqueue_says_so_and_can_be_retried(self):
        station = self.create("0-756-0-uc18")
        self.set_status(station, Status.FAILED)
        self.delay.side_effect = OperationalError("down")
        with self.assertLogs("publishing", "ERROR"):
            self.assertEqual(self.retry(station).status_code, 503)
        self.assertEqual(self.status_of(station), Status.PENDING)

        self.delay.side_effect = None
        self.assertEqual(self.retry(station).status_code, 200)

    def test_my_stations_gives_the_status_only_to_those_who_can_edit(self):
        station = self.create("0-756-0-uc19")
        self.set_status(station, Status.FAILED)

        def status_for(user):
            self.client.force_authenticate(user)
            stations_listed = self.client.get(reverse("my_stations")).json()
            return {s["station_id"]: s["publication_status"] for s in stations_listed}[station.pk]

        self.assertEqual(status_for(self.colleague), "failed")
        self.assertIsNone(status_for(self.foreigner))

    def test_a_real_login_session_works_the_way_the_frontend_uses_it(self):
        station = self.create("0-756-0-uc20")
        self.set_status(station, Status.FAILED)
        retry = reverse("publication-retry", args=[station.pk])
        browser = Client(enforce_csrf_checks=True)

        self.assertEqual(browser.get(reverse("publications")).status_code, 403)  # not logged in yet

        browser.get(reverse("auth-csrf"))
        login = browser.post(
            reverse("auth-login"), {"username": "uc_colleague", "password": "pw"}, content_type="application/json"
        )
        self.assertEqual(login.status_code, 200, login.content)
        browser.get(reverse("auth-csrf"))  # login rotates the token

        [listed] = browser.get(reverse("publications")).json()["results"]
        self.assertEqual((listed["station_id"], listed["can_retry"]), (station.pk, True))

        self.assertEqual(browser.post(retry).status_code, 403)  # no CSRF token
        self.assertEqual(self.status_of(station), Status.FAILED)

        answer = browser.post(retry, HTTP_X_CSRFTOKEN=browser.cookies["csrftoken"].value)
        self.assertEqual(answer.status_code, 200, answer.content)
        self.assertEqual(answer.json()["status"], "pending")
