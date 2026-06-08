from archonos.storage.sqlite import database_ok, initialize_database, table_count


def test_initialize_database_creates_required_tables(tmp_path):
    db_path = tmp_path / ".archonos" / "archonos.db"

    initialize_database(db_path)

    assert db_path.exists()
    assert database_ok(db_path)
    assert table_count(db_path, "documents") == 0
    assert table_count(db_path, "memories") == 0
    assert table_count(db_path, "workflows") == 0
