BEGIN;

-- Running upgrade 0012 -> 0013

ALTER TABLE repositories ADD COLUMN hook_id INTEGER;

ALTER TABLE repositories ADD COLUMN hook_error VARCHAR(300);

UPDATE alembic_version SET version_num='0013' WHERE alembic_version.version_num = '0012';

COMMIT;

