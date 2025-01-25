from __future__ import annotations as _annotations

from typing import TYPE_CHECKING as _TYPE_CHECKING
from pathlib import Path as _Path
from functools import partial as _partial

from exceptionman import ReporterException as _ReporterException
import mdit as _mdit

if _TYPE_CHECKING:
    from pyshellman.exception import (
        PyShellManExecutionError, PyShellManNonZeroExitCodeError, PyShellManStderrError
    )
    from pyshellman import ShellOutput


class GitTidyError(_ReporterException):
    """Base class for all GitTidy errors."""

    def __init__(
        self,
        title: str,
        intro: str,
        details,
    ):
        sphinx_config = {"html_title": "GitTidy Error Report"}
        sphinx_target_config = _mdit.target.sphinx(
            renderer=_partial(
                _mdit.render.sphinx,
                config=_mdit.render.get_sphinx_config(sphinx_config)
            )
        )
        report = _mdit.document(
            heading=title,
            body={"intro": intro},
            section={"details": _mdit.document(heading="Details", body=details)},
            target_configs_md={"sphinx": sphinx_target_config},
        )
        super().__init__(report=report)
        return


class GitTidyGitNotFoundError(GitTidyError):
    """Git executable was not found in PATH."""

    def __init__(self, error: PyShellManExecutionError):
        super().__init__(
            title="Git Not Found Error",
            intro="Git executable not found.",
            details=error.output.report(),
        )
        return


class GitTidyNonZeroGitExitCodeError(GitTidyError):
    """Git command exited with a non-zero code."""

    def __init__(self, error: PyShellManNonZeroExitCodeError):
        super().__init__(
            title="Non-Zero Git Exit Code Error",
            intro="Git command exited with a non-zero code.",
            details=error.output.report(),
        )
        return


class GitTidyGitStderrError(GitTidyError):
    """Git command produced output in stderr."""

    def __init__(self, error: PyShellManStderrError):
        super().__init__(
            title="Git Stderr Error",
            intro="Git command produced output in stderr.",
            details=error.output.report(),
        )
        return


class GitTidyNoGitRepositoryError(GitTidyError):
    """No Git repository found in the given path or any parent directory."""

    def __init__(self, output: ShellOutput, path: str | _Path):
        self.path = _Path(path).resolve()
        super().__init__(
            title="No Git Repository Error",
            intro=f"No Git repository found at '{self.path}' or any parent directory.",
            details=output.report(),
        )
        return


class GitTidyInputError(GitTidyError):
    """Error in the input arguments provided to Git methods."""

    def __init__(self, message: str):
        super().__init__(message)
        return


class GitTidyOperationError(GitTidyError):
    """Error in the execution of an operation."""

    def __init__(self, message: str):
        super().__init__(message)
        return
