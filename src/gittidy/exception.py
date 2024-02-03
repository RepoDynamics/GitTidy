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
