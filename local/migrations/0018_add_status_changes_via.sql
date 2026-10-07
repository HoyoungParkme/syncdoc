BEGIN;

-- Running upgrade 0017 -> 0018

ALTER TABLE status_changes ADD COLUMN via VARCHAR(8) DEFAULT 'web' NOT NULL;

UPDATE alembic_version SET version_num='0018' WHERE alembic_version.version_num = '0017';

COMMIT;

