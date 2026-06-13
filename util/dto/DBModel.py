from pydantic import BaseModel

from util.functions import to_snake_case


class DBModel(BaseModel):
    def db_dump(self):
        return self.model_dump()

    def values(self):
        return self.db_dump().values()

    def update_values(self, org_id: str):
        data = self.db_dump()
        return tuple(data[field] for field in self.update_fields()) + (data["id"], org_id)

    @classmethod
    def fields(
        cls,
        include: set[str] | None = None,
        exclude: set[str] | None = None,
    ) -> list[str]:
        exclude = exclude or set()
        return [
            field
            for field in cls.model_fields.keys()
            if field not in exclude and (include is None or field in include)
        ]

    @classmethod
    def field_list(
        cls,
        include: set[str] | None = None,
        exclude: set[str] | None = None,
    ) -> str:
        return ",".join(cls.fields(include=include, exclude=exclude))

    @classmethod
    def set_clause(
        cls,
        include: set[str] | None = None,
        exclude: set[str] | None = None,
    ) -> str:
        fields = cls.fields(include=include, exclude=exclude)
        return ", ".join(f"{field} = ${i}" for i, field in enumerate(fields, start=1))

    @classmethod
    def place_holders(
            cls,
            include: set[str] | None = None,
            exclude: set[str] | None = None,
    ) -> str:
        n = len(cls.fields(include=include, exclude=exclude))
        return ",".join(f"${i}" for i in range(1, n + 1))

    @classmethod
    def table_name(cls) -> str:
        name = cls.__name__.removesuffix("DTO")
        return to_snake_case(name) + "s"
