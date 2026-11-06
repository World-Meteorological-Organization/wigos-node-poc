import unittest
from types import SimpleNamespace
from unittest import mock

import paho.mqtt.client as paho

from publishing.base import Location, Message, PublishError
from publishing.registry import ConfigurationError, build_publishers
from publishing.transports import mqtt
from publishing.transports.mqtt import MQTTTransport

SUCCESS = SimpleNamespace(is_failure=False)
REFUSED = SimpleNamespace(is_failure=True)


class FakeInfo:
    def __init__(self, rc=paho.MQTT_ERR_SUCCESS, published=True):
        self.rc = rc
        self.published = published
        self.waited = None

    def wait_for_publish(self, timeout=None):
        self.waited = timeout

    def is_published(self):
        return self.published


class FakeClient:
    """Connects as soon as the loop starts, unless told not to."""

    def __init__(self, api_version):
        self.api_version = api_version
        self.credentials = None
        self.tls = False
        self.connects = True
        self.calls = []
        self.published = []
        self.infos = []

    def username_pw_set(self, username, password):
        self.credentials = (username, password)

    def tls_set(self):
        self.tls = True

    def connect_async(self, host, port):
        self.calls.append(("connect_async", host, port))

    def loop_start(self):
        self.calls.append("loop_start")
        if self.connects:
            self.on_connect(self, None, {}, SUCCESS, None)

    def loop_stop(self):
        self.calls.append("loop_stop")

    def disconnect(self):
        self.calls.append("disconnect")

    def publish(self, topic, payload, qos):
        self.published.append((topic, payload, qos))
        info = self.infos.pop(0) if self.infos else FakeInfo()
        if isinstance(info, Exception):
            raise info
        return info


def transport(url="mqtt://broker:1883", **options):
    with mock.patch.object(mqtt.mqtt, "Client", FakeClient):
        return MQTTTransport(url=url, **{"topic": "origin/a/test", **options})


def opened(*args, **kwargs):
    t = transport(*args, **kwargs)
    t.open()
    return t


MESSAGE = Message(body=b'{"id":"wnm"}', media_type="application/geo+json")


class MQTTTransportTestCase(unittest.TestCase):
    def test_url_gives_host_port_and_credentials(self):
        t = transport("mqtt://us%40er:p%2Fss@broker:1884")
        self.assertEqual((t.host, t.port, t.client.credentials), ("broker", 1884, ("us@er", "p/ss")))
        self.assertFalse(t.client.tls)
        self.assertNotIn("url", t.options)

    def test_mqtts_uses_tls_and_its_default_port(self):
        t = transport("mqtts://broker")
        self.assertEqual(t.port, 8883)
        self.assertTrue(t.client.tls)

    def test_a_bad_url_is_a_configuration_error_without_the_password(self):
        with self.assertRaises(ConfigurationError) as caught:
            build_publishers([{
                "NAME": "wnm",
                "STEPS": [{
                    "NAME": "send",
                    "GENERATOR": {"CLASS": "publishing.generators.wmdr2.RecordFileGenerator",
                                  "OPTIONS": {"centre_id": "c"}},
                    "TRANSPORT": {"CLASS": "publishing.transports.mqtt.MQTTTransport",
                                  "OPTIONS": {"url": "http://user:secret@broker"}},
                }],
            }])
        self.assertIn("url must look like", caught.exception.errors[0])
        self.assertNotIn("secret", caught.exception.errors[0])

    def test_creating_it_makes_no_connection(self):
        self.assertEqual(transport().client.calls, [])

    def test_open_and_close_run_the_network_thread(self):
        t = opened()
        t.close()
        self.assertEqual(t.client.calls, [("connect_async", "broker", 1883), "loop_start", "disconnect", "loop_stop"])

    def test_publishes_with_qos_1_to_the_default_topic(self):
        t = opened()
        self.assertIsNone(t.send(MESSAGE))
        self.assertEqual(t.client.published, [("origin/a/test", MESSAGE.body, 1)])

    def test_a_messages_own_topic_wins(self):
        t = opened()
        t.send(Message(b"x", "text/plain", topic="own/topic"))
        self.assertEqual(t.client.published[0][0], "own/topic")

    def test_a_message_needs_a_topic(self):
        t = opened(topic=None)
        with self.assertRaises(PublishError):
            t.send(MESSAGE)

    def test_does_not_wait_for_the_brokers_acknowledgement(self):
        t = opened()
        info = FakeInfo(published=False)
        t.client.infos = [info]
        self.assertIsNone(t.send(MESSAGE))
        self.assertIsNone(info.waited)

    def test_nothing_is_handed_to_the_client_while_disconnected(self):
        t = transport(timeout=0.01)
        t.client.connects = False
        t.open()
        with self.assertRaises(PublishError):
            t.send(MESSAGE)
        self.assertEqual(t.client.published, [])

    def test_a_lost_connection_stops_publishing_until_it_is_back(self):
        t = opened(timeout=0.01)
        with self.assertLogs("publishing", "WARNING"):
            t.client.on_disconnect(t.client, None, {}, "broker gone", None)
        with self.assertRaises(PublishError) as caught:
            t.send(MESSAGE)
        self.assertIn("broker gone", str(caught.exception))
        self.assertEqual(t.client.published, [])
        t.client.on_connect(t.client, None, {}, SUCCESS, None)
        t.send(MESSAGE)
        self.assertEqual(len(t.client.published), 1)

    def test_a_refused_connection_keeps_its_reason(self):
        t = transport(timeout=0.01)
        t.client.connects = False
        t.open()
        with self.assertLogs("publishing", "ERROR"):
            t.client.on_connect(t.client, None, {}, REFUSED, None)
        with self.assertLogs("publishing", "WARNING"):
            t.client.on_disconnect(t.client, None, {}, "closed", None)  # follows a refusal
        with self.assertRaises(PublishError) as caught:
            t.send(MESSAGE)
        self.assertIn("connection refused", str(caught.exception))

    def test_publish_errors_are_publish_errors(self):
        t = opened()
        for rc in (paho.MQTT_ERR_QUEUE_SIZE, paho.MQTT_ERR_NO_CONN):
            t.client.infos = [FakeInfo(rc=rc)]
            with self.assertRaises(PublishError):
                t.send(MESSAGE)
        t.client.infos = [ValueError("Publish topic cannot contain wildcards.")]
        with self.assertRaises(PublishError):
            t.send(MESSAGE)

    def test_nothing_to_remove(self):
        transport().remove(Location("http://x"))
