BEGIN;

-- Running upgrade 0016 -> 0017

ALTER TABLE users ADD COLUMN kind VARCHAR(12) DEFAULT 'github' NOT NULL;

UPDATE users SET kind = 'placeholder' WHERE github_user_id IS NULL;

UPDATE alembic_version SET version_num='0017' WHERE alembic_version.version_num = '0016';

COMMIT;

