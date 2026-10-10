#!/usr/bin/env python3
"""Fast, network-free admission regression checks for source-isolated collector."""
import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from collector import ALLOWED

class CollectorRoutesTest(unittest.TestCase):
 def test_required_sources_supported(self):
  self.assertTrue({"bikeinsights","rideinsights","sram","geometrygeeks"}.issubset(ALLOWED))
 def test_geometrygeeks_paths(self):
  self.assertTrue(ALLOWED["geometrygeeks"]("/bike/specialized-tarmac-2024/"))
  self.assertFalse(ALLOWED["geometrygeeks"]("/admin/"))
  self.assertFalse(ALLOWED["geometrygeeks"]("/bike-directory/all/"))
 def test_other_source_isolation(self):
  self.assertTrue(ALLOWED["bikeinsights"]("/bikes/a"))
  self.assertFalse(ALLOWED["bikeinsights"]("/en/service/"))
  self.assertTrue(ALLOWED["rideinsights"]("/parts/frames/example"))
  self.assertFalse(ALLOWED["rideinsights"]("/bike/example/"))
  self.assertTrue(ALLOWED["sram"]("/en/sram/models/products/test"))
  self.assertFalse(ALLOWED["sram"]("/bike/example/"))

if __name__=="__main__": unittest.main()
