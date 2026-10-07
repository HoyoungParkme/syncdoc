BEGIN;

-- Running upgrade 0008 -> 0009

ALTER TABLE repositories ADD COLUMN fetch_error VARCHAR(300);

UPDATE alembic_version SET version_num='0009' WHERE alembic_version.version_num = '0008';

COMMIT;

