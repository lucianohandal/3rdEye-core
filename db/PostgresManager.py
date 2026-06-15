from threading import RLock
from typing import TypeVar

from db.AnalysisDB import AnalysisDB
from db.PostgresDB import PostgresDB
from db.RawLogDB import RawLogDB


TPostgresDB = TypeVar("TPostgresDB", bound=PostgresDB)


class PostgresManager:
    def __init__(self):
        self._postgress_dbs: dict[str, PostgresDB] = {}
        self._rawlogs_dbs: dict[str, RawLogDB] = {}
        self._summary_dbs: dict[str, AnalysisDB] = {}
        self._lock = RLock()

    def _get_or_create(
        self,
        clients: dict[str, TPostgresDB],
        org_id: str,
        db_class: type[TPostgresDB],
    ) -> TPostgresDB:
        with self._lock:
            if org_id not in clients:
                clients[org_id] = db_class(org_id)

            return clients[org_id]

    def get_rawlogs_db(self, org_id: str) -> RawLogDB:
        return self._get_or_create(self._rawlogs_dbs, org_id, RawLogDB)

    def get_analysis_db(self, org_id: str = "default") -> AnalysisDB:
        return self._get_or_create(self._summary_dbs, org_id, AnalysisDB)


_manager = PostgresManager()

def get_rawlogs_db(org_id: str) -> RawLogDB:
    return _manager.get_rawlogs_db(org_id)


def get_analysis_db(org_id: str = "default") -> AnalysisDB:
    return _manager.get_analysis_db(org_id)
