from pydantic import BaseModel

from util.functions import to_snake_case


class DBModel(BaseModel):
    def db_dump(self):
        return self.model_dump()

    def values(self):
        return self.db_dump().values()

    @classmethod
    def field_list(cls) -> str:
        return ",".join(cls.model_fields.keys())

    @classmethod
    def placeholders(cls) -> str:
        n = len(cls.model_fields)
        return ",".join(f"${i}" for i in range(1, n + 1))

    @classmethod
    def table_name(cls) -> str:
        name = cls.__name__.removesuffix("DTO")
        return to_snake_case(name) + "s"