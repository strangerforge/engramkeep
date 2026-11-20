"""CLI tests for the fix/fixes troubleshooting commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engramkeep.cli import main


def test_fix_and_fixes_roundtrip(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "fix",
                "Android keystore mismatch",
                "--solution",
                "Enable v2 signing",
                "--project",
                "my-app",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "my-app" in out

    assert main(["fixes", "keystore"]) == 0
    out = capsys.readouterr().out
    assert "keystore" in out.lower()
    assert "v2 signing" in out


def test_fixes_json_output(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["fix", "err one", "--solution", "fix one", "--project", "demo"])
    capsys.readouterr()
    assert main(["fixes", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["error"] == "err one"
    assert payload[0]["project"] == "demo"


def test_fixes_without_query_lists_newest(
    cli_home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(["fix", "first problem", "--solution", "first fix", "--project", "one"])
    main(["fix", "second problem", "--solution", "second fix", "--project", "two"])
    capsys.readouterr()
    assert main(["fixes"]) == 0
    out = capsys.readouterr().out
    assert out.index("two") < out.index("one")


def test_fix_requires_solution(cli_home: Path) -> None:
    with pytest.raises(SystemExit):
        main(["fix", "some error"])


def test_fix_rejects_blank_error(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fix", "   ", "--solution", "some fix"]) == 1
    assert "error" in capsys.readouterr().err.lower()


def test_fixes_limit_matrix(cli_home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(["fix", "port 8080 busy", "--solution", "Stop old process", "--project", "one"]) == 0
    )
    assert main(["fix", "port 8080 conflict", "--solution", "Use 8081", "--project", "two"]) == 0
    capsys.readouterr()

    # limit=0 returns empty result list
    assert main(["fixes", "port 8080", "--limit", "0", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []

    # limit=1 caps results to 1
    assert main(["fixes", "port 8080", "--limit", "1", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 1

    # limit larger than matches returns all matches
    assert main(["fixes", "port 8080", "--limit", "50", "--json"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 2

    # negative limit fails with argparse usage error (exit code 2)
    with pytest.raises(SystemExit) as excinfo:
        main(["fixes", "port 8080", "--limit", "-3"])
    assert excinfo.value.code == 2
    assert ">= 0" in capsys.readouterr().err

    # help text documents valid range
    with pytest.raises(SystemExit) as help_exc:
        main(["fixes", "--help"])
    assert help_exc.value.code == 0
    assert ">= 0" in capsys.readouterr().out
