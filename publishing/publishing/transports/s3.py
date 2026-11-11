import io
import json
import threading
from urllib.parse import quote, unquote

import urllib3
from minio import Minio
from minio.error import MinioException

from ..base import Location, PublishError, TransportLayer


def public_read_policy(bucket):
    """Anonymous download of the bucket's objects (no listing)."""
    return json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"AWS": ["*"]},
            "Action": ["s3:GetObject"],
            "Resource": [f"arn:aws:s3:::{bucket}/*"],
        }],
    })


class S3Transport(TransportLayer):
    """Stores each message as an object in an S3-compatible bucket (MinIO,
    AWS S3, ...), named by the message's name. put_object is all or nothing:
    an object appears complete or not at all.

    Options: endpoint (host:port), bucket, access_key, secret_key, secure
    (TLS, default True), region, prefix (prepended to object names),
    public_url (base URL the objects are served at, used in the WNM; default
    <endpoint>/<bucket>), create_bucket (default False: for development,
    create a missing bucket with anonymous read on the first send) and
    timeout (seconds per request, default 30; with the retries a call
    gives up well within the job's lock, unlike the client's default)."""

    def __init__(self, *, endpoint, bucket, access_key=None, secret_key=None, secure=True, region=None,
                 prefix="", public_url=None, create_bucket=False, timeout=30, **options):
        super().__init__(
            endpoint=endpoint, bucket=bucket, secure=secure, region=region, prefix=prefix,
            public_url=public_url, create_bucket=create_bucket, timeout=timeout, **options,
        )  # the credentials are kept out of self.options
        self.bucket = bucket
        self.prefix = prefix
        self.public_url = (public_url or f"{'https' if secure else 'http'}://{endpoint}/{bucket}").rstrip("/")
        self.create_bucket = create_bucket
        # connects on use, so open() can't fail on the network
        http_client = urllib3.PoolManager(
            timeout=urllib3.Timeout(connect=min(timeout, 5), read=timeout),
            retries=urllib3.Retry(total=2, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504]),
        )
        self.client = Minio(
            endpoint, access_key=access_key, secret_key=secret_key, secure=secure, region=region,
            http_client=http_client,
        )
        self._bucket_ready = not create_bucket
        self._bucket_lock = threading.Lock()

    def _call(self, action, *args, **kwargs):
        try:
            return action(*args, **kwargs)
        except (MinioException, urllib3.exceptions.HTTPError, OSError, ValueError) as e:
            raise PublishError(f"{action.__name__} on bucket {self.bucket}: {e}") from e

    def _ensure_bucket(self):
        with self._bucket_lock:
            if self._bucket_ready:
                return
            if not self._call(self.client.bucket_exists, bucket_name=self.bucket):
                self._call(self.client.make_bucket, bucket_name=self.bucket)
                self._call(self.client.set_bucket_policy, bucket_name=self.bucket, policy=public_read_policy(self.bucket))
            self._bucket_ready = True

    def send(self, message):
        if not message.name:
            raise PublishError("S3Transport stores named messages only")
        self._ensure_bucket()
        object_name = self.prefix + message.name
        self._call(
            self.client.put_object,
            bucket_name=self.bucket,
            object_name=object_name,
            data=io.BytesIO(message.body),
            length=len(message.body),
            content_type=message.media_type,
        )
        return Location(f"{self.public_url}/{quote(object_name)}")

    def remove(self, location):
        base = f"{self.public_url}/"
        if not location.url.startswith(base):
            raise PublishError(f"{location.url} is not in bucket {self.bucket}")
        # removing an object that is already gone is not an error in S3
        self._call(self.client.remove_object, bucket_name=self.bucket, object_name=unquote(location.url[len(base):]))
