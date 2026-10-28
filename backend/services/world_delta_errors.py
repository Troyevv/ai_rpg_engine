"""Shared structural error with explicit repair eligibility; no catch-all salvage."""

class StructuralDeltaError(ValueError):
    """No safe partial application is known."""
    recoverable = False
    def __init__(self, message, code='invalid_reference', *, repairable=True, **path):
        super().__init__(message)
        self.code, self.repairable, self.path = code, repairable, path

    def diagnostic(self, stage):
        section=self.path.get('section', 'runtime')
        path=section if section!='runtime' else '$'
        if 'index' in self.path: path+=f"[{self.path['index']}]"
        if self.path.get('field'): path+='.'+self.path['field']
        return dict(domain=section, section=section, path=path, code=self.code,
                    source_ids=[self.path['entity']] if self.path.get('entity') else [],
                    severity='recoverable' if self.repairable else 'hard_conflict',
                    action='extraction_repair' if self.repairable else 'regenerate',
                    repair_reason=str(self), repair_error_type=type(self).__name__,
                    repair_error_code=self.code, stage=stage) | self.path
