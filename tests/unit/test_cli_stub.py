from typer.testing import CliRunner

from openreversefeed.cli import app


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    output = result.stdout.lower()
    assert "openreversefeed" in output or "orf" in output


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout


def test_cli_migrate_stub_exits_nonzero():
    runner = CliRunner()
    result = runner.invoke(app, ["migrate"])
    assert result.exit_code == 1
    assert "not yet implemented" in result.stdout


def test_cli_process_stub_exits_nonzero():
    runner = CliRunner()
    result = runner.invoke(app, ["process", "some-file.csv"])
    assert result.exit_code == 1
    assert "not yet implemented" in result.stdout
