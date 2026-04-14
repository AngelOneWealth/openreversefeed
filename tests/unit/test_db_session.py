from openreversefeed.db.session import Base, make_engine, make_session_factory


def test_base_has_metadata_schema():
    assert Base.metadata.schema == "openreversefeed"


def test_engine_and_session_factory_construct(tmp_path):
    # Use SQLite for this unit test — we don't need Postgres here
    url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = make_engine(url, schema=None)
    assert engine is not None
    factory = make_session_factory(engine)
    with factory() as session:
        assert session.is_active
