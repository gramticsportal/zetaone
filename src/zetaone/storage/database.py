# zetaone database storage

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker, declarative_base

# ---------------------------------------------------------------------------
# Connection config placeholder
# ---------------------------------------------------------------------------
# Load from environment / config in production:
#   DATABASE_URL, DATABASE_POOL_SIZE, DATABASE_MAX_OVERFLOW, etc.
# Multi-tenant: tenant-specific connection strings or schema selection
# ---------------------------------------------------------------------------

import os as _os

DATABASE_URL = _os.environ.get("DATABASE_URL", "postgresql://localhost:5432/zetaone")
DATABASE_POOL_SIZE = 5
DATABASE_MAX_OVERFLOW = 10
DATABASE_ECHO = False  # Set True for SQL debugging


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

Base = declarative_base()


# ---------------------------------------------------------------------------
# Engine and session factory
# ---------------------------------------------------------------------------

_engine = None
_SessionLocal = None
SessionLocal = None  # Set by get_session_factory() on first call


def get_engine():
    """Create or return the database engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            DATABASE_URL,
            pool_size=DATABASE_POOL_SIZE,
            max_overflow=DATABASE_MAX_OVERFLOW,
            echo=DATABASE_ECHO,
        )
    return _engine


def get_session_factory():
    """Create or return the session factory (SessionLocal)."""
    global _SessionLocal, SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
        SessionLocal = _SessionLocal
    return _SessionLocal




def create_all_tables() -> None:
    """Create all tables defined in models. Call after importing all models."""
    from zetaone.models import (  # noqa: F401 - register models
        Tenant,
        Asset,
        Signal,
        Evidence,
        Verdict,
        AuditEvent,
    )

    Base.metadata.create_all(bind=get_engine())


# ---------------------------------------------------------------------------
# Multi-tenant context
# ---------------------------------------------------------------------------
# Store current tenant_id in context for row-level filtering.
# Use set_tenant_id() before queries; tables will filter by tenant_id.
# ---------------------------------------------------------------------------

_tenant_id_ctx: ContextVar[str | None] = ContextVar("tenant_id", default=None)


def set_tenant_id(tenant_id: str | None) -> None:
    """Set the current tenant ID for multi-tenant queries."""
    _tenant_id_ctx.set(tenant_id)


def get_tenant_id() -> str | None:
    """Get the current tenant ID from context."""
    return _tenant_id_ctx.get()


# ---------------------------------------------------------------------------
# Session manager
# ---------------------------------------------------------------------------


class Database:
    """Database session manager with multi-tenant support."""

    def __init__(self) -> None:
        self._session_factory = get_session_factory()

    @contextmanager
    def session(self, tenant_id: str | None = None) -> Generator[Session, None, None]:
        """
        Yield a database session. Optionally set tenant context for multi-tenant queries.

        Usage:
            db = Database()
            with db.session(tenant_id="tenant-123") as session:
                ...
        """
        token = None
        if tenant_id is not None:
            token = _tenant_id_ctx.set(tenant_id)
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            if token is not None:
                _tenant_id_ctx.reset(token)

    def get_session(self, tenant_id: str | None = None) -> Session:
        """
        Return a session. Caller must commit/rollback and close.

        For multi-tenant: call set_tenant_id(tenant_id) before queries.
        """
        if tenant_id is not None:
            set_tenant_id(tenant_id)
        return self._session_factory()


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------

def get_base():
    """Return the declarative Base class for model definitions."""
    return Base
