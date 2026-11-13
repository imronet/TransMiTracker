"""Version 1 contracts: stable codes/field paths, no CLI or widget dependency."""

from dataclasses import asdict, dataclass, fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Issue:
    code: str
    field: str
    message: str


@dataclass(frozen=True)
class Result(Generic[T]):
    data: T | None = None
    errors: tuple[Issue, ...] = ()
    warnings: tuple[Issue, ...] = ()
    contract_version: int = 1

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "contract_version": self.contract_version,
            "ok": self.ok,
            "data": primitive(self.data),
            "errors": [asdict(i) for i in self.errors],
            "warnings": [asdict(i) for i in self.warnings],
        }


def primitive(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if is_dataclass(value):
        return {f.name: primitive(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (list, tuple)):
        return [primitive(v) for v in value]
    if isinstance(value, dict):
        return {k: primitive(v) for k, v in value.items()}
    return value


def failure(code: str, field: str, message: str):
    return Result(errors=(Issue(code, field, message),))
