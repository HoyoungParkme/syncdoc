BEGIN;

-- Running upgrade 0002 -> 0003

ALTER TABLE versions ADD COLUMN message TEXT DEFAULT '' NOT NULL;

ALTER TABLE versions ALTER COLUMN message DROP DEFAULT;

UPDATE alembic_version SET version_num='0003' WHERE alembic_version.version_num = '0002';

COMMIT;

