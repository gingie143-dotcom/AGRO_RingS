import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-0000000000000000000000000000"
os.environ["SERVICE_TOKEN"] = "test-service-token-000000000000000000000000"
os.environ["ADMIN_PASSWORD"] = "test-password-0000"
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from sqlalchemy import event
from fastapi.testclient import TestClient
from app.db import Base, session
from app.main import app, login_limit
from app.security import bootstrap


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session_db:
        bootstrap(session_db)
        yield session_db
    engine.dispose()


@pytest.fixture
def client(db):
    app.dependency_overrides[session] = lambda: db
    app.dependency_overrides[login_limit] = lambda: None
    c = TestClient(app)
    result = c.post("/api/auth/login", json={"username": "admin", "password": "test-password-0000"})
    assert result.status_code == 200, result.text
    c.headers["x-csrf-token"] = c.cookies["csrf"]
    yield c
    c.close()
    app.dependency_overrides.clear()
