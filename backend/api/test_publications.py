"""The publication API (api/publications.py): real stations saved through the
API, nothing set by hand apart from their status, then what each kind of user
sees and can do."""

import copy
import json

from django.test import Client
from django.urls import reverse
from django_tasks_db.models import DBTaskResult
from rest_framework.test import APITestCase

from .models import Station, WIGOSNodeGroup, WIGOSNodeUser

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


class PublicationsApiTestCase(APITestCase):
    def setUp(self):
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

    def test_a_row_says_who_and_what(self):
        station = self.create("0-756-0-uc9", updated="2026-11-05T10:00:00Z", title="Ninth")
        changed = record("0-756-0-uc9", updated="2026-11-05T10:00:00Z", title="Ninth")
        changed["properties"]["description"] = "Changed by a colleague"
        self.update(station, changed, self.colleague)
        self.set_status(station, Status.FAILED)

        [row] = self.listed()

        self.assertEqual(row, {
            "station_id": station.pk,
            "wigos_identifier": "0-756-0-uc9",
            "name": "Ninth",
            "status": "failed",
            "updated": "2026-11-05T10:00:00Z",
            "changed_by": "uc_colleague",
            "can_retry": True,
        })

    def test_an_administrators_change_shows_no_user_name(self):
        self.create("0-756-0-uc11", self.admin)
        [row] = self.listed(self.colleague)
        self.assertIsNone(row["changed_by"])

    def test_the_page_offers_a_retry_only_after_a_failure(self):
        for status in (Status.PENDING, Status.PROCESSING, Status.FAILED, Status.PROCESSED):
            self.set_status(self.create(f"0-756-0-{status}"), status)
        flags = {row["status"]: row["can_retry"] for row in self.listed()}
        self.assertEqual(flags, {"pending": False, "processing": False, "failed": True, "processed": False})

    def test_a_retry_publishes_the_current_record_again_as_an_update_whatever_the_status(self):
        for status in (Status.PENDING, Status.PROCESSING, Status.FAILED, Status.PROCESSED):
            station = self.create(f"0-756-0-r{status}")
            self.set_status(station, status)
            DBTaskResult.objects.all().delete()

            response = self.retry(station)

            self.assertEqual(response.status_code, 200, status)
            self.assertEqual(response.json()["status"], "pending")
            self.assertEqual(self.status_of(station), Status.PENDING)
            self.assertEqual(queued(), [(station.pk, "update")])
            job = DBTaskResult.objects.get()
            self.assertEqual(job.args_kwargs["args"][1], Station.objects.get(pk=station.pk).wmdrv2)

    def test_a_colleague_can_retry_but_someone_who_cant_edit_cant(self):
        station = self.create("0-756-0-uc13")
        self.set_status(station, Status.FAILED)
        DBTaskResult.objects.all().delete()

        for user in (self.foreigner, self.outsider):
            self.assertEqual(self.retry(station, user).status_code, 404, user.username)
        self.assertEqual(self.status_of(station), Status.FAILED)
        self.assertEqual(queued(), [])

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
