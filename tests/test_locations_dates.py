import unittest
from date_core import normalise_date
import location_core as loc

class DatesLocationsTest(unittest.TestCase):
    def test_formats_and_impossible_dates(self):
        for value in ['8/10/2026','08/10/26','8-10-26','08.10.2026','08102026','081026','2026-10-8']:
            self.assertEqual(normalise_date(value),'2026-10-08')
        self.assertEqual(normalise_date('29/2/24'),'2024-02-29')
        for value in ['31/2/26','29/2/25','10/31/26','8/10','12345','2026-00-08','31/04/2026']:
            with self.assertRaises(ValueError):normalise_date(value)

    def test_sunshine_coast_recognises_suburbs_without_manual_list(self):
        prefs=dict(home_base='Sunshine Coast',home_aliases='',local_radius_km=50)
        for place in ['Maroochydore','Mooloolaba','Caloundra','Buderim','Noosa Heads']:
            self.assertEqual(loc.local_assessment(prefs,place)['status'],'local',place)
        for place in ['Cairns','Townsville','Brisbane']:
            self.assertEqual(loc.local_assessment(prefs,place)['status'],'away',place)
        self.assertGreater(loc.coverage(prefs)['local_count'],30)

    def test_ambiguity_postcode_state_and_address(self):
        self.assertIsNone(loc.resolve('Richmond'))
        self.assertEqual(loc.resolve('Richmond VIC 3121')['state'],'VIC')
        self.assertIsNone(loc.resolve('Unrecognised suburb'))
        prefs=dict(home_base='Sunshine Coast',home_aliases='',local_radius_km=50)
        self.assertEqual(loc.local_assessment(prefs,'Richmond')['status'],'unknown')
        self.assertEqual(loc.local_assessment(prefs,'Sunshine Coast','1 Test St Maroochydore QLD 4558')['status'],'local')
        self.assertEqual(loc.local_assessment(prefs,'New York',currency='USD')['status'],'unknown')
        self.assertTrue(any(x['name']=='Maroochydore' for x in loc.search('4558')))

    def test_selected_base_and_radius(self):
        base=loc.resolve('Maroochydore');prefs=dict(home_base=base['name'],home_place_id=base['id'],local_radius_km=5)
        result=loc.local_assessment(prefs,'Caloundra');self.assertEqual(result['status'],'away')
        prefs['local_radius_km']=50;self.assertEqual(loc.local_assessment(prefs,'Caloundra')['status'],'local')
