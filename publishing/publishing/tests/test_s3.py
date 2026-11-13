import json
import unittest
from unittest import mock

import urllib3
from minio.error import S3Error

from publishing.base import Location, Message, PublishError
from publishing.transports import s3
from publishing.transports.s3 import S3Transport


class FakeMinio:
    """The few Minio client calls S3Transport makes, kept in memory."""

    def __init__(self, endpoint, **kwargs):
        self.endpoint = endpoint
        self.kwargs = kwargs
        self.buckets = {}  # name -> policy
        self.objects = {}  # (bucket, name) -> (body, content type)
        self.calls = []
        self.fail = None

    def _record(self, call):
        self.calls.append(call)
        if self.fail:
            raise self.fail

    def bucket_exists(self, *, bucket_name):
        self._record("bucket_exists")
        return bucket_name in self.buckets

    def make_bucket(self, *, bucket_name):
        self._record("make_bucket")
        self.buckets[bucket_name] = None

    def set_bucket_policy(self, *, bucket_name, policy):
        self._record("set_bucket_policy")
        self.buckets[bucket_name] = json.loads(policy)

    def put_object(self, *, bucket_name, object_name, data, length, content_type):
        self._record("put_object")
        body = data.read()
        assert len(body) == length
        self.objects[bucket_name, object_name] = (body, content_type)

    def remove_object(self, *, bucket_name, object_name):
        self._record("remove_object")
        self.objects.pop((bucket_name, object_name), None)


def transport(**options):
    with mock.patch.object(s3, "Minio", FakeMinio):
        return S3Transport(**{"endpoint": "minio:9000", "bucket": "webstorage", **options})


MESSAGE = Message(body=b'{"id":"0-1-2-3"}', media_type="application/geo+json", name="wmdr2 a.json")


class S3TransportTestCase(unittest.TestCase):
    def test_stores_the_message_and_reports_its_public_url(self):
        t = transport(public_url="https://node.example/webstorage/")

        location = t.send(MESSAGE)

        self.assertEqual(t.client.objects, {("webstorage", "wmdr2 a.json"): (MESSAGE.body, "application/geo+json")})
        self.assertEqual(location, Location("https://node.example/webstorage/wmdr2%20a.json"))

    def test_url_defaults_to_the_endpoint_and_bucket(self):
        self.assertEqual(transport().send(MESSAGE).url, "https://minio:9000/webstorage/wmdr2%20a.json")
        self.assertEqual(transport(secure=False).send(MESSAGE).url, "http://minio:9000/webstorage/wmdr2%20a.json")

    def test_prefix_is_part_of_the_object_name(self):
        t = transport(prefix="wmdr2/")
        location = t.send(MESSAGE)
        self.assertIn(("webstorage", "wmdr2/wmdr2 a.json"), t.client.objects)
        self.assertEqual(location.url, "https://minio:9000/webstorage/wmdr2/wmdr2%20a.json")

    def test_client_gets_the_credentials_but_options_dont(self):
        t = transport(access_key="key", secret_key="secret", secure=False, region="eu", timeout=7)
        http_client = t.client.kwargs.pop("http_client")
        self.assertEqual(t.client.kwargs, {"access_key": "key", "secret_key": "secret", "secure": False, "region": "eu"})
        self.assertNotIn("secret_key", t.options)
        self.assertEqual(http_client.connection_pool_kw["timeout"].read_timeout, 7)

    def test_storage_errors_become_publish_errors(self):
        t = transport()
        for error in (
            S3Error("AccessDenied", "denied", "", "", "", None),
            ConnectionRefusedError("minio is down"),
            urllib3.exceptions.MaxRetryError(None, "/", "gave up"),
        ):
            t.client.fail = error
            with self.assertRaises(PublishError):
                t.send(MESSAGE)

    def test_unnamed_messages_are_refused(self):
        with self.assertRaises(PublishError):
            transport().send(Message(b"{}", "application/json"))

    def test_remove_deletes_the_stored_object(self):
        t = transport(prefix="p/")
        location = t.send(MESSAGE)
        t.remove(location)
        self.assertEqual(t.client.objects, {})
        t.remove(location)  # already gone: fine

    def test_remove_refuses_urls_outside_the_bucket(self):
        with self.assertRaises(PublishError):
            transport().remove(Location("https://elsewhere.example/file.json"))

    def test_create_bucket_makes_a_missing_bucket_publicly_readable_once(self):
        t = transport(create_bucket=True)

        t.send(MESSAGE)
        t.send(MESSAGE)

        [statement] = t.client.buckets["webstorage"]["Statement"]
        self.assertEqual((statement["Action"], statement["Resource"]), (["s3:GetObject"], ["arn:aws:s3:::webstorage/*"]))
        self.assertEqual(t.client.calls, ["bucket_exists", "make_bucket", "set_bucket_policy", "put_object", "put_object"])

    def test_create_bucket_leaves_an_existing_bucket_alone(self):
        t = transport(create_bucket=True)
        t.client.buckets["webstorage"] = "own policy"
        t.send(MESSAGE)
        self.assertEqual(t.client.buckets["webstorage"], "own policy")

    def test_without_create_bucket_the_bucket_is_not_checked(self):
        t = transport()
        t.send(MESSAGE)
        self.assertEqual(t.client.calls, ["put_object"])

    def test_a_failed_bucket_check_is_retried_on_the_next_send(self):
        t = transport(create_bucket=True)
        t.client.fail = ConnectionRefusedError("starting")
        with self.assertRaises(PublishError):
            t.send(MESSAGE)
        t.client.fail = None
        t.send(MESSAGE)
        self.assertIn("make_bucket", t.client.calls)
