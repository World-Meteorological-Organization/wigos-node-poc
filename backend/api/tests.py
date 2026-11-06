from django.test import TestCase, TransactionTestCase
from .models import Station, WIGOSNodeUser

import json

from django.db.utils import IntegrityError

class StationChangeFieldsTestCase(TestCase):

    def test_existing_stations_have_no_status_or_author(self):
        """The test stations are created by a migration before these fields."""
        station = Station.objects.get(wigos_identifier='0-20000-0-12345')
        self.assertEqual(station.publication_status, '')
        self.assertIsNone(station.last_changed_by)

    def test_deleting_the_user_keeps_the_station(self):
        user = WIGOSNodeUser.objects.create_user(username='changer', email='changer@example.com', password='pw')
        Station.objects.filter(wigos_identifier='0-20000-0-12345').update(last_changed_by=user)

        user.delete()

        station = Station.objects.get(wigos_identifier='0-20000-0-12345')
        self.assertIsNone(station.last_changed_by)


class StationCreationTestCase(TestCase):



    def test_double_creation_rejected(self):

        with open(r'/test_data/test_wmdrv2.json') as f:
            wmdrv2_data = json.load(f)

            some_owner = WIGOSNodeUser.objects.first()

            with self.assertRaises(ValueError):
                Station.objects.create(wmdrv2=wmdrv2_data, owner=some_owner)


    def test_primary_wsi_in_additional_identifier_rejected(self):
        with open(r'/test_data/test_wmdrv2.json') as f:
            wmdrv2_data = json.load(f)
            wmdrv2_data['id'] = '0-51-21-2121'         # WSI used in additional identifiers in test station

            some_owner = WIGOSNodeUser.objects.first()

            with self.assertRaises(ValueError):
                Station.objects.create(wmdrv2=wmdrv2_data, owner=some_owner)



    def test_additional_wsi_in_additional_identifier_rejected(self):
        with open(r'/test_data/test_wmdrv2.json') as f:
            wmdrv2_data = json.load(f)
            wmdrv2_data['id'] = '0-51-21-2121ok'         # WSI not yet used
            wmdrv2_data['properties']['additionalIds'] = ['0-51-21-2121'] # already used in additional identifiers in test station

            some_owner = WIGOSNodeUser.objects.first()

            with self.assertRaises(ValueError):
                Station.objects.create(wmdrv2=wmdrv2_data, owner=some_owner)


    def test_additional_wsi_in_primary_identifier_rejected(self):
        with open(r'/test_data/test_wmdrv2.json') as f:
            wmdrv2_data = json.load(f)
            wmdrv2_data['id'] = '0-51-21-2121ok'         # WSI not yet used
            wmdrv2_data['properties']['additionalIds'] = ['0-20000-0-123456'] # already used in primary identifier in test station

            some_owner = WIGOSNodeUser.objects.first()

            with self.assertRaises(ValueError):
                Station.objects.create(wmdrv2=wmdrv2_data, owner=some_owner)
