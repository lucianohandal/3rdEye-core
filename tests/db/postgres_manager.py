import unittest
from uuid import uuid4

from db.AnalysisDB import AnalysisDB
from db.PostgresManager import PostgresManager
from db.RawLogDB import RawLogDB
from db.UsersDB import UsersDB


class PostgresManagerTestCase(unittest.TestCase):
    def test_singleton_dbs_are_reused(self) -> None:
        manager = PostgresManager()

        self.assertIs(manager.get_analysis_db(), manager.get_analysis_db())
        self.assertIs(manager.get_users_db(), manager.get_users_db())
        self.assertIsInstance(manager.get_analysis_db(), AnalysisDB)
        self.assertIsInstance(manager.get_users_db(), UsersDB)

    def test_raw_log_dbs_are_cached_by_org_id_string(self) -> None:
        manager = PostgresManager()
        org_id = uuid4()

        first = manager.get_rawlogs_db(org_id)
        second = manager.get_rawlogs_db(str(org_id))

        self.assertIs(first, second)
        self.assertIsInstance(first, RawLogDB)
