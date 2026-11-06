"""WMDR2 records as published files.

The bytes from render_record() are what web storage holds, and what a WNM's
integrity and content are computed over. Every generator renders through
here, so they always agree."""

import json

MEDIA_TYPE = "application/geo+json"


def render_record(wmdrv2):
    """Compact UTF-8 JSON, keys in the order given."""
    return json.dumps(wmdrv2, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def identity(wmdrv2):
    """(WIGOS identifier, version) of a record, e.g.
    ('0-20000-0-12345', '2026-08-21T16:29:00.000Z'). The version is
    properties.updated, else properties.created."""
    wigos_identifier = wmdrv2.get("id")
    if not wigos_identifier:
        raise ValueError("Missing required field 'id' in wmdrv2 JSON data")
    record_properties = wmdrv2.get("properties") or {}
    version = record_properties.get("updated") or record_properties.get("created")
    if not version:
        raise ValueError("The record needs 'properties.updated' or 'properties.created' to be published")
    return wigos_identifier, version


def record_file_name(wmdrv2, centre_id):
    """Name the record is published under, e.g.
    wmdr2_io-wis2dev-test-wigosnode_0-20000-0-12345_2026-08-21T16_29_00_000.json"""
    wigos_identifier, version = identity(wmdrv2)
    stamp = version.removesuffix("Z").replace(":", "_").replace(".", "_")
    return f"wmdr2_{centre_id}_{wigos_identifier}_{stamp}.json"
