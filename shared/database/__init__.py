"""Shared online research database (Supabase PostgreSQL).

* ``connection``       configuration and connections (``SUPABASE_DB_URL``)
* ``migrate``          schema setup: ``python -m shared.database.migrate``
* ``repository``       insert / upsert / get / list for channels, videos, comments
* ``snapshot_export``  Supabase -> Parquet research snapshots

See docs/architecture/supabase.md.
"""
