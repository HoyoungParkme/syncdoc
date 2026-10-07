BEGIN;

-- Running upgrade 0015 -> 0016

ALTER TABLE repositories ADD COLUMN storage VARCHAR(8) DEFAULT 'github' NOT NULL;

UPDATE alembic_version SET version_num='0016' WHERE alembic_version.version_num = '0015';

COMMIT;

