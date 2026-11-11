import base64
import hashlib
import json
import unittest
import uuid
from datetime import datetime, timezone

from publishing.base import DefaultPublisher, Delivery, Location, Message, Operation, PublishError, Step
from publishing.generators.wmdr2 import RecordFileGenerator
from publishing.generators.wnm import (
    MAX_INLINE_CONTENT_SIZE,
    WNM_CONFORMANCE_CLASS,
    WNMGenerator,
    create_wnm,
)
from publishing.wmdr2 import record_file_name, render_record

from .test_base import RecordingTransport, make_event

RECORD = {
    "id": "0-20000-0-123456",
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [-23, 22]},
    "properties": {"title": "Test station", "updated": "2026-08-07T11:13:00.000Z"},
}
HREF = "https://example.org/webstorage/wmdr2_c_0-20000-0-123456_2026-08-07T11_13_00_000.json"
CONTENT = render_record(RECORD)


def sha512(data):
    return base64.b64encode(hashlib.sha512(data).digest()).decode("ascii")


class CreateWnmTestCase(unittest.TestCase):
    def wnm(self, operation=Operation.CREATE, record=RECORD, content=CONTENT, **kwargs):
        return create_wnm(record, operation, HREF, "io-test", content=content, **kwargs)

    def test_required_properties(self):
        message = self.wnm()

        uuid.UUID(message["id"])
        self.assertEqual(message["type"], "Feature")
        self.assertEqual(message["conformsTo"], [WNM_CONFORMANCE_CLASS])
        self.assertEqual(message["geometry"], {"type": "Point", "coordinates": [-23, 22]})
        uuid.UUID(message["properties"]["data_id"])
        self.assertNotEqual(message["properties"]["data_id"], message["id"])
        self.assertEqual(message["properties"]["metadata_id"], "0-20000-0-123456")
        self.assertEqual(message["properties"]["datetime"], "2026-08-07T11:13:00Z")
        self.assertRegex(message["properties"]["pubtime"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
        self.assertEqual(message["links"], [
            {"href": HREF, "rel": "canonical", "type": "application/geo+json", "length": len(CONTENT)}
        ])

    def test_version_falls_back_to_created(self):
        record = {**RECORD, "properties": {"created": "2026-01-02T03:04:05Z"}}
        self.assertEqual(self.wnm(record=record)["properties"]["datetime"], "2026-01-02T03:04:05Z")

    def test_missing_version_or_identifier_rejected(self):
        with self.assertRaises(ValueError):
            self.wnm(record={**RECORD, "properties": {}})
        with self.assertRaises(ValueError):
            self.wnm(record={k: v for k, v in RECORD.items() if k != "id"})

    def test_integrity_and_content_describe_the_given_file(self):
        stored = b'{"served":"by storage"}'
        properties = self.wnm(content=stored)["properties"]
        self.assertEqual(properties["integrity"], {"method": "sha512", "value": sha512(stored)})
        self.assertEqual(properties["content"], {"encoding": "utf-8", "value": stored.decode(), "size": len(stored)})

    def test_binary_content_is_inlined_as_base64(self):
        stored = b"\x89PNG\r\n\x1a\n\xff"
        content = self.wnm(content=stored)["properties"]["content"]
        self.assertEqual(content, {"encoding": "base64", "value": base64.b64encode(stored).decode(), "size": 9})

    def test_large_file_not_inlined(self):
        properties = self.wnm(content=b"x" * (MAX_INLINE_CONTENT_SIZE + 1))["properties"]
        self.assertNotIn("content", properties)
        self.assertIn("integrity", properties)

    def test_update_and_deletion_links(self):
        self.assertEqual(self.wnm(Operation.UPDATE)["links"][0]["rel"], "update")
        deletion = self.wnm(Operation.DELETE, content=None)
        self.assertEqual(deletion["links"], [{"href": HREF, "rel": "deletion", "type": "application/geo+json"}])
        self.assertNotIn("integrity", deletion["properties"])
        self.assertNotIn("content", deletion["properties"])

    def test_create_and_update_need_content(self):
        with self.assertRaises(ValueError):
            self.wnm(Operation.UPDATE, content=None)

    def test_pubtime(self):
        pubtime = datetime(2026, 10, 21, 12, 30, tzinfo=timezone.utc)
        self.assertEqual(self.wnm(pubtime=pubtime)["properties"]["pubtime"], "2026-10-21T12:30:00Z")

    def test_unknown_operation_rejected(self):
        with self.assertRaises(ValueError):
            self.wnm("replace")


class WNMGeneratorTestCase(unittest.TestCase):
    def setUp(self):
        self.generator = WNMGenerator(centre_id="io-test")
        self.stored = Delivery("wis2-storage", Message(CONTENT, "application/geo+json", name="f.json"), Location(HREF))

    def generate(self, operation, deliveries):
        return [json.loads(m.body) for m in self.generator.generate(make_event(operation, wmdrv2=RECORD), deliveries)]

    def test_announces_each_stored_record_file(self):
        [wnm] = self.generate(Operation.UPDATE, [self.stored])
        self.assertEqual(wnm["links"][0]["href"], HREF)
        self.assertEqual(wnm["links"][0]["rel"], "update")
        self.assertEqual(wnm["properties"]["integrity"]["value"], sha512(CONTENT))

    def test_ignores_deliveries_without_location_or_of_other_types(self):
        other = Delivery("x", Message(b"<a/>", "application/xml", name="a.xml"), Location("https://e/a.xml"))
        note = Delivery("y", Message(b"{}", "application/geo+json"))
        self.assertEqual(len(self.generate(Operation.CREATE, [other, note, self.stored])), 1)

    def test_create_without_stored_file_raises(self):
        with self.assertRaises(PublishError):
            self.generate(Operation.CREATE, [])

    def test_skip_missing_logs_and_sends_nothing(self):
        self.generator = WNMGenerator(centre_id="io-test", skip_missing=True)
        with self.assertLogs("publishing", "WARNING") as logs:
            self.assertEqual(self.generate(Operation.UPDATE, []), [])
        self.assertIn("No stored application/geo+json file", logs.output[0])
        # with a stored file it announces as usual
        self.assertEqual(len(self.generate(Operation.UPDATE, [self.stored])), 1)

    def test_deletion_needs_no_content(self):
        read_back = Delivery("wis2-storage", Message(None, "application/geo+json", name="f.json"), self.stored.location)
        [wnm] = self.generate(Operation.DELETE, [read_back])
        self.assertEqual(wnm["links"][0], {"href": HREF, "rel": "deletion", "type": "application/geo+json"})

    def test_deletion_of_something_never_announced_sends_nothing(self):
        self.assertEqual(self.generate(Operation.DELETE, []), [])

    def test_a_retry_gets_a_new_data_id_but_the_same_pubtime(self):
        first, second = self.generate(Operation.UPDATE, [self.stored]) + self.generate(Operation.UPDATE, [self.stored])
        self.assertNotEqual(first["properties"]["data_id"], second["properties"]["data_id"])
        self.assertEqual(first["properties"]["pubtime"], "2026-10-28T00:00:00Z")  # when the change was made
        self.assertEqual(second["properties"]["pubtime"], first["properties"]["pubtime"])

    def test_message_is_a_geojson_wnm(self):
        [message] = self.generator.generate(make_event(wmdrv2=RECORD), [self.stored])
        self.assertEqual(message.media_type, "application/geo+json")
        self.assertIsNone(message.topic)


class StorageThenWnmTestCase(unittest.TestCase):
    """The steps as configured: the WNM describes the bytes storage was sent."""

    def test_integrity_comes_from_the_stored_bytes(self):
        url = f"http://store/{record_file_name(RECORD, 'io-test')}"
        storage = RecordingTransport(url="http://store")
        notifications = RecordingTransport()
        publisher = DefaultPublisher(
            "wis2",
            [
                Step("storage", RecordFileGenerator(centre_id="io-test"), storage),
                Step("wnm", WNMGenerator(centre_id="io-test"), notifications),
            ],
        )

        publisher.publish(make_event(Operation.CREATE, wmdrv2=RECORD))

        [stored] = storage.sent
        [wnm] = [json.loads(m.body) for m in notifications.sent]
        self.assertEqual(wnm["links"][0]["href"], url)
        self.assertEqual(wnm["links"][0]["length"], len(stored.body))
        self.assertEqual(wnm["properties"]["integrity"]["value"], sha512(stored.body))
