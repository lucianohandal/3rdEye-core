from threading import RLock
from typing import TypeVar
from uuid import UUID

from db.AnalysisDB import AnalysisDB
from db.PostgresDB import PostgresDB
from db.RawLogDB import RawLogDB
from db.UsersDB import UsersDB


TPostgresDB = TypeVar("TPostgresDB", bound=PostgresDB)


class PostgresManager:
    def __init__(self):
        self._analysis_db = AnalysisDB()
        self._users_db = UsersDB()
        self._rawlogs_dbs: dict[str, RawLogDB] = {}
        self._lock = RLock()

    def _get_or_create(
        self,
        clients: dict[str, TPostgresDB],
        org_id: str | UUID,
        db_class: type[TPostgresDB],
    ) -> TPostgresDB:
        key = str(org_id)
        with self._lock:
            if key not in clients:
                clients[key] = db_class(org_id)

            return clients[key]

    def get_rawlogs_db(self, org_id: str | UUID) -> RawLogDB:
        return self._get_or_create(self._rawlogs_dbs, org_id, RawLogDB)

    def get_analysis_db(self) -> AnalysisDB:
        return self._analysis_db

    def get_users_db(self) -> UsersDB:
        return self._users_db


_manager = PostgresManager()

def get_rawlogs_db(org_id: str | UUID) -> RawLogDB:
    return _manager.get_rawlogs_db(org_id)


def get_analysis_db() -> AnalysisDB:
    return _manager.get_analysis_db()


def get_users_db() -> UsersDB:
    return _manager.get_users_db()
