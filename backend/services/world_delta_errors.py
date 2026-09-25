"""Explicit delta failure classification and leaf removal. Unknown errors are fatal.

Only validators may authorize removal. The caller must revalidate the complete
candidate on a fresh state copy after EVERY removal, before committing anything.
"""

class StructuralDeltaError(ValueError):
    """No safe partial application is known."""
    recoverable = False
    def __init__(self, message, code='invalid_reference', *, repairable=True, **path):
        super().__init__(message)
        self.code, self.repairable, self.path = code, repairable, path

    def diagnostic(self, stage):
        return dict(repair_reason=str(self), repair_error_type=type(self).__name__,
                    repair_error_code=self.code, stage=stage, **self.path)



class SecondaryDeltaError(ValueError):
    """A validator-authorized independent record or field; deterministic removal is safe."""
    recoverable = True

    def __init__(self, section, index, reason, field=None, entity=None, *, path=None, cause_field=None, code="secondary_invalid"):
        self.section, self.index = section, index
        self.path = tuple(path) if path is not None else ((field,) if field else ())
        self.warning = {'type':'sanitized_delta', 'code':code, 'section': section, 'index': index, 'reason': reason}
        if field:
            self.warning['field'] = field
        if entity:
            self.warning['entity'] = entity
        if cause_field:
            self.warning['cause_field'] = cause_field
        diagnostic_field = field or cause_field
        super().__init__(f'World Delta: {section}[{index}]' + (f'.{diagnostic_field}' if diagnostic_field else '') + ': ' + reason)


def sanitize_secondary(delta, error, original_indices):
    """Remove exactly the authorized path, preserving other fields and indices."""
    if not isinstance(error, SecondaryDeltaError):
        raise StructuralDeltaError('Removal requires an explicitly classified secondary error.')
    section, index = error.section, error.index
    records = delta[section]
    warning = dict(error.warning, index=original_indices[section][index])
    if error.path:
        record = records[index]
        parent = record
        for key in error.path[:-1]:
            parent = parent[key]
        del parent[error.path[-1]]
        if section == 'characters' and len(error.path) == 1:
            (record.get('player_evidence') or {}).pop(error.path[0], None)
    else:
        del records[index]
        original_indices[section].pop(index)
    return warning
