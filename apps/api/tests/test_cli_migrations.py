from __future__ import annotations

from types import SimpleNamespace

from app import cli


class _FakeConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, dict[str, int] | None]] = []

    def execute(self, statement, params=None):
        self.statements.append((str(statement), params))


class _FakeConnectionContext:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection

    def __enter__(self) -> _FakeConnection:
        return self.connection

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _FakeEngine:
    def __init__(self) -> None:
        self.connection = _FakeConnection()

    def connect(self) -> _FakeConnectionContext:
        return _FakeConnectionContext(self.connection)


def test_db_upgrade_uses_postgres_advisory_lock(monkeypatch, capsys):
    calls: list[tuple[str, str]] = []
    engine = _FakeEngine()

    monkeypatch.setattr(cli, "_migration_lock_engine", lambda: engine)
    monkeypatch.setattr(
        cli.command,
        "upgrade",
        lambda cfg, target: calls.append(("upgrade", target)),
    )

    assert cli.cmd_db_upgrade(SimpleNamespace()) == 0

    assert calls == [("upgrade", "head")]
    assert "pg_advisory_lock" in engine.connection.statements[0][0]
    assert "pg_advisory_unlock" in engine.connection.statements[-1][0]
    assert engine.connection.statements[0][1] == {"lock_id": cli.ALEMBIC_ADVISORY_LOCK_ID}
    assert "app-schema Alembic upgrade complete" in capsys.readouterr().out


def test_db_upgrade_releases_advisory_lock_on_failure(monkeypatch):
    engine = _FakeEngine()

    monkeypatch.setattr(cli, "_migration_lock_engine", lambda: engine)

    def fail_upgrade(_cfg, _target):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli.command, "upgrade", fail_upgrade)

    try:
        cli.cmd_db_upgrade(SimpleNamespace())
    except RuntimeError as exc:
        assert str(exc) == "boom"
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("cmd_db_upgrade should propagate migration failures")

    assert "pg_advisory_unlock" in engine.connection.statements[-1][0]


def test_db_verify_current_succeeds_when_database_matches_head(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_script_heads", lambda: ("abc123",))
    monkeypatch.setattr(cli, "_database_current_heads", lambda: ("abc123",))

    assert cli.cmd_db_verify_current(SimpleNamespace()) == 0

    assert "Database schema is at Alembic head: abc123" in capsys.readouterr().out


def test_db_verify_current_fails_when_database_is_behind(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_script_heads", lambda: ("head123",))
    monkeypatch.setattr(cli, "_database_current_heads", lambda: ("old456",))

    assert cli.cmd_db_verify_current(SimpleNamespace()) == 1

    output = capsys.readouterr().out
    assert "Database schema is not at Alembic head" in output
    assert "current: old456" in output
    assert "head: head123" in output


def test_db_heads_fails_when_multiple_heads(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_script_heads", lambda: ("head_a", "head_b"))

    assert cli.cmd_db_heads(SimpleNamespace()) == 1
    output = capsys.readouterr().out
    assert "Alembic has multiple heads" in output
    assert "head_a" in output and "head_b" in output
