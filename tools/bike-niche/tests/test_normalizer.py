#!/usr/bin/env python3
"""Deterministic regression tests for parsed numeric bicycle geometry.

No network or external credentials. Run: python3 -m unittest discover -s tests
"""
import unittest,sys,pathlib
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from normalize_geometry import normalize,parse,METRIC_LIMITS

class TestNumericGeometry(unittest.TestCase):
 def test_measurement_bounds_cover_fields(self):
  self.assertEqual(len(METRIC_LIMITS),16)
 def test_decimal_comma_and_whitespace(self):
  self.assertEqual(normalize("reach","461,25"),(461.25,"mm"))
  self.assertEqual(normalize("seat_tube_angle","73, 5"),(73.5,"deg"))
  self.assertEqual(normalize("stack","633,48"),(633.48,"mm"))
 def test_grouped_thousands(self):
  self.assertEqual(normalize("wheelbase","1,234 mm"),(1234.0,"mm"))
  self.assertEqual(normalize("wheelbase","1,040.9"),(1040.9,"mm"))
 def test_units(self):
  self.assertEqual(normalize("fork_offset","4.5cm"),(45.0,"mm"))
  self.assertEqual(normalize("head_tube_angle","69,5 °"),(69.5,"deg"))
  self.assertEqual(normalize("fork_offset","44 in"),None)
  self.assertEqual(normalize("fork_offset","2 in"),(50.8,"mm"))
 def test_partial_notes_dont_misparse_unit(self):
  self.assertEqual(normalize("head_tube_angle","70.5 (toe overlap 4 more than M)cm"),(70.5,"deg"))
 def test_bad_values(self):
  for metric,raw in [("bb_height","-7730 mm"),("fork_offset","-9730.4 mm"),("wheelbase","0"),("seat_tube_angle","91 deg"),("stack","0"),("top_tube_length","-1706.3 mm")]:
   with self.subTest(metric=metric,raw=raw):
    self.assertIsNone(normalize(metric,raw))
 def test_valid_values(self):
  for metric,raw in [("reach","455 mm"),("stack","630mm"),("wheelbase","1100 mm"),("fork_length","550 mm"),("bb_drop","-10 mm")]:
   with self.subTest(metric=metric,raw=raw):
    self.assertIsNotNone(normalize(metric,raw))
 def test_stack_reach_geometry_table(self):
  table=[["Size","S","M"],["Stack","600","620"],["Reach","435","455"],["Wheelbase","1030","1050"]]
  got=parse([table])
  self.assertEqual(len(got),6)
  self.assertIn(("M","reach",455.0,"mm","455"),got)
 def test_non_geometry_table_excluded(self):
  self.assertEqual(parse([[["Size","M"],["Weight","7 kg"],["Color","Red"],["Reach","455"]]]),[])
 def test_range_string_preserve_first_reported_variant(self):
  self.assertEqual(normalize("head_tube_angle","67,5-68,5"),(67.5,"deg"))

if __name__=="__main__":unittest.main()
