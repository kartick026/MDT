"""
GitHub Webhook payload schemas.

GitHub sends raw JSON directly — not a wrapper. These models map
the actual GitHub Push Event payload structure.
Reference: https://docs.github.com/en/webhooks/webhook-events-and-payloads#push
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


# ---------------------------------------------------------------------------
# GitHub push event sub-models
# ---------------------------------------------------------------------------

class GitHubUser(BaseModel):
    """Minimal GitHub user/author object"""
    name: str = ""
    email: str = ""
    username: str = ""


class GitHubCommit(BaseModel):
    """A single commit inside a push event"""
    id: str
    message: str
    timestamp: str = ""
    url: str = ""
    author: GitHubUser = Field(default_factory=GitHubUser)
    added: List[str] = Field(default_factory=list)
    removed: List[str] = Field(default_factory=list)
    modified: List[str] = Field(default_factory=list)


class GitHubRepository(BaseModel):
    """Repository info inside a push event"""
    id: int = 0
    name: str = ""
    full_name: str = ""
    clone_url: str = ""
    html_url: str = ""
    private: bool = False

    model_config = {"extra": "ignore"}


class GitHubPusher(BaseModel):
    name: str = ""
    email: str = ""


# ---------------------------------------------------------------------------
# Top-level GitHub event payloads
# ---------------------------------------------------------------------------

class GitHubPushPayload(BaseModel):
    """
    Real GitHub push event payload.
    Only fields MDT needs are declared; everything else is ignored.
    """
    ref: str                                        # e.g. "refs/heads/main"
    before: str = ""                                # SHA before the push
    after: str = ""                                 # SHA after the push (head commit)
    repository: GitHubRepository = Field(default_factory=GitHubRepository)
    pusher: GitHubPusher = Field(default_factory=GitHubPusher)
    commits: List[GitHubCommit] = Field(default_factory=list)
    head_commit: Optional[GitHubCommit] = None

    model_config = {"extra": "ignore"}

    @property
    def branch(self) -> str:
        """Extract branch name from ref string"""
        return self.ref.replace("refs/heads/", "")

    @property
    def commit_sha(self) -> str:
        return self.after or (self.head_commit.id if self.head_commit else "")

    @property
    def repo_url(self) -> str:
        return self.repository.clone_url or self.repository.html_url

    @property
    def author(self) -> str:
        return self.pusher.name or (
            self.head_commit.author.username if self.head_commit else "unknown"
        )

    @property
    def commit_message(self) -> str:
        if self.head_commit:
            return self.head_commit.message
        if self.commits:
            return self.commits[-1].message
        return ""

    def all_changed_files(self) -> List[Dict[str, Any]]:
        """
        Collect every file touched across all commits in this push,
        with the change type (added / modified / removed) for each.
        Files changed in multiple commits are deduplicated; the last
        seen change_type wins.
        """
        seen: Dict[str, str] = {}
        for commit in self.commits:
            for path in commit.added:
                seen[path] = "added"
            for path in commit.modified:
                seen[path] = "modified"
            for path in commit.removed:
                seen[path] = "removed"
        return [{"path": p, "change_type": ct} for p, ct in seen.items()]


class GitHubPingPayload(BaseModel):
    """GitHub sends a ping event when a webhook is first configured"""
    zen: str = ""
    hook_id: int = 0
    hook: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "ignore"}



