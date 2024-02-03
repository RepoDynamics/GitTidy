import json
from typing import Literal, Optional
from pathlib import Path
import re
from contextlib import contextmanager
from loggerman import logger
import pyshellman as _pyshellman
from repodynamics.version import PEP440SemVer

from gittidy import exception as _exception


class Git:
    _COMMITTER_USERNAME = "RepoDynamicsBot"
    _COMMITTER_EMAIL = "146771514+RepoDynamicsBot@users.noreply.github.com"

    @logger.sectioner("Initialize Git API")
    def __init__(
        self,
        path: str | Path = ".",
        user: tuple[str, str] | None = None,
        user_scope: Literal["system", "global", "local", "worktree"] = "global",
    ):
        try:
            git_version = _pyshellman.run(["git", "version", "--build-options"])
        except _pyshellman.exception.PyShellManError:
            raise _exception.GitTidyGitNotFoundError()
        logger.info(code_title="Git version", code=git_version.output)

        try:
            repo_root_path = _pyshellman.run(
                ["git", "-C", str(Path(path).resolve()), "rev-parse", "--show-toplevel"]
            )
        except _pyshellman.exception.PyShellManError:
            raise _exception.GitTidyNoGitRepositoryError(path)
        self._path = Path(repo_root_path.output)
        logger.info(code_title="Git repository path", code=self._path)

        if user:
            self.set_user(username=user[0], email=user[1], scope=user_scope)
        return

    def push(
        self, target: str = None, ref: str = None, set_upstream: bool = False, force_with_lease: bool = False
    ) -> str | None:
        command = ["git", "push"]
        if set_upstream:
            if not target:
                self._logger.error("No target provided while setting upstream.")
            command.extend(["--set-upstream", target, self.current_branch_name()])
        elif target:
            command.append(target)
        if ref:
            command.append(ref)
        if force_with_lease:
            command.append("--force-with-lease")
        with self._temp_committer():
            self.run_command(command)
        return self.commit_hash_normal()

    def commit(
        self,
        message: str = "",
        stage: Literal["all", "tracked", "none"] = "all",
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
            self._logger.error("No commit message provided.")
        commit_cmd = ["git", "commit"]
        if amend:
            commit_cmd.append("--amend")
            if not message:
                commit_cmd.append("--no-edit")
        if allow_empty:
            commit_cmd.append("--allow-empty")
        for msg_line in message.splitlines():
            if msg_line:
                commit_cmd.extend(["-m", msg_line])

        if stage != "none":
            flag = "-A" if stage == "all" else "-u"
            with self._temp_committer():
                self.run_command(["git", "add", flag])
        commit_hash = None
        if allow_empty or self.has_changes(check_type="staged"):
            with self._temp_committer():
                out, err, code = self.run_command(commit_cmd, raise_exit_code=False)
            if code != 0:
                with self._temp_committer():
                    self.run_command(commit_cmd)
            commit_hash = self.commit_hash_normal()
            self._logger.success(f"Committed changes. Commit hash: {commit_hash}")
        else:
            self._logger.attention(f"No changes to commit.")
        return commit_hash

    def create_tag(
        self,
        tag: str,
        message: str = None,
        push_target: str = "origin",
    ):
        cmd = ["git", "tag"]
        if not message:
            cmd.append(tag)
        else:
            cmd.extend(["-a", tag, "-m", message])
        with self._temp_committer():
            self.run_command(cmd)
        out = self.run_command(["git", "show", tag])
        if push_target:
            self.push(target=push_target, ref=tag)
        return out

    def has_changes(self, check_type: Literal["staged", "unstaged", "all"] = "all") -> bool:
        """Checks for git changes.

        Parameters:
        - check_type (str): Can be 'staged', 'unstaged', or 'both'. Default is 'both'.

        Returns:
        - bool: True if changes are detected, False otherwise.
        """
        commands = {"staged": ["git", "diff", "--quiet", "--cached"], "unstaged": ["git", "diff", "--quiet"]}
        if check_type == "all":
            return any(self.run_command(cmd, raise_exit_code=False)[2] != 0 for cmd in commands.values())
        return self.run_command(commands[check_type], raise_exit_code=False)[2] != 0

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
        changes = self.run_command(["git", "diff", "--name-status", ref_start, ref_end]).splitlines()
        for change in changes:
            key, *paths = change.split("\t")
            if key in key_def:
                out.setdefault(key_def[key], []).extend(paths)
                continue
            key, similarity = key[0], int(key[1:])
            if key not in ["C", "R"]:
                self._logger.error(f"Unknown change type '{change}'.")
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
        return self.run_command(["git", "rev-parse", f"HEAD~{parent}"])

    def describe(
        self, abbrev: int | None = None, first_parent: bool = True, match: str | None = None
    ) -> str | None:
        cmd = ["git", "describe"]
        if abbrev is not None:
            cmd.append(f"--abbrev={abbrev}")
        if first_parent:
            cmd.append("--first-parent")
        if match:
            cmd.extend(["--match", match])
        out, err, code = self.run_command(command=cmd, raise_exit_code=False)
        return out if code == 0 else None

    def log(
        self,
        number: int | None = None,
        simplify_by_decoration: bool = True,
        tags: bool | str = True,
        pretty: str | None = "format:%D",
        date: str | None = None,
        revision_range: str | None = None,
        paths: str | list[str] | None = None,
    ):
        cmd = ["git", "log"]
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
        return self.run_command(cmd)

    def set_user(
        self,
        username: str | None,
        email: str | None,
        user_type: Literal["user", "author", "committer"] = "user",
        scope: Literal["system", "global", "local", "worktree"] | None = "global",
    ):
        """
        Set the git username and email.
        """
        cmd = ["git", "config"]
        if scope:
            cmd.append(f"--{scope}")
        if not ((username is None or isinstance(username, str)) and (email is None or isinstance(email, str))):
            raise ValueError("username and email must be either a string or None.")
        for key, val in [("name", username), ("email", email)]:
            if val is None:
                self.run_command([*cmd, "--unset", f"{user_type}.{key}"])
            else:
                self.run_command([*cmd, f"{user_type}.{key}", val])
        return

    def get_user(
        self,
        user_type: Literal["user", "author", "committer"] = "user",
        scope: Optional[Literal["system", "global", "local", "worktree"]] = None,
    ) -> tuple[str | None, str | None]:
        """
        Get the git username and email.
        """
        cmd = ["git", "config"]
        if scope:
            cmd.append(f"--{scope}")
        user = []
        for key in ["name", "email"]:
            out, err, code = self.run_command([*cmd, f"{user_type}.{key}"], raise_exit_code=False)
            if code == 0:
                user.append(out)
            elif code == 1 and not out:
                user.append(None)
            else:
                self._logger.error(f"Failed to get {user_type}.{key}.", details=err, exit_code=code)
        return tuple(user)

    def fetch_remote_branches_by_pattern(
        self,
        branch_pattern: re.Pattern | None = None,
        remote_name: str = "origin",
        exists_ok: bool = False,
        not_fast_forward_ok: bool = False,
    ):
        remote_branches = self.run_command(["git", "branch", "-r"]).splitlines()
        branch_names = []
        for remote_branch in remote_branches:
            remote_branch = remote_branch.strip()
            if remote_branch.startswith(f"{remote_name}/") and " -> " not in remote_branch:
                remote_branch = remote_branch.removeprefix(f"{remote_name}/")
                if not branch_pattern or branch_pattern.match(remote_branch):
                    branch_names.append(remote_branch)
        return self.fetch_remote_branches_by_name(
            branch_names=branch_names,
            remote_name=remote_name,
            exists_ok=exists_ok,
            not_fast_forward_ok=not_fast_forward_ok,
        )

    def fetch_remote_branches_by_name(
        self,
        branch_names: str | list[str],
        remote_name: str = "origin",
        exists_ok: bool = False,
        not_fast_forward_ok: bool = False,
    ):
        if isinstance(branch_names, str):
            branch_names = [branch_names]
        if not exists_ok:
            curr_branch, other_branches = self.get_all_branch_names()
            local_branches = [curr_branch] + other_branches
            branch_names = [branch_name for branch_name in branch_names if branch_name not in local_branches]
        refspecs = [
            f"{'+' if not_fast_forward_ok else ''}{branch_name}:{branch_name}" for branch_name in branch_names
        ]
        self.run_command(["git", "fetch", remote_name, *refspecs])
        # for branch_name in branch_names:
        #     self._run(["git", "branch", "--track", branch_name, f"{remote_name}/{branch_name}"])
        # self._run(["git", "fetch", "--all"])
        # self._run(["git", "pull", "--all"])
        return

    def pull(self, fast_forward_only: bool = True):
        cmd = ["git", "pull"]
        if fast_forward_only:
            cmd.append("--ff-only")
        return self.run_command(cmd)

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
        cmd = ["git", "log", f"--pretty=format:{format}", "--name-only"]

        if revision_range:
            cmd.append(revision_range)
        out = self.run_command(cmd)

        pattern = re.compile(
            rf"{re.escape(marker_start)}\n(.*?)\n(.*?)\n(.*?)\n(.*?){re.escape(marker_commit_end)}\n(.*?)(?:\n\n|$)",
            re.DOTALL,
        )

        matches = pattern.findall(out)
        self._logger.success(f"Found {len(matches)} commits.", json.dumps(matches, indent=3))

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
        return self.run_command(["git", "branch", "--show-current"])

    def branch_delete(self, branch_name: str, force: bool = False):
        cmd = ["git", "branch", "-D" if force else "-d", branch_name]
        self.run_command(cmd)
        return

    def branch_rename(self, new_name: str, force: bool = False):
        cmd = ["git", "branch", "-M" if force else "-m", new_name]
        self.run_command(cmd)
        return

    def get_all_branch_names(self) -> tuple[str, list[str]]:
        """Get the name of the current branch."""
        branches_str = self.run_command(["git", "branch"])
        branches_other = []
        branch_current = []
        for branch in branches_str.split("\n"):
            branch = branch.strip()
            if not branch:
                continue
            if branch.startswith("*"):
                branch_current.append(branch.removeprefix("*").strip())
            else:
                branches_other.append(branch)
        if len(branch_current) > 1:
            raise RuntimeError("More than one current branch found.")
        return branch_current[0], branches_other

    def checkout(self, branch: str, create: bool = False, reset: bool = False, orphan: bool = False):
        """Checkout a branch."""
        cmd = ["git", "checkout"]
        if reset:
            cmd.append("-B")
        elif create:
            cmd.append("-b")
        elif orphan:
            cmd.append("--orphan")
        cmd.append(branch)
        return self.run_command(cmd)

    def get_distance(self, ref_start: str, ref_end: str = "HEAD") -> int:
        """
        Get the distance between two commits.

        Parameters:
        - ref_start (str): The starting commit hash.
        - ref_end (str): The ending commit hash.

        Returns:
        - int: The distance between the two commits.
        """
        return int(self.run_command(["git", "rev-list", "--count", f"{ref_start}..{ref_end}"]))

    def get_tags(self) -> list[list[str]]:
        """Get a list of tags reachable from the current commit

        This returns a list of tags ordered by the commit date (newest first).
        Each element is a list itself, containing all tags that point to the same commit.
        """
        tags_on_branch = self.run_command(["git", "tag", "--merged"]).splitlines()
        output = self.log(simplify_by_decoration=True, pretty="format:%D")
        tags = []
        for line in output.splitlines():
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

    def get_latest_version(self, tag_prefix: str, dev_only: bool = False) -> PEP440SemVer | None:
        tags_lists = self.get_tags()
        if not tags_lists:
            return
        for tags_list in tags_lists:
            ver_tags = []
            for tag in tags_list:
                if tag.startswith(tag_prefix):
                    ver_tags.append(PEP440SemVer(tag.removeprefix(tag_prefix)))
            if ver_tags:
                if dev_only:
                    ver_tags = sorted(ver_tags, reverse=True)
                    for ver_tag in ver_tags:
                        if ver_tag.release_type == "dev":
                            return ver_tag
                else:
                    return max(ver_tags)
        return

    @property
    def remotes(self) -> dict:
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
        out = self.run_command(["git", "remote", "-v"])
        remotes = {}
        for remote in out.splitlines():
            remote_name, url, purpose_raw = remote.split()
            purpose = purpose_raw.removeprefix("(").removesuffix(")")
            remote_dict = remotes.setdefault(remote_name, {})
            if purpose in remote_dict:
                self._logger.error(f"Duplicate remote purpose '{purpose}' for remote '{remote_name}'.")
            remote_dict[purpose] = url
        return remotes

    def repo_name(
        self,
        remote_name: str = "origin",
        remote_purpose: str = "push",
        fallback_name: bool = True,
        fallback_purpose: bool = True,
    ) -> tuple[str, str] | None:
        def extract_repo_name_from_url(url):
            # Regular expression pattern for extracting repo name from GitHub URL
            pattern = re.compile(r"github\.com[/:]([\w\-]+)/([\w\-.]+?)(?:\.git)?$")
            match = pattern.search(url)
            if not match:
                self._logger.attention(f"Failed to extract repo name from URL '{url}'.")
                return None
            owner, repo = match.groups()[0:2]
            return owner, repo

        remotes = self.remotes
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

    def check_gitattributes(self):
        command = ["sh", "-c", "git ls-files | git check-attr -a --stdin | grep 'text: auto'"]
        out = self.run_command(command)
        if out:
            return False
        return True

    def file_at_hash(self, commit_hash: str, path: str | Path, raise_missing: bool = True) -> str | None:
        out, err, code = self.run_command(["git", "show", f"{commit_hash}:{path}"], raise_exit_code=raise_missing)
        if err or code != 0:
            if raise_missing:
                self._logger.error(f"Failed to get file '{path}' at commit '{commit_hash}'.", details=err)
            return None
        return out

    def discard_changes(self, path: str | Path = "."):
        """Revert all uncommitted changes in the specified path, back to the state of the last commit."""
        return self.run_command(["git", "checkout", "--", str(path)])

    def stash(
        self, name: str = "Stashed by RepoDynamics", include: Literal["tracked", "untracked", "all"] = "all"
    ):
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
        command = ["git", "stash"]
        if include in ["untracked", "all"]:
            command.extend(["save", "--include-untracked" if include == "untracked" else "--all"])
        if name:
            command.append(str(name))
        return self.run_command(command)

    def stash_pop(self):
        """Reapply the most recently stashed changes and remove the stash from the stack.

        This will take the changes stored in the stash and apply them back to the working directory,
        removing the stash from the stack.
        """
        return self.run_command(["git", "stash", "pop"], raise_exit_code=False)

    @property
    def path_root(self) -> Path:
        return self._path

    @contextmanager
    def _temp_committer(self):
        committer_username, committer_email = self.get_user(user_type="committer", scope="local")
        if committer_username != self._COMMITTER_USERNAME or committer_email != self._COMMITTER_EMAIL:
            self.set_user(
                username=self._COMMITTER_USERNAME,
                email=self._COMMITTER_EMAIL,
                user_type="committer",
                scope="local",
            )
        yield
        if committer_username != self._COMMITTER_USERNAME or committer_email != self._COMMITTER_EMAIL:
            self.set_user(
                username=committer_username, email=committer_email, user_type="committer", scope="local"
            )
        return

    @contextmanager
    def temp_author(self, username: str = None, email: str = None):
        author_username, author_email = self.get_user(user_type="author", scope="local")
        username = username or self._COMMITTER_USERNAME
        email = email or self._COMMITTER_EMAIL
        if author_username != username or author_email != email:
            self.set_user(username=username, email=email, user_type="author", scope="local")
        yield
        if author_username != username or author_email != email:
            self.set_user(username=author_username, email=author_email, user_type="author", scope="local")
        return

    def run_command(
        self,
        command: list[str],
        raise_exit_code: bool = True,
        raise_stderr: bool = False,
        text_output: bool = True,
    ) -> _pyshellman.ShellOutput:
        result = _pyshellman.run(
            command=["git", *command],
            cwd=self._path,
            raise_execution=True,
            raise_exit_code=raise_exit_code,
            raise_stderr=raise_stderr,
            text_output=text_output,
        )
        logger.info("Run git command", msg=result.summary, code_title="Result", code=result)
        return result
