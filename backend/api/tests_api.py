import copy
import json

from django.urls import reverse
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Station, WIGOSNodeGroup, WIGOSNodeUser


class StationAPITestCase(APITestCase):

    def test_check_wigosidentifiers(self):
        """Test that a GET request successfully retrieves WIGOS identifier checks."""
        self.checkwsi_url = reverse('check_wigosidentifiers')
        response = self.client.get(self.checkwsi_url, {'wigos_identifier': '1-123-456-ABC'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['1-123-456-ABC'], False)

    def test_check_wigosidentifiers_no_identifiers(self):
        """Test that a GET request without WIGOS identifiers returns a 400 error."""
        self.checkwsi_url = reverse('check_wigosidentifiers')
        response = self.client.get(self.checkwsi_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()['detail'], "No WIGOS identifiers provided")

    def test_check_wigosidentifiers_existing_primary_identifier(self):
        """Test that a GET request with an existing WIGOS identifier returns True."""
        # First, create a station with a known WIGOS identifier
        self.checkwsi_url = reverse('check_wigosidentifiers')
        response = self.client.get(self.checkwsi_url, {'wigos_identifier': '0-20000-0-123456'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['0-20000-0-123456'], True)


    def test_check_wigosidentifiers_existing_secondary_identifier(self):
        """Test that a GET request with an existing secondary WIGOS identifier returns True."""
        # First, create a station with a known secondary WIGOS identifier
        self.checkwsi_url = reverse('check_wigosidentifiers')
        response = self.client.get(self.checkwsi_url, {'wigos_identifier': '0-533-1212-12321'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['0-533-1212-12321'], True)

    def test_check_wigosidentifiers_partial_secondary_identifier(self):
        """Test that a prefix or suffix of an existing secondary WIGOS identifier is not reported as taken."""
        self.checkwsi_url = reverse('check_wigosidentifiers')
        # the test station has additional identifiers 0-51-21-2121 and 0-533-1212-12321
        partial = ['0-51-21-212', '0-533-1212-1232', '-51-21-2121', '1-2121']
        response = self.client.get(self.checkwsi_url, {'wigos_identifier': partial})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {wsi: False for wsi in partial})

    def test_wmdrv2_by_wsi(self):
        """A record is found by its primary or an additional WIGOS identifier."""
        station = Station.objects.get(wigos_identifier='0-20000-0-12345')
        for wsi in ['0-20000-0-12345', '0-533-1212-12321']:
            response = self.client.get(reverse('wmdrv2-wsi', kwargs={'wsi': wsi}))
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.json(), station.wmdrv2)

    def test_wmdrv2_by_wsi_unknown(self):
        response = self.client.get(reverse('wmdrv2-wsi', kwargs={'wsi': '0-20000-0-unknown'}))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_wmdrv2_by_wsi_is_read_only(self):
        response = self.client.put(reverse('wmdrv2-wsi', kwargs={'wsi': '0-20000-0-12345'}), {}, format='json')
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED))

    def test_wmdrv2_response_is_compact_whatever_the_accept_header(self):
        """The record endpoint always serves the same bytes, so a WNM linking
        to it keeps matching."""
        station = Station.objects.get(wigos_identifier='0-20000-0-123456')
        url = reverse('wmdrv2', kwargs={'station_id': station.pk})
        plain = self.client.get(url)
        indented = self.client.get(url, HTTP_ACCEPT='application/json; indent=4')

        self.assertEqual(plain.status_code, status.HTTP_200_OK)
        self.assertEqual(indented.content, plain.content)
        self.assertNotIn(b'\n', plain.content)


with open('/test_data/test_wmdrv2.json') as f:
    BASE_RECORD = json.load(f)

# Issuer groups seeded by migration 0004 (nfps_Switzerland and nfps_Brazil).
ISSUER_A = 756
ISSUER_B = 76


def record(wsi, title="Batch station"):
    data = copy.deepcopy(BASE_RECORD)
    data['id'] = wsi
    data['properties']['title'] = title
    return data


class BatchAPITestCase(APITestCase):

    def setUp(self):
        # Groups can't be created here: the Group post_save signal adds a
        # WIGOSNodeGroup without an issuer, which the database rejects.
        self.group_a = WIGOSNodeGroup.objects.get(issuer_identifier=ISSUER_A).group

        self.owner = WIGOSNodeUser.objects.create_user(username='batch_owner', email='batch_owner@example.com', password='pw')
        self.owner.groups.add(self.group_a)
        self.member = WIGOSNodeUser.objects.create_user(username='batch_member', email='batch_member@example.com', password='pw')
        self.member.groups.add(self.group_a)
        self.outsider = WIGOSNodeUser.objects.create_user(username='batch_outsider', email='batch_outsider@example.com', password='pw')

        self.stations = []
        for i in range(3):
            station = Station(wmdrv2=record(f'0-{ISSUER_A}-0-batch{i}', f'Batch {i}'), owner=self.owner)
            station.save()
            assign_perm('change_station', self.owner, station)
            assign_perm('change_station', self.group_a, station)
            self.stations.append(station)

        self.url = reverse('wmdrv2-batch')

    def post_batch(self, updates, dry_run=False):
        return self.client.post(self.url, {'dry_run': dry_run, 'updates': updates}, format='json')

    def update(self, station, **changes):
        data = copy.deepcopy(station.wmdrv2)
        title = changes.pop('title', None)
        if title:
            data['properties']['title'] = title
        data.update(changes)
        return {'station_id': station.id, 'wmdrv2': data}

    def title_of(self, station):
        return Station.objects.get(id=station.id).wmdrv2['properties']['title']

    def test_batch_update_saves(self):
        self.client.force_authenticate(self.owner)
        response = self.post_batch([self.update(s, title=f'Renamed {s.id}') for s in self.stations])
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(body['summary'], {'ok': 3, 'error': 0})
        self.assertEqual([r['index'] for r in body['results']], [0, 1, 2])
        for station in self.stations:
            self.assertEqual(self.title_of(station), f'Renamed {station.id}')
            self.assertEqual(Station.objects.get(id=station.id).name, f'Renamed {station.id}')

    def test_dry_run_saves_nothing(self):
        self.client.force_authenticate(self.owner)
        response = self.post_batch([self.update(s, title='Changed') for s in self.stations], dry_run=True)
        body = response.json()
        self.assertTrue(body['dry_run'])
        self.assertEqual(body['summary'], {'ok': 3, 'error': 0})
        for i, station in enumerate(self.stations):
            self.assertEqual(self.title_of(station), f'Batch {i}')

    def test_schema_invalid_record_fails_alone(self):
        self.client.force_authenticate(self.owner)
        invalid = self.update(self.stations[0], title='Invalid')
        del invalid['wmdrv2']['properties']['observations'][0]['configurations'][0]['time']
        response = self.post_batch([invalid, self.update(self.stations[1], title='Valid')])
        first, second = response.json()['results']
        self.assertEqual(first['status'], 'error')
        self.assertEqual(first['message'], 'The record is not valid against the WMDR2 schema.')
        self.assertIn("/properties/observations/0/configurations/0: 'time' is a required property", first['errors'])
        self.assertEqual(second['status'], 'ok')
        self.assertEqual(self.title_of(self.stations[0]), 'Batch 0')
        self.assertEqual(self.title_of(self.stations[1]), 'Valid')

    def test_station_without_permission_fails_alone(self):
        other = Station(wmdrv2=record(f'0-{ISSUER_A}-0-other'), owner=self.outsider)
        other.save()
        self.client.force_authenticate(self.owner)
        response = self.post_batch([self.update(other, title='Nope'), self.update(self.stations[0], title='Yes')])
        first, second = response.json()['results']
        self.assertEqual(first['status'], 'error')
        self.assertEqual(second['status'], 'ok')
        self.assertEqual(self.title_of(other), 'Batch station')

    def test_missing_or_unknown_station_id_never_creates(self):
        self.client.force_authenticate(self.owner)
        count = Station.objects.count()
        response = self.post_batch([
            {'wmdrv2': record(f'0-{ISSUER_A}-0-new1')},
            {'station_id': 999999, 'wmdrv2': record(f'0-{ISSUER_A}-0-new2')},
            {'station_id': True, 'wmdrv2': record(f'0-{ISSUER_A}-0-new3')},
        ])
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['summary'], {'ok': 0, 'error': 3})
        self.assertEqual(Station.objects.count(), count)

    def test_primary_id_change_checks_new_issuer(self):
        self.client.force_authenticate(self.owner)
        response = self.post_batch([
            self.update(self.stations[0], id=f'0-{ISSUER_B}-0-moved'),
            self.update(self.stations[1], id=f'0-{ISSUER_A}-0-renumbered'),
        ])
        first, second = response.json()['results']
        self.assertEqual(first['status'], 'error')
        self.assertIn(str(ISSUER_B), first['message'])
        self.assertEqual(second['status'], 'ok')
        self.assertEqual(second['wsi'], f'0-{ISSUER_A}-0-renumbered')
        self.assertEqual(Station.objects.get(id=self.stations[0].id).wigos_identifier, f'0-{ISSUER_A}-0-batch0')
        self.assertEqual(Station.objects.get(id=self.stations[1].id).wigos_identifier, f'0-{ISSUER_A}-0-renumbered')

    def test_same_new_wsi_twice_in_batch(self):
        self.client.force_authenticate(self.owner)
        wsi = f'0-{ISSUER_A}-0-shared'
        response = self.post_batch([self.update(self.stations[0], id=wsi), self.update(self.stations[1], id=wsi)])
        first, second = response.json()['results']
        self.assertEqual(first['status'], 'ok')
        self.assertEqual(second['status'], 'error')
        self.assertIn('already in use', second['message'])

    def test_batch_requires_authentication(self):
        response = self.post_batch([self.update(self.stations[0], title='Anon')])
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_too_many_updates(self):
        self.client.force_authenticate(self.owner)
        response = self.post_batch([self.update(self.stations[0])] * 501)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_batch_read(self):
        ids = [self.stations[0].id, self.stations[2].id, 999999]
        response = self.client.get(self.url, {'station_id': ids})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(set(body), {str(self.stations[0].id), str(self.stations[2].id)})
        self.assertEqual(body[str(self.stations[0].id)]['id'], f'0-{ISSUER_A}-0-batch0')

    def test_batch_read_rejects_bad_ids(self):
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.client.get(self.url, {'station_id': 'abc'}).status_code, status.HTTP_400_BAD_REQUEST)

    def can_edit_map(self):
        response = self.client.get(reverse('my_stations'))
        return {s['station_id']: s['can_edit'] for s in response.json()}

    def test_my_stations_can_edit(self):
        mine = {s.id for s in self.stations}

        self.client.force_authenticate(self.owner)
        can_edit = self.can_edit_map()
        self.assertTrue(all(can_edit[i] for i in mine))
        self.assertFalse(any(v for i, v in can_edit.items() if i not in mine))

        self.client.force_authenticate(self.member)
        self.assertTrue(all(self.can_edit_map()[i] for i in mine))

        self.client.force_authenticate(self.outsider)
        self.assertFalse(any(self.can_edit_map().values()))

        self.client.force_authenticate(None)
        self.assertFalse(any(self.can_edit_map().values()))

    def test_single_put_validates_schema(self):
        self.client.force_authenticate(self.owner)
        data = copy.deepcopy(self.stations[0].wmdrv2)
        data['id'] = 'not-a-wsi'
        response = self.client.put(reverse('wmdrv2', args=[self.stations[0].id]), data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(response.json()['errors'])

    def test_single_post_validates_and_creates(self):
        self.client.force_authenticate(self.owner)
        response = self.client.post(reverse('wmdrv2'), record(f'0-{ISSUER_A}-0-created'), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        station = Station.objects.get(id=response.json()['station_id'])
        self.assertTrue(self.member.has_perm('change_station', station))

        response = self.client.post(reverse('wmdrv2'), record(f'0-{ISSUER_B}-0-created'), format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('error', response.json())