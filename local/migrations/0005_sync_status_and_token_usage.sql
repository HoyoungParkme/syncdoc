BEGIN;

-- Running upgrade 0004 -> 0005

ALTER TABLE repositories ADD COLUMN behind_by INTEGER;

ALTER TABLE repositories ADD COLUMN fetched_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE access_tokens ADD COLUMN last_used_at TIMESTAMP WITH TIME ZONE;

UPDATE alembic_version SET version_num='0005' WHERE alembic_version.version_num = '0004';

COMMIT;

