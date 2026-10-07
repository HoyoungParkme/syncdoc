BEGIN;

-- Running upgrade 0001 -> 0002

ALTER TABLE versions ADD COLUMN via VARCHAR(8) DEFAULT 'github' NOT NULL;

ALTER TABLE versions ALTER COLUMN via DROP DEFAULT;

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

COMMIT;

