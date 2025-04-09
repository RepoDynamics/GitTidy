"""Git API."""
from __future__ import annotations as _annotations

import datetime as _datetime
from typing import Literal as _Literal, TYPE_CHECKING as _TYPE_CHECKING
import os as _os
from pathlib import Path as _Path
import re as _re
from contextlib import contextmanager as _contextmanager

import loggerman as _loggerman
import pyshellman as _pyshellman

from gittidy import exception as _exception

if _TYPE_CHECKING:
    from typing import Literal
    LogLevel = Literal["debug", "success", "info", "notice", "warning", "error", "critical"]


__all__ = ["Git"]


class Git:

    def __init__(
        self,
        path: str | _Path,
        user: tuple[str, str] | None = None,
        user_scope: Literal["system", "global", "local", "worktree", "process"] = "process",
        author: tuple[str, str] | None = None,
        author_scope: Literal["system", "global", "local", "worktree", "process"] = "process",
        committer: tuple[str, str] | None = None,
        committer_scope: Literal["system", "global", "local", "worktree", "process"] = "process",
        raise_execution: bool = True,
        raise_exit_code: bool = True,
        raise_stderr: bool = False,
        logger: _loggerman.Logger | None = None,
        log_title: str = "Git Command",
        log_level_execution: LogLevel = "critical",
        log_level_exit_code: LogLevel = "error",
        log_level_stderr: LogLevel = "info",
        log_level_success: LogLevel = "success",
    ):
        if logger:
            self.logger = logger
        else:
            self.logger = _loggerman.create(realtime_levels=None)
            self.logger.section("GitTidy Logs")
        self._shell_runner = _pyshellman.Runner(
            pre_command=["git"],
            raise_execution=raise_execution,
            raise_exit_code=raise_exit_code,
            raise_stderr=raise_stderr,
            logger=self.logger,
            log_title=log_title,
            log_level_execution=log_level_execution,
            log_level_exit_code=log_level_exit_code,
            log_level_stderr=log_level_stderr,
            log_level_success=log_level_success,
        )
        self._path = None
        self.run_command(
            ["version", "--build-options"],
            log_title="Git: Check Version",
            raise_execution=True,
            raise_exit_code=False,
            raise_stderr=False,
        )
        output_repo_path = self.run_command(
            ["-C", str(_Path(path).resolve()), "rev-parse", "--show-toplevel"],
            log_title="Git: Check Repository Path",
            raise_exit_code=False,
            raise_stderr=False,
        )
        if not output_repo_path.succeeded:
            raise _exception.GitTidyNoGitRepositoryError(output=output_repo_path, path=path)
        self._path = _Path(output_repo_path.out).resolve()

        for user_type, user_data, user_scope in (
            ("user", user, user_scope),
            ("author", author, author_scope),
            ("committer", committer, committer_scope),
        ):
            if user_data:
                self.set_user(
                    name=user_data[0],
                    email=user_data[1],
                    typ=user_type,
                    scope=user_scope,
                )
        return

    @property
    def repo_path(self) -> _Path:
        return self._path

    def run_command(
        self,
        command: list[str],
        log_title: str | None = None,
        raise_execution: bool | None = None,
        raise_exit_code: bool | None = None,
        raise_stderr: bool | None = None,
        log_level_execution: LogLevel | None = None,
        log_level_exit_code: LogLevel | None = None,
        log_level_stderr: LogLevel | None = None,
        log_level_success: LogLevel | None = None,
        text_output: bool = True,
        stack_up: int = 0,
    ) -> _pyshellman.ShellOutput:

        def run() -> _pyshellman.ShellOutput:
            try:
                return self._shell_runner.run(
                    command=command,
                    cwd=self._path,
                    raise_execution=raise_execution,
                    raise_exit_code=raise_exit_code,
                    raise_stderr=raise_stderr,
                    text_output=text_output,
                    log_title=log_title,
                    log_level_execution=log_level_execution,
                    log_level_exit_code=log_level_exit_code,
                    log_level_stderr=log_level_stderr,
                    log_level_success=log_level_success,
                    stack_up=stack_up + 2,
                )
            except _pyshellman.exception.PyShellManExecutionError as e:
                raise _exception.GitTidyGitNotFoundError(e) from None
            except _pyshellman.exception.PyShellManNonZeroExitCodeError as e:
                raise _exception.GitTidyNonZeroGitExitCodeError(e) from None
            except _pyshellman.exception.PyShellManStderrError as e:
                raise _exception.GitTidyGitStderrError(e) from None
        return run()

    def push(
        self,
        target: str = "",
        ref: str = "",
        set_upstream: bool = False,
        upstream_branch_name: str = "",
        force_with_lease: bool = False
    ) -> None:
        command = ["push"]
        if set_upstream:
            if not target:
                raise _exception.GitTidyInputError("No 'target' provided while 'set_upstream' is set.")
            command.extend(["--set-upstream", target, upstream_branch_name or self.current_branch_name()])
        elif target:
            command.append(target)
        if ref:
            command.append(ref)
        if force_with_lease:
            command.append("--force-with-lease")
        self.run_command(
            command=command,
            log_title="Git: Push",
            stack_up=1,
        )
        return

    def commit(
        self,
        message: str = "",
        stage: _Literal["all", "tracked", "none"] = "all",
        amend: bool = False,
        allow_empty: bool = False,
    ) -> str | None:
        """
        Commit changes to git.

        Parameters:
        - message (str): The commit message.
        - username (str): The git username.
        - email (str): The git email.
        - add (bool): Whether to add all changes before committing.
        """
        if not amend and not message:
            raise _exception.GitTidyInputError("No 'message' provided for new commit.")
        if stage != "none":
            self.run_command(
                ["add", "-A" if stage == "all" else "-u"],
                log_title="Git: Stage Changes",
                stack_up=1,
            )
        commit_cmd = ["commit"]
        if amend:
            commit_cmd.append("--amend")
            if not message:
                commit_cmd.append("--no-edit")
        if allow_empty:
            commit_cmd.append("--allow-empty")
        for msg_line in message.splitlines():
            if msg_line:
                commit_cmd.extend(["-m", msg_line])
        commit_hash = None
        if allow_empty or self.has_changes(check_type="staged"):
            self.run_command(
                commit_cmd,
                log_title="Git: Commit Changes",
                stack_up=1,
            )
            commit_hash = self.commit_hash_normal()
        return commit_hash

    def create_tag(
        self,
        tag: str,
        message: str = "",
        push_target: str | None = "origin",
    ):
        cmd = ["tag"]
        if not message:
            cmd.append(tag)
        else:
            cmd.extend(["-a", tag, "-m", message])
        self.run_command(cmd, log_title="Git: Create Tag", stack_up=1)
        out = self.run_command(["show", tag], log_title="Git: Show Tag", stack_up=1).out
        if push_target:
            self.push(target=push_target, ref=tag)
        return out

    def delete_tag(
        self,
        tag: str,
        push_target: str | None = "origin",
        raise_nonexistent: bool = True,
    ) -> None:
        nonexistent = self.run_command(
            ["tag", "-d", tag],
            log_title=f"Git: Delete Local Tag {tag}",
            raise_exit_code=raise_nonexistent,
            stack_up=1
        ).code
        if push_target and not nonexistent:
            self.run_command(
                ["push", push_target, "--delete", tag],
                log_title=f"Git: Delete Remote Tag {tag}",
                stack_up=1,
            )
        return

    def has_changes(
        self,
        check_type: _Literal["staged", "unstaged", "all"] = "all",
        path: str | None = None,
    ) -> bool:
        """Checks for git changes.

        Parameters:
        - check_type (str): Can be 'staged', 'unstaged', or 'both'. Default is 'both'.

        Returns:
        - bool: True if changes are detected, False otherwise.
        """
        commands = {"staged": ["diff", "--quiet", "--cached"], "unstaged": ["diff", "--quiet"]}
        if path:
            commands = {k: [*v, path] for k, v in commands.items()}
        if check_type == "all":
            return any(
                self.run_command(
                    cmd,
                    raise_exit_code=False,
                    log_title=f"Git: Check {cmd_type} changes",
                    log_level_exit_code=self._shell_runner.log_level_success,
                    stack_up=1,
                ).code != 0 for cmd_type, cmd in commands.items()
            )
        return self.run_command(
            commands[check_type],
            raise_exit_code=False,
            log_level_exit_code=self._shell_runner.log_level_success,
            log_title=f"Git: Check {check_type} changes",
            stack_up=1,
        ).code != 0

    def restore(
        self,
        path: str,
        change_type: _Literal["staged", "unstaged", "all"] = "all",
        source: str | None = None,
    ):
        """Restore changes in git.

        Parameters:
        - change_type (str): Can be 'staged', 'unstaged', or 'all'. Default is 'all'.
        """
        cmd = ["restore", "--progress"]
        if source:
            cmd.extend(["--source", source])
        if change_type == "all":
            cmd.extend(["--staged", "--worktree"])
        elif change_type == "staged":
            cmd.append("--staged")
        else:
            cmd.append("--worktree")
        cmd.append(path)
        self.run_command(
            cmd,
            log_title="Git: Restore Changes",
            stack_up=1,
        )
        return

    def changed_files(self, ref_start: str, ref_end: str) -> dict[str, list[str]]:
        """
        Get all files that have changed between two commits, and the type of changes.

        Parameters
        ----------
        ref_start : str
            The starting commit hash.
        ref_end : str
            The ending commit hash.

        Returns
        -------
        dict[str, list[str]]
            A dictionary where the keys are the type of change, and the values are lists of paths.
            The paths are given as strings, and are relative to the repository root.
            The keys are one of the following:

            - 'added': Files that have been added.
            - 'deleted': Files that have been deleted.
            - 'modified': Files that have been modified.
            - 'unmerged': Files that have been unmerged.
            - 'unknown': Files with unknown changes.
            - 'broken': Files that are broken.
            - 'copied_from': Source paths of files that have been copied.
            - 'copied_to': Destination paths of files that have been copied.
            - 'renamed_from': Source paths of files that have been renamed.
            - 'renamed_to': Destination paths of files that have been renamed.
            - 'copied_modified_from': Source paths of files that have been copied and modified.
            - 'copied_modified_to': Destination paths of files that have been copied and modified.
            - 'renamed_modified_from': Source paths of files that have been renamed and modified.
            - 'renamed_modified_to': Destination paths of files that have been renamed and modified.

            In the case of keys that end with '_from' and '_to', the elements of the corresponding
            lists are in the same order, e.g. 'copied_from[0]' and 'copied_to[0]' are the source and
            destination paths of the same file.

        """
        key_def = {
            "A": "added",
            "D": "deleted",
            "M": "modified",
            "U": "unmerged",
            "X": "unknown",
            "B": "broken",
            "C": "copied",
            "R": "renamed",
        }
        out = {}
        changes = self.run_command(
            ["diff", "--name-status", ref_start, ref_end],
            log_title="Git: Get Changed Files",
            stack_up=1,
        ).out.splitlines()
        for change in changes:
            key, *paths = change.split("\t")
            if key in key_def:
                out.setdefault(key_def[key], []).extend(paths)
                continue
            key, similarity = key[0], int(key[1:])
            if key not in ["C", "R"]:
                raise ValueError(f"Unknown file change type: {change}")
            out_key = key_def[key]
            if similarity != 100:
                out_key += "_modified"
            out.setdefault(f"{out_key}_from", []).append(paths[0])
            out.setdefault(f"{out_key}_to", []).append(paths[1])
        return out

    def commit_hash_normal(self, parent: int = 0) -> str | None:
        """
        Get the commit hash of the current commit.

        Parameters:
        - parent (int): The number of parents to traverse. Default is 0.

        Returns:
        - str: The commit hash.
        """
        return self.run_command(
            ["rev-parse", f"HEAD~{parent}"],
            log_title="Git: Get Commit Hash",
            stack_up=1,
        ).out

    def commit_date_latest(self) -> _datetime.datetime:
        # Run the git command to get the commit date
        date_str = self.run_command(
            ["log", "-1", "--format=%cd"],
            log_title="Git: Get Latest Commit Date",
            stack_up=1,
        ).out.strip()
        return _datetime.datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y %z")

    def describe(
        self, abbrev: int | None = None, first_parent: bool = True, match: str | None = None
    ) -> str | None:
        cmd = ["describe"]
        if abbrev is not None:
            cmd.append(f"--abbrev={abbrev}")
        if first_parent:
            cmd.append("--first-parent")
        if match:
            cmd.extend(["--match", match])
        result = self.run_command(command=cmd, raise_exit_code=False, log_title="Git: Describe", stack_up=1)
        return result.out if result.code == 0 else None

    def log(
        self,
        number: int | None = None,
        simplify_by_decoration: bool = True,
        tags: bool | str = True,
        pretty: str = "format:%D",
        date: str = "",
        revision_range: str = "",
        paths: str | list[str] = "",
    ) -> str:
        cmd = ["log"]
        if number:
            cmd.append(f"-{number}")
        if simplify_by_decoration:
            cmd.append("--simplify-by-decoration")
        if tags:
            cmd.append(f"--tags={tags}" if isinstance(tags, str) else "--tags")
        if pretty:
            cmd.append(f"--pretty={pretty}")
        if date:
            cmd.append(f"--date={date}")
        if revision_range:
            cmd.append(revision_range)
        if paths:
            cmd.extend(["--"] + (paths if isinstance(paths, list) else [paths]))
        return self.run_command(cmd, log_title=f"Git: Log", stack_up=1).out or ""

    def set_user(
        self,
        name: str | None = "",
        email: str | None = "",
        typ: _Literal["user", "author", "committer"] = "user",
        scope: _Literal["system", "global", "local", "worktree", "process"] | None = "process",
    ) -> None:
        """
        Set the git username and email.
        """
        def get_env_var_names(config_type: Literal["name", "email"]) -> list[str]:
            env_vars_names = []
            if typ in ("user", "author"):
                env_vars_names.append(f"GIT_AUTHOR_{config_type.upper()}")
            if typ in ("user", "committer"):
                env_vars_names.append(f"GIT_COMMITTER_{config_type.upper()}")
            return env_vars_names

        if not ((name is None or isinstance(name, str)) and (email is None or isinstance(email, str))):
            raise _exception.GitTidyInputError("'username' and 'email' must be either a string or None.")
        if name is None and email is None:
            raise _exception.GitTidyInputError("Both 'username' and 'email' cannot be None.")
        if typ not in ["user", "author", "committer"]:
            raise _exception.GitTidyInputError("'user_type' must be one of 'user', 'author', or 'committer'.")
        if scope and scope not in ["system", "global", "local", "worktree", "process"]:
            raise _exception.GitTidyInputError("'scope' must be one of 'system', 'global', 'local', 'worktree', 'process', or None.")

        if scope == "process":
            # Set env vars: https://git-scm.com/book/en/v2/Git-Internals-Environment-Variables
            for config_name, config in (("name", name), ("email", email)):
                if config is None:
                    continue
                env_vars_names = get_env_var_names(config_name)
                for env_var_name in env_vars_names:
                    if config:
                        _os.environ[env_var_name] = config
                    else:
                        _os.environ.pop(env_var_name, None)
            return

        cmd = ["config"]
        if scope:
            cmd.append(f"--{scope}")
        for key, val in [("name", name), ("email", email)]:
            if val is None:
                continue
            if val == "":
                self.run_command(
                    [*cmd, "--unset", f"{typ}.{key}"],
                    log_title=f"Git: Unset {typ} {key}",
                    stack_up=1,
                )
            else:
                self.run_command(
                    [*cmd, f"{typ}.{key}", val],
                    log_title=f"Git: Set {typ} {key}",
                    stack_up=1,
                )
        return

    def get_user(
        self,
        typ: _Literal["user", "author", "committer"] = "user",
        scope: _Literal["system", "global", "local", "worktree", "process"] | None = None,
    ) -> tuple[str | None, str | None]:
        """
        Get the git username and email.
        """
        if typ == "user" and scope == "process":
            raise _exception.GitTidyInputError("'scope' cannot be 'process' when 'typ' is 'user'.")

        if scope == "process":
            name = _os.environ.get(f"GIT_{typ.upper()}_NAME")
            email = _os.environ.get(f"GIT_{typ.upper()}_EMAIL")
            return name, email

        cmd = ["config"]
        if scope:
            cmd.append(f"--{scope}")
        user = []
        for key in ["name", "email"]:
            result = self.run_command(
                [*cmd, f"{typ}.{key}"],
                raise_exit_code=False,
                log_title=f"Git: Get {typ} {key}",
                stack_up=1,
            )
            if result.code == 0:
                user.append(result.out)
            elif result.code == 1 and not result.out:
                user.append(None)
            else:
                raise _exception.GitTidyOperationError(
                    f"Failed to get {typ}.{key}")
        return tuple(user)

    def fetch_remote_branches_by_pattern(
        self,
        branch_pattern: _re.Pattern | None = None,
        remote_name: str = "origin",
        exists_ok: bool = False,
        not_fast_forward_ok: bool = False,
    ) -> None:
        remote_branches = self.run_command(
            ["branch", "-r"],
            log_title="Git: List Remote Branches",
            stack_up=1,
        ).out.splitlines()
        branch_names = []
        for remote_branch in remote_branches:
            remote_branch = remote_branch.strip()
            if remote_branch.startswith(f"{remote_name}/") and " -> " not in remote_branch:
                remote_branch = remote_branch.removeprefix(f"{remote_name}/")
                if not branch_pattern or branch_pattern.match(remote_branch):
                    branch_names.append(remote_branch)
        self.fetch_remote_branches_by_name(
            branch_names=branch_names,
            remote_name=remote_name,
            exists_ok=exists_ok,
            not_fast_forward_ok=not_fast_forward_ok,
        )
        return

    def fetch_remote_branches_by_name(
        self,
        branch_names: str | list[str],
        remote_name: str = "origin",
        exists_ok: bool = False,
        not_fast_forward_ok: bool = False,
    ) -> None:
        if isinstance(branch_names, str):
            branch_names = [branch_names]
        if not exists_ok:
            curr_branch, other_branches = self.get_all_branch_names()
            local_branches = [curr_branch] + other_branches
            branch_names = [branch_name for branch_name in branch_names if branch_name not in local_branches]
        refspecs = [
            f"{'+' if not_fast_forward_ok else ''}{branch_name}:{branch_name}" for branch_name in branch_names
        ]
        self.run_command(
            ["fetch", remote_name, *refspecs],
            log_title="Git: Fetch Remote Branches",
            stack_up=1,
        )
        # for branch_name in branch_names:
        #     self._run(["git", "branch", "--track", branch_name, f"{remote_name}/{branch_name}"])
        # self._run(["git", "fetch", "--all"])
        # self._run(["git", "pull", "--all"])
        return

    def pull(self, fast_forward_only: bool = True) -> None:
        cmd = ["pull"]
        if fast_forward_only:
            cmd.append("--ff-only")
        self.run_command(cmd, log_title="Git: Pull", stack_up=1)
        return

    def get_commits(self, revision_range: str | None = None) -> list[dict[str, str | list[str]]]:
        """
        Get a list of commits.

        Parameters:
        - revision_range (str): The revision range to get commits from.

        Returns:
        - list[str]: A list of commit hashes.
        """
        marker_start = "<start new commit>"
        hash = "%H"
        author = "%an"
        date = "%ad"
        commit = "%B"
        marker_commit_end = "<end of commit message>"

        format = f"{marker_start}%n{hash}%n{author}%n{date}%n{commit}%n{marker_commit_end}"
        cmd = ["log", f"--pretty=format:{format}", "--name-only"]

        if revision_range:
            cmd.append(revision_range)
        result = self.run_command(cmd, log_title="Git: Get Commits", stack_up=1)

        pattern = _re.compile(
            rf"{_re.escape(marker_start)}\n(.*?)\n(.*?)\n(.*?)\n(.*?){_re.escape(marker_commit_end)}\n(.*?)(?:\n\n|$)",
            _re.DOTALL,
        )

        matches = pattern.findall(result.out)

        commits = []
        for match in matches:
            commit_info = {
                "hash": match[0].strip(),
                "author": match[1].strip(),
                "date": match[2].strip(),
                "msg": match[3].strip(),
                "files": list(filter(None, match[4].strip().split("\n"))),
            }
            commits.append(commit_info)
        return commits

    def current_branch_name(self) -> str:
        """Get the name of the current branch."""
        return self.run_command(
            ["branch", "--show-current"],
            log_title="Git: Show Current Branch",
            stack_up=1,
        ).out

    def branch_delete(self, branch_name: str, force: bool = False) -> None:
        cmd = ["branch", "-D" if force else "-d", branch_name]
        self.run_command(cmd, log_title="Git: Delete Branch", stack_up=1)
        return

    def branch_rename(self, new_name: str, force: bool = False) -> None:
        cmd = ["branch", "-M" if force else "-m", new_name]
        self.run_command(cmd, log_title="Git: Rename Branch", stack_up=1)
        return

    def get_all_branch_names(self) -> tuple[str, list[str]]:
        """Get the name of all branches."""
        result = self.run_command(["branch"], log_title="Git: Get Branch Names", stack_up=1)
        branches_other = []
        branch_current = []
        for branch in result.out.split("\n"):
            branch = branch.strip()
            if not branch:
                continue
            if branch.startswith("*"):
                branch_current.append(branch.removeprefix("*").strip())
            else:
                branches_other.append(branch)
        if len(branch_current) > 1:
            raise _exception.GitTidyOperationError("More than one current branch found.")
        return branch_current[0], branches_other

    def checkout(self, branch: str, create: bool = False, reset: bool = False, orphan: bool = False) -> None:
        """Checkout a branch."""
        cmd = ["checkout"]
        if reset:
            cmd.append("-B")
        elif create:
            cmd.append("-b")
        elif orphan:
            cmd.append("--orphan")
        cmd.append(branch)
        self.run_command(cmd, log_title="Git: Checkout Branch", stack_up=1)
        return

    def get_distance(self, ref_start: str, ref_end: str = "HEAD") -> int:
        """
        Get the distance between two commits.

        Parameters:
        - ref_start (str): The starting commit hash.
        - ref_end (str): The ending commit hash.

        Returns:
        - int: The distance between the two commits.
        """
        return int(
            self.run_command(
                ["rev-list", "--count", f"{ref_start}..{ref_end}"],
                log_title="Git: Get Distance",
                stack_up=1,
            ).out
        )

    def get_tags(self) -> list[list[str]]:
        """Get a list of tags reachable from the current commit

        This returns a list of tags ordered by the commit date (newest first).
        Each element is a list itself, containing all tags that point to the same commit.
        """
        logs = self.log(simplify_by_decoration=True, pretty="format:%D")
        tags_on_branch = (
            self.run_command(
                ["tag", "--merged"],
                log_title="Git: Get Tags on Branch",
                stack_up=1,
            ).out or ""
        ).splitlines()
        tags = []
        for line in logs.splitlines():
            potential_tags = line.split(", ")
            sub_list_added = False
            for potential_tag in potential_tags:
                if potential_tag.startswith("tag: "):
                    tag = potential_tag.removeprefix("tag: ")
                    if tag in tags_on_branch:
                        if not sub_list_added:
                            tags.append([])
                            sub_list_added = True
                        tags[-1].append(tag)
        return tags

    def get_remotes(self) -> dict[str, dict[str, str]]:
        """
        Remote URLs of the git repository.

        Returns
        -------
        A dictionary where the keys are the remote names and
        the values are dictionaries of purpose:URL pairs.
        Example:

        {
            "origin": {
                "push": "git@github.com:owner/repo-name.git",
                "fetch": "git@github.com:owner/repo-name.git",
            },
            "upstream": {
                "push": "https://github.com/owner/repo-name.git",
                "fetch": "https://github.com/owner/repo-name.git"
            }
        }
        """
        out = self.run_command(["remote", "-v"], log_title="Git: Get Remotes", stack_up=1).out or ""
        remotes = {}
        for remote in out.splitlines():
            remote_name, url, purpose_raw = remote.split()
            purpose = purpose_raw.removeprefix("(").removesuffix(")")
            remote_dict = remotes.setdefault(remote_name, {})
            if purpose in remote_dict:
                raise _exception.GitTidyOperationError(
                    f"Duplicate remote purpose '{purpose}' for remote '{remote_name}'."
                )
            remote_dict[purpose] = url
        return remotes

    def get_remote_repo_name(
        self,
        remote_name: str = "origin",
        remote_purpose: str = "push",
        fallback_name: bool = True,
        fallback_purpose: bool = True,
    ) -> tuple[str, str] | None:
        def extract_repo_name_from_url(url):
            # Regular expression pattern for extracting repo name from GitHub URL
            pattern = _re.compile(r"github\.com[/:]([\w\-]+)/([\w\-.]+?)(?:\.git)?$")
            match = pattern.search(url)
            if not match:
                return
            owner, repo = match.groups()[0:2]
            return owner, repo

        remotes = self.get_remotes()
        if not remotes:
            return
        if remote_name in remotes:
            if remote_purpose in remotes[remote_name]:
                repo_name = extract_repo_name_from_url(remotes[remote_name][remote_purpose])
                if repo_name:
                    return repo_name
            if fallback_purpose:
                for _remote_purpose, remote_url in remotes[remote_name].items():
                    repo_name = extract_repo_name_from_url(remote_url)
                    if repo_name:
                        return repo_name
        if fallback_name:
            for _remote_name, data in remotes.items():
                if remote_purpose in data:
                    repo_name = extract_repo_name_from_url(data[remote_purpose])
                    if repo_name:
                        return repo_name
                for _remote_purpose, url in data.items():
                    if _remote_purpose != remote_purpose:
                        repo_name = extract_repo_name_from_url(url)
                        if repo_name:
                            return repo_name
        return

    def get_remote_default_branch(
        self,
        remote_name: str = "origin",
    ) -> str | None:
        """Get the default branch of the remote repository.

        Parameters
        ----------
        remote_name : str, default: "origin"
            The name of the remote repository.

        Returns
        -------
        str | None
            The name of the default branch, or None if not found.
        """
        self.run_command(["remote", "set-head", remote_name, "--auto"], log_title="Git: Update Remote Head", stack_up=1)
        prefix = f"refs/remotes/{remote_name}/"
        result = self.run_command(
            ["symbolic-ref", f"{prefix}HEAD"],
            log_title="Git: Get Remote Default Branch",
            stack_up=1,
        ).out
        if not result:
            return None
        return result.removeprefix(prefix)

    def check_gitattributes(self) -> bool:
        command = ["sh", "-c", "git ls-files | git check-attr -a --stdin | grep 'text: auto'"]
        result = _pyshellman.run(
            command=command,
            cwd=self._path,
            raise_execution=True,
            raise_exit_code=True,
            raise_stderr=True,
            text_output=True,
        )
        return not result.out

    def file_at_ref(self, ref: str, path: str | _Path, raise_missing: bool = True) -> str | None:
        """Get the content of a file at a specific Git reference."""
        result = self.run_command(
            ["show", f"{ref}:{path}"],
            log_title="Git: Get File at Reference",
            raise_exit_code=raise_missing,
            stack_up=1,
        )
        if result.err or result.code != 0:
            if raise_missing:
                raise _exception.GitTidyOperationError(
                    f"Failed to get file '{path}' at reference '{ref}'."
                )
            return
        return result.out

    def discard_changes(self, path: str | _Path = ".") -> None:
        """Revert all uncommitted changes in the specified path, back to the state of the last commit."""
        self.run_command(["checkout", "--", str(path)], log_title="Git: Discard Changes", stack_up=1)
        return

    def stash(
        self, include: _Literal["tracked", "untracked", "all"] = "all", name: str = "Stashed by GitTidy"
    ) -> None:
        """Stash changes in the working directory.

        This takes the modified files, stages them and saves them on a stack of unfinished changes
        that can be reapplied at any time.

        Parameters
        ----------
        name : str, default: "Stashed by RepoDynamics"
            The name of the stash.
        include : {'tracked', 'untracked', 'all'}, default: 'all'
            Which files to include in the stash.

            - 'tracked': Stash tracked files only.
            - 'untracked': Stash tracked and untracked files.
            - 'all': Stash all files, including ignored files.
        """
        command = ["stash"]
        if include in ["untracked", "all"]:
            command.extend(["save", "--include-untracked" if include == "untracked" else "--all"])
        if name:
            command.append(str(name))
        self.run_command(command, log_title="Git: Stash Changes", stack_up=1)
        return

    def stash_pop(self) -> None:
        """Reapply the most recently stashed changes and remove the stash from the stack.

        This will take the changes stored in the stash and apply them back to the working directory,
        removing the stash from the stack.
        """
        self.run_command(
            ["stash", "pop"],
            log_title="Git: Pop Stash",
            raise_exit_code=False,
            log_level_exit_code=self._shell_runner.log_level_stderr,
            stack_up=1,
        )
        return
