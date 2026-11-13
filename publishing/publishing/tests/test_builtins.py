import json
import unittest

from publishing.base import Location, Message, Operation
from publishing.generators.wmdr2 import RecordFileGenerator
from publishing.transports.log import LogTransport
from publishing.wmdr2 import record_file_name, render_record

from .test_base import make_event

RECORD = {
    "id": "0-20000-0-12345",
    "type": "Feature",
    "properties": {"name": "Zürich 中", "updated": "2026-08-21T16:29:00.000Z"},
    "geometry": {"type": "Point", "coordinates": [8.5, 47.4]},
}


class RenderRecordTestCase(unittest.TestCase):
    def test_compact_utf8_in_given_key_order(self):
        body = render_record({"b": 1, "a": ["é", None]})
        self.assertEqual(body, '{"b":1,"a":["é",null]}'.encode("utf-8"))

    def test_round_trips(self):
        self.assertEqual(json.loads(render_record(RECORD)), RECORD)

    def test_rejects_nan(self):
        with self.assertRaises(ValueError):
            render_record({"x": float("nan")})


class RecordFileNameTestCase(unittest.TestCase):
    def test_uses_centre_wsi_and_updated(self):
        self.assertEqual(
            record_file_name(RECORD, "io-test"),
            "wmdr2_io-test_0-20000-0-12345_2026-08-21T16_29_00_000.json",
        )

    def test_falls_back_to_created(self):
        record = {"id": "0-1-2-3", "properties": {"created": "2026-01-02T03:04:05Z"}}
        self.assertEqual(record_file_name(record, "c"), "wmdr2_c_0-1-2-3_2026-01-02T03_04_05.json")

    def test_needs_id_and_version(self):
        with self.assertRaises(ValueError):
            record_file_name({"properties": {"updated": "2026-01-01T00:00:00Z"}}, "c")
        with self.assertRaises(ValueError):
            record_file_name({"id": "0-1-2-3", "properties": {}}, "c")


class RecordFileGeneratorTestCase(unittest.TestCase):
    def setUp(self):
        self.generator = RecordFileGenerator(centre_id="io-test")

    def test_create_and_update_give_the_record_file(self):
        for operation in (Operation.CREATE, Operation.UPDATE):
            [message] = self.generator.generate(make_event(operation, wmdrv2=RECORD), [])
            self.assertEqual(message.body, render_record(RECORD))
            self.assertEqual(message.media_type, "application/geo+json")
            self.assertEqual(message.name, "wmdr2_io-test_0-20000-0-12345_2026-08-21T16_29_00_000.json")

    def test_delete_gives_nothing(self):
        self.assertEqual(self.generator.generate(make_event(Operation.DELETE, wmdrv2=RECORD), []), [])

    def test_centre_id_is_required(self):
        with self.assertRaisesRegex(TypeError, "centre_id"):
            RecordFileGenerator()


class LogTransportTestCase(unittest.TestCase):
    def test_logs_message_with_default_topic(self):
        transport = LogTransport(topic="origin/a/wis2/x")
        with self.assertLogs("publishing", "INFO") as logs:
            transport.send(Message(body=b'{"a":1}', media_type="application/json", name="f.json"))
        self.assertIn("name=f.json topic=origin/a/wis2/x type=application/json size=7 {\"a\":1}", logs.output[0])

    def test_message_topic_wins_and_body_is_cut(self):
        transport = LogTransport(topic="default", max_body=3)
        with self.assertLogs("publishing", "INFO") as logs:
            transport.send(Message(body=b"abcdef", media_type="text/plain", topic="own"))
        self.assertIn("topic=own", logs.output[0])
        self.assertTrue(logs.output[0].endswith("size=6 abc..."))

    def test_reports_a_location_only_with_url_and_name(self):
        message = Message(body=b"{}", media_type="application/json", name="a b.json")
        with self.assertLogs("publishing", "INFO"):
            self.assertIsNone(LogTransport().send(message))
            self.assertIsNone(LogTransport(url="https://pub/").send(Message(b"{}", "application/json")))
            location = LogTransport(url="https://pub/").send(message)
        self.assertEqual(location, Location("https://pub/a%20b.json"))

    def test_remove_logs(self):
        with self.assertLogs("publishing", "INFO") as logs:
            LogTransport().remove(Location("https://pub/f.json"))
        self.assertIn("remove url=https://pub/f.json", logs.output[0])
