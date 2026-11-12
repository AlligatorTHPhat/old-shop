"""HBA generation for VM deployments, without Docker/database dependencies."""

import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "deploy/scripts/sites.py"
SPEC = importlib.util.spec_from_file_location("sites_access_under_test", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AccessOnly:
    selected = "B"

    def __init__(self):
        self.env = {
            "SITES_SUBNET": "172.29.88.0/24",
            "SITE_B_DB_NAME": "oldshop_2",
            "SITE_A_VIRTUAL_IP": "172.29.88.11",
            "CATALOGUE_VIRTUAL_IP": "172.29.88.20",
            "SITE_B_READER_SOURCE_CIDR": "192.168.56.1/32",
        }
        self.hba = ""

    def run(self, args, input_text):
        self.hba = input_text

    def query(self, *args):
        return [{"n": 0}]

    def sql(self, *args):
        pass


class TestSitesAccess(unittest.TestCase):
    def test_local_default_is_preserved(self):
        instance = AccessOnly()
        MODULE.Sites.configure_access(instance)
        self.assertIn("host oldshop_2 global_reader 172.29.88.20/32 scram-sha-256", instance.hba)

    def test_vm_gateway_source_override_does_not_open_other_sources(self):
        instance = AccessOnly()
        instance.env["SITE_B_CATALOG_SOURCE_CIDR"] = "192.168.56.1/32"
        MODULE.Sites.configure_access(instance)
        self.assertIn("host oldshop_2 global_reader 192.168.56.1/32 scram-sha-256", instance.hba)
        self.assertNotIn("host oldshop_2 global_reader 172.29.88.20/32", instance.hba)
        self.assertIn("host all all 0.0.0.0/0 reject", instance.hba)

    def test_invalid_source_is_rejected_before_applying_hba(self):
        instance = AccessOnly()
        instance.env["SITE_B_CATALOG_SOURCE_CIDR"] = "invalid"
        with self.assertRaises(ValueError):
            MODULE.Sites.configure_access(instance)
        self.assertEqual(instance.hba, "")
