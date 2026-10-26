from dataclasses import dataclass
from enum import Enum, auto


class ProcessingStep(Enum):
    REQUEST_ROUTING = auto()
    REQUEST_DENIED = auto()
    CREATE_GRANT = auto()
    PROVISION_GRANT = auto()
    REVOKE_GRANT = auto()


class ProcessingResult(Enum):
    NO_ACTION_NEEDED = auto()
    APPROVAL_REQUIRED = auto()
    NOTIFICATION_REQUIRED = auto()
    ERROR = auto()


@dataclass(frozen=True)
class ProcessingReport:
    subject: object
    processing_step: ProcessingStep
    processing_step_result: ProcessingResult
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.processing_step_result != ProcessingResult.ERROR

    @classmethod
    def ok(cls, subject, step, result):
        return cls(subject, step, result)

    @classmethod
    def failed(cls, subject, step, error):
        return cls(subject, step, ProcessingResult.ERROR, error)


class RunReport:
    def __init__(self):
        self.results: list[ProcessingReport] = []

    def extend(self, results):
        self.results.extend(results)

    @property
    def to_notify_approvers(self):
        return [r for r in self.results if r.succeeded and r.processing_step_result == ProcessingResult.APPROVAL_REQUIRED]

    @property
    def to_notify_user(self):
        return [r for r in self.results if r.succeeded and r.processing_step_result == ProcessingResult.NOTIFICATION_REQUIRED]

    @property
    def failures(self):
        return [r for r in self.results if not r.succeeded]
