"""Shared structural error with explicit repair eligibility; no catch-all salvage."""

class StructuralDeltaError(ValueError):
    """No safe partial application is known."""
    recoverable = False
    def __init__(self, message, code='invalid_reference', *, repairable=True, **path):
        super().__init__(message)
        self.code, self.repairable, self.path = code, repairable, path

    def diagnostic(self, stage):
        return dict(repair_reason=str(self), repair_error_type=type(self).__name__,
                    repair_error_code=self.code, stage=stage, **self.path)
