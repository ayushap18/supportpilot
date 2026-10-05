from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from supportpilot.storage import Base


class GitHubConnectionRow(Base):
    __tablename__ = "github_connections"
    workspace_id: Mapped[str] = mapped_column(String, primary_key=True)
    token: Mapped[str] = mapped_column(Text)
    login: Mapped[str] = mapped_column(String)
    scopes: Mapped[str] = mapped_column(String)


class GitHubOAuthRow(Base):
    __tablename__ = "github_oauth_states"
    state: Mapped[str] = mapped_column(String, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    reviewer_id: Mapped[str] = mapped_column(String)
    binding: Mapped[str] = mapped_column(String)
    verifier: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GitHubRepositoryRow(Base):
    __tablename__ = "github_repositories"
    __table_args__ = (UniqueConstraint("workspace_id", "github_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    github_id: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)


class GitHubIssueRow(Base):
    __tablename__ = "github_ticket_issues"
    __table_args__ = (UniqueConstraint("workspace_id", "repository_id", "ticket_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String, index=True)
    repository_id: Mapped[str] = mapped_column(String, index=True)
    ticket_id: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
