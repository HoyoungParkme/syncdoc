"""SYNC-DOM-002 2.7 열거형 · 2.8 내부 타입(DTO). 카드 A가 쓰는 것만.

열거형은 DB enum이 아니라 varchar + 앱 검증(SYNC-DOM-003 설계 규칙). 타입은 여기 한 곳에만.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from syncdoc.core.account.models import AccessToken, User


class DocType(StrEnum):
    RFQ = "RFQ"
    PRD = "PRD"
    SCN = "SCN"
    UC = "UC"
    INFRA = "INFRA"
    DOM = "DOM"
    UI = "UI"
    API = "API"
    SEQ = "SEQ"
    MS = "MS"
    CODE = "CODE"
    STD = "STD"


class DocStatus(StrEnum):
    draft = "draft"
    review = "review"
    approved = "approved"


class AuthorKind(StrEnum):
    human = "human"
    agent = "agent"


class FlagKind(StrEnum):
    needs_check = "needs_check"
    broken_ref = "broken_ref"
    upstream_impact = "upstream_impact"


class Propagation(StrEnum):
    propagate = "propagate"
    skip = "skip"
    undecided = "undecided"


class Entry(StrEnum):
    mcp = "mcp"
    web_revert = "web_revert"
    web_status = "web_status"
    github = "github"


@dataclass(frozen=True)
class Author:
    kind: AuthorKind
    user: User
    instructed_by: User | None
    via: Entry


@dataclass(frozen=True)
class IssuedToken:
    token: AccessToken
    raw: str


@dataclass(frozen=True)
class ChangedFile:
    path: str
    status: str  # A | M | D
    commit_hash: str
    author_login: str
    message: str


@dataclass(frozen=True)
class Commit:
    hash: str
    login: str
    date: datetime
    message: str


@dataclass(frozen=True)
class GithubUser:
    id: int
    login: str
    name: str
