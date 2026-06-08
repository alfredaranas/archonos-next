from archonos.cli.main import main


def test_init_status_healthcheck(tmp_path, capsys):
    assert main(["init", "--path", str(tmp_path)]) == 0
    assert (tmp_path / ".archonos" / "archonos.db").exists()

    assert main(["status", "--path", str(tmp_path)]) == 0
    status_output = capsys.readouterr().out
    assert "Database Status: ready" in status_output
    assert "Knowledge Count: 0" in status_output

    assert main(["healthcheck", "--path", str(tmp_path)]) == 0
    health_output = capsys.readouterr().out
    assert "Filesystem: ok" in health_output
    assert "Database: ok" in health_output
