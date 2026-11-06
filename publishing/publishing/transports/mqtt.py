import logging
import threading
from urllib.parse import unquote, urlsplit

import paho.mqtt.client as mqtt

from ..base import PublishError, TransportLayer

logger = logging.getLogger("publishing")

DEFAULT_PORTS = {"mqtt": 1883, "mqtts": 8883}


class MQTTTransport(TransportLayer):
    """Publishes each message to an MQTT broker at QoS 1, as wis2box does: it
    doesn't wait for the broker's acknowledgement. The real confirmation is
    the message coming back on our own subscription (see the upstream
    confirmation in docs/publishing-plan.md).

    Options: url (mqtt://user:password@host:port, or mqtts:// for TLS), topic
    (default topic; a message's own topic wins), qos (default 1) and timeout
    (seconds to wait for a connection, default 5).

    Each worker process has one client, with its own network thread that also
    reconnects and re-sends what the broker hasn't acknowledged. An
    accepted message can't be recalled, so there is nothing to remove()."""

    def __init__(self, *, url, topic=None, qos=1, timeout=5, **options):
        super().__init__(topic=topic, qos=qos, timeout=timeout, **options)  # the url holds the password
        parts = urlsplit(url)
        if parts.scheme not in DEFAULT_PORTS or not parts.hostname:
            raise ValueError("url must look like mqtt://user:password@host:port or mqtts://...")
        self.host = parts.hostname
        self.port = parts.port or DEFAULT_PORTS[parts.scheme]
        self.topic = topic
        self.qos = qos
        self.timeout = timeout
        self._connected = threading.Event()
        self._last_problem = "not connected yet"
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        if parts.username:
            self.client.username_pw_set(unquote(parts.username), unquote(parts.password or ""))
        if parts.scheme == "mqtts":
            self.client.tls_set()

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            self._last_problem = f"connection refused: {reason_code}"
            logger.error("MQTT broker %s:%s %s", self.host, self.port, self._last_problem)
            return
        self._connected.set()
        logger.info("Connected to MQTT broker %s:%s", self.host, self.port)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        if self._connected.is_set():  # a refused connection also ends here; keep its reason
            self._last_problem = f"disconnected: {reason_code}"
        self._connected.clear()
        logger.warning("MQTT broker %s:%s disconnected: %s", self.host, self.port, reason_code)

    def open(self):
        # connects in the network thread, so a broker that is down at startup
        # only delays publishing
        self.client.connect_async(self.host, self.port)
        self.client.loop_start()

    def close(self):
        self.client.disconnect()
        self.client.loop_stop()

    def send(self, message):
        topic = message.topic or self.topic
        if not topic:
            raise PublishError("MQTTTransport needs a topic")
        # paho would queue a message while disconnected and send it whenever
        # it reconnects, possibly after the event has failed: never hand it one
        if not self._connected.wait(self.timeout):
            raise PublishError(f"MQTT broker {self.host}:{self.port}: {self._last_problem}")
        try:
            info = self.client.publish(topic, message.body, qos=self.qos)
        except ValueError as e:  # e.g. wildcards in the topic
            raise PublishError(f"Could not publish to {topic}: {e}") from e
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise PublishError(f"Could not publish to {topic}: {mqtt.error_string(info.rc)}")
        logger.info("publish topic=%s type=%s size=%d", topic, message.media_type, len(message.body))
        return None
