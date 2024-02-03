from pathlib import Path as _Path


class GitTidyError(Exception):
    """Base class for all GitTidy errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
        return


class GitTidyGitNotFoundError(GitTidyError):
    """Git executable was not found in PATH."""

    def __init__(
        self,
        message: str = "Git executable not found in PATH; please install 'git' and try again."
    ):
        super().__init__(message)
        return


class GitTidyNoGitRepositoryError(GitTidyError):
    """No Git repository found in the given path or any parent directory."""

    def __init__(self, path: str | _Path):
        self.path = _Path(path).resolve()
        super().__init__(f"No Git repository found in '{self.path}' or any parent directory.")
        return
