"""Expose unittest failures as GitHub Actions annotations when running in CI.

The normal unittest output stays in the job log. Annotations additionally name
the failed test and exception, so the failure is identifiable from the run's
check results when job logs cannot be downloaded.
"""

import os
import unittest


if os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
    _add_failure = unittest.TestResult.addFailure
    _add_error = unittest.TestResult.addError

    def _escape(value):
        return str(value).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")

    def _annotate(kind, test, error):
        exception_type, exception, _ = error
        message = " ".join(str(exception).split())[:800] or exception_type.__name__
        title = f"{kind}: {test.id()}"
        module = test.__class__.__module__.replace(".", "/")
        print(
            f"::error file={_escape(module + '.py')},line=1,"
            f"title={_escape(title)}::{_escape(exception_type.__name__ + ': ' + message)}",
            flush=True,
        )

    def _failure_with_annotation(self, test, error):
        _annotate("FAIL", test, error)
        return _add_failure(self, test, error)

    def _error_with_annotation(self, test, error):
        _annotate("ERROR", test, error)
        return _add_error(self, test, error)

    unittest.TestResult.addFailure = _failure_with_annotation
    unittest.TestResult.addError = _error_with_annotation