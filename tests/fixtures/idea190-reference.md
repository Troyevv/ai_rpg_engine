# Approved visual source for Issue #190

`idea190-reference.zip` contains the supplied prototype's prebuilt workspace HTML/JS/CSS, excluding fonts, screenshots, audit and preview chrome. Original source: the archive linked in Issue #190 and its portable comment attachment. It is rendered only by `tests/e2e_server.py` for same-viewport visual comparisons. The sole bundle adaptation is the folio URL under the test-only mount. Fonts come from the project's unchanged Workshop fonts; the same supplied folio image is used by both pages.

The bundled demo model, local calendar snapshot and simulated job are never imported into production. Production settings, jobs and recovery use the existing API. Keep this snapshot fixed while changing the implementation so screenshots remain an independent visual reference.
