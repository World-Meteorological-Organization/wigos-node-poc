import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from publishing.base import (
    DefaultPublisher,
    Delivery,
    Event,
    Location,
    Message,
    MessageGenerator,
    Operation,
    Publisher,
    PublishError,
    Step,
    TransportLayer,
)


def one_step(generator, transport, name="main"):
    return [Step(name, generator, transport)]


def make_event(operation=Operation.CREATE, **fields):
    values = {
        "operation": operation,
        "station_id": 7,
        "wigos_identifier": "0-20000-0-12345",
        "wmdrv2": {"id": "0-20000-0-12345"},
        "occurred_at": datetime(2026, 10, 28, tzinfo=timezone.utc),
    }
    values.update(fields)
    return Event(**values)


class EchoGenerator(MessageGenerator):
    """One message per event, carrying the operation; none on DELETE."""

    def generate(self, event, deliveries):
        if event.operation == Operation.DELETE:
            return []
        return [Message(body=event.operation.encode(), media_type="text/plain", name=event.wigos_identifier)]


class ContentGenerator(MessageGenerator):
    """Echoes the retrieved content of the earlier deliveries."""

    def needs_content(self, event):
        return True

    def generate(self, event, deliveries):
        self.seen = deliveries
        return [Message(body=d.content, media_type="text/plain") for d in deliveries if d.content is not None]


class RecordingTransport(TransportLayer):
    """Remembers what it sent; reports named messages as stored at
    <url>/<name> when given a url option."""

    def __init__(self, **options):
        super().__init__(**options)
        self.sent = []
        self.opened = self.closed = False

    def open(self):
        self.opened = True

    def close(self):
        self.closed = True

    def send(self, message):
        self.sent.append(message)
        if self.options.get("url") and message.name:
            return Location(f"{self.options['url']}/{message.name}")
        return None

    def remove(self, location):
        self.removed = getattr(self, "removed", []) + [location.url]


class CreatesOnlyPublisher(Publisher):
    def should_publish(self, event):
        return event.operation == Operation.CREATE


class FakeRetrievalPublisher(DefaultPublisher):
    """Serves retrievals from a dict instead of the network."""

    def __init__(self, *args, files, **kwargs):
        super().__init__(*args, **kwargs)
        self.files = files
        self.retrieved = []

    def retrieve(self, location):
        self.retrieved.append(location.retrieve_url)
        return self.files[location.retrieve_url]


class PublisherTestCase(unittest.TestCase):
    def setUp(self):
        self.transport = RecordingTransport()
        self.publisher = DefaultPublisher("echo", one_step(EchoGenerator(), self.transport))

    def test_publish_sends_generated_messages(self):
        self.publisher.publish(make_event(Operation.UPDATE))
        self.assertEqual([m.body for m in self.transport.sent], [b"update"])
        self.assertEqual(self.transport.sent[0].name, "0-20000-0-12345")

    def test_generator_returning_nothing_sends_nothing(self):
        self.assertEqual(self.publisher.publish(make_event(Operation.DELETE)), [])
        self.assertEqual(self.transport.sent, [])

    def test_should_publish_filters_events(self):
        publisher = CreatesOnlyPublisher("creates", one_step(EchoGenerator(), self.transport))
        self.assertEqual(publisher.publish(make_event(Operation.UPDATE)), [])
        publisher.publish(make_event(Operation.CREATE))
        self.assertEqual([m.body for m in self.transport.sent], [b"create"])

    def test_open_and_close_reach_the_transport(self):
        self.publisher.open()
        self.publisher.close()
        self.assertTrue(self.transport.opened)
        self.assertTrue(self.transport.closed)

    def test_send_many_keeps_order(self):
        messages = [Message(body=str(i).encode(), media_type="text/plain") for i in range(3)]
        self.assertEqual(self.transport.send_many(messages), [None, None, None])
        self.assertEqual(self.transport.sent, messages)

    def test_options_are_kept(self):
        self.assertEqual(RecordingTransport(topic="a/b").options, {"topic": "a/b"})

    def test_publisher_without_should_publish_is_abstract(self):
        class Incomplete(Publisher):
            pass

        with self.assertRaises(TypeError):
            Incomplete("x", EchoGenerator(), self.transport)


class DeliveryTestCase(unittest.TestCase):
    def test_publish_returns_receipts_with_locations(self):
        publisher = DefaultPublisher("files", one_step(EchoGenerator(), RecordingTransport(url="http://store")))
        [delivery] = publisher.publish(make_event())
        self.assertEqual(delivery.publisher, "files")
        self.assertEqual(delivery.message.body, b"create")
        self.assertEqual(delivery.location, Location("http://store/0-20000-0-12345"))
        self.assertIsNone(delivery.content)

    def test_notification_receipts_have_no_location(self):
        [delivery] = DefaultPublisher("note", one_step(EchoGenerator(), RecordingTransport())).publish(make_event())
        self.assertIsNone(delivery.location)

    def test_generator_gets_the_retrieved_file_not_the_sent_body(self):
        sent = Message(body=b"as sent", media_type="text/plain", name="f")
        earlier = [
            Delivery("files", sent, Location("https://public/f", "http://internal/f")),
            Delivery("note", Message(body=b"no file", media_type="text/plain")),
        ]
        generator = ContentGenerator()
        publisher = FakeRetrievalPublisher(
            "check", one_step(generator, RecordingTransport()), files={"http://internal/f": b"as stored"}
        )
        publisher.run_step(publisher.steps[0], make_event(), earlier)
        self.assertEqual(publisher.retrieved, ["http://internal/f"])
        self.assertEqual([d.content for d in generator.seen], [b"as stored", None])
        self.assertEqual([m.body for m in publisher.steps[0].transport.sent], [b"as stored"])

    def test_nothing_is_retrieved_unless_needed(self):
        publisher = FakeRetrievalPublisher("echo", one_step(EchoGenerator(), RecordingTransport()), files={})
        publisher.run_step(
            publisher.steps[0], make_event(), [Delivery("files", Message(b"x", "text/plain"), Location("http://f"))]
        )
        self.assertEqual(publisher.retrieved, [])

    def test_a_generator_relying_on_a_read_back_body_fails_instead_of_sending_nothing(self):
        class Mirror(MessageGenerator):
            def generate(self, event, deliveries):
                return [Message(d.message.body, "text/plain") for d in deliveries]

        transport = RecordingTransport()
        publisher = DefaultPublisher("mirror", one_step(Mirror(), transport))
        read_back = Delivery("files", Message(None, "text/plain"), Location("http://f"))

        with self.assertRaisesRegex(PublishError, "without a body"):
            publisher.run_step(publisher.steps[0], make_event(), [read_back])
        self.assertEqual(transport.sent, [])

    def test_retrieve_reads_the_internal_url(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "record.json")
            path.write_bytes(b'{"stored":true}')
            location = Location("https://public.example/record.json", path.as_uri())
            self.assertEqual(Location("u").retrieve_url, "u")
            publisher = DefaultPublisher("check", one_step(ContentGenerator(), RecordingTransport()))
            self.assertEqual(publisher.retrieve(location), b'{"stored":true}')

    def test_undo_removes_only_this_publishers_stored_deliveries_newest_first(self):
        transport = RecordingTransport()
        publisher = DefaultPublisher("files", one_step(EchoGenerator(), transport))
        body = Message(b"x", "text/plain")
        publisher.undo(make_event(), [
            Delivery("files", body, Location("http://store/a"), step="main"),
            Delivery("other", body, Location("http://store/other"), step="main"),
            Delivery("files", body, step="main"),  # nothing stored
            Delivery("files", body, Location("http://store/b"), step="main"),
        ])
        self.assertEqual(transport.removed, ["http://store/b", "http://store/a"])

    def test_default_remove_does_nothing(self):
        class NotificationTransport(TransportLayer):
            def send(self, message):
                return None

        publisher = DefaultPublisher("note", one_step(EchoGenerator(), NotificationTransport()))
        publisher.undo(make_event(), [Delivery("note", Message(b"x", "text/plain"), Location("http://x"), step="main")])

    def test_undo_errors_reach_the_caller(self):
        class BrokenRemove(RecordingTransport):
            def remove(self, location):
                raise PublishError("storage down")

        publisher = DefaultPublisher("files", one_step(EchoGenerator(), BrokenRemove()))
        with self.assertRaises(PublishError):
            publisher.undo(make_event(), [Delivery("files", Message(b"x", "text/plain"), Location("http://x"), step="main")])

    def test_failed_retrieval_raises_publish_error(self):
        publisher = DefaultPublisher("check", one_step(ContentGenerator(), RecordingTransport()))
        with self.assertRaises(PublishError):
            publisher.retrieve(Location("file:///nonexistent/record.json"))
        with self.assertRaises(PublishError):
            publisher.retrieve(Location("not a url"))


class StepsTestCase(unittest.TestCase):
    """A publisher pipes its own steps, from start to end."""

    def setUp(self):
        self.storage = RecordingTransport(url="http://store")
        self.notes = RecordingTransport()
        self.generator = ContentGenerator()
        self.publisher = FakeRetrievalPublisher(
            "pipe",
            [Step("store", EchoGenerator(), self.storage), Step("note", self.generator, self.notes)],
            files={"http://store/0-20000-0-12345": b"as stored"},
        )

    def test_each_step_gets_the_receipts_of_the_steps_before_it(self):
        store, note = self.publisher.publish(make_event())
        self.assertEqual((store.publisher, store.step), ("pipe", "store"))
        self.assertEqual((note.publisher, note.step), ("pipe", "note"))
        self.assertEqual([m.body for m in self.notes.sent], [b"as stored"])

    def test_open_and_close_reach_every_transport(self):
        self.publisher.open()
        self.publisher.close()
        self.assertTrue(self.storage.opened and self.storage.closed and self.notes.opened and self.notes.closed)

    def test_on_step_reports_the_progress_after_each_step(self):
        seen = []
        self.publisher.publish(make_event(), on_step=lambda step, receipts: seen.append((step.name, len(receipts))))
        self.assertEqual(seen, [("store", 1), ("note", 2)])

    def test_a_failing_step_stops_the_later_ones(self):
        self.publisher.retrieve = mock.Mock(side_effect=PublishError("storage down"))
        with self.assertRaises(PublishError):
            self.publisher.publish(make_event())
        self.assertEqual(self.notes.sent, [])

    def test_only_a_deletion_is_given_the_previous_receipts(self):
        previous = [Delivery("pipe", Message(b"", "text/plain"), Location("http://store/old"), step="store")]
        self.publisher.files["http://store/old"] = b"old"

        self.publisher.publish(make_event(Operation.DELETE), previous=previous)
        self.assertEqual([d.location.url for d in self.generator.seen], ["http://store/old"])

        self.publisher.publish(make_event(Operation.UPDATE), previous=previous)
        self.assertNotIn("http://store/old", [d.location.url for d in self.generator.seen])

    def test_undo_uses_the_transport_of_the_step_that_stored_it(self):
        other = RecordingTransport()
        publisher = DefaultPublisher("pipe", [Step("a", EchoGenerator(), self.storage), Step("b", EchoGenerator(), other)])
        body = Message(b"x", "text/plain")
        publisher.undo(make_event(), [
            Delivery("pipe", body, Location("http://a"), step="a"),
            Delivery("pipe", body, Location("http://b"), step="b"),
        ])
        self.assertEqual((self.storage.removed, other.removed), (["http://a"], ["http://b"]))

    def test_undo_of_an_unknown_step_is_an_error(self):
        with self.assertRaises(KeyError):  # recorded by the worker
            self.publisher.undo(make_event(), [Delivery("pipe", Message(b"x", "t"), Location("http://a"), step="gone")])
