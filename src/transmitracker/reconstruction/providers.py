"""Provider-neutral future contracts. No HTTP, polling, cache implementation or billing."""

from dataclasses import dataclass
from typing import Iterable, Protocol

from transmitracker.reconstruction.models import (
    CandidateIdentity,
    OriginalObservation,
    ProviderSnapshot,
)


class SnapshotSource(Protocol):
    def snapshots(self) -> Iterable[ProviderSnapshot]: ...


class OperationalIdentityVerifier(Protocol):
    """Future independent evidence gate. 3A implements no real operational attestation."""

    def assess(
        self,
        *,
        candidate: CandidateIdentity,
        observations: tuple[OriginalObservation, ...],
        evidence_references: tuple[str, ...],
    ) -> CandidateIdentity: ...


@dataclass(frozen=True)
class CreditPolicy:
    monthly_credits: int = 1500
    reserved_credits: int = 0
    live_cost: int = 10
    dataset_cost: int = 1
    # User-supplied planning values, not endpoint cost verification or current provider terms.
    operation_classification_verified: bool = False


@dataclass(frozen=True)
class CreditReservation:
    request_fingerprint: str
    operation_class: str
    estimated_credits: int
    confirmed_credits: int | None
    allowed: bool
    dry_run: bool
    cached: bool
    reason: str


class CreditBudgetManager(Protocol):
    def authorize(
        self, *, operation_class: str, request_fingerprint: str, month: str, dry_run: bool
    ) -> CreditReservation: ...
    def confirm(self, reservation: CreditReservation, actual_credits: int) -> None: ...
    def release(self, reservation: CreditReservation) -> None: ...
