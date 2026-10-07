BEGIN;

-- Running upgrade 0003 -> 0004

ALTER TABLE repositories ADD COLUMN registered_by_user_id INTEGER;

UPDATE repositories SET registered_by_user_id = (SELECT min(id) FROM users);

ALTER TABLE repositories ALTER COLUMN registered_by_user_id SET NOT NULL;

ALTER TABLE repositories ADD CONSTRAINT fk_repositories_registered_by_user_id_users FOREIGN KEY(registered_by_user_id) REFERENCES users (id);

CREATE INDEX ix_repositories_registered_by_user_id ON repositories (registered_by_user_id);

UPDATE alembic_version SET version_num='0004' WHERE alembic_version.version_num = '0003';

COMMIT;

