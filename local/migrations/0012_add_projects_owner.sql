BEGIN;

-- Running upgrade 0011 -> 0012

ALTER TABLE projects ADD COLUMN owner_user_id INTEGER;

UPDATE projects p SET owner_user_id = COALESCE( (SELECT r.registered_by_user_id FROM repositories r WHERE r.project_id = p.id), (SELECT min(id) FROM users));

ALTER TABLE projects ALTER COLUMN owner_user_id SET NOT NULL;

ALTER TABLE projects ADD CONSTRAINT fk_projects_owner_user_id_users FOREIGN KEY(owner_user_id) REFERENCES users (id);

CREATE INDEX ix_projects_owner_user_id ON projects (owner_user_id);

UPDATE alembic_version SET version_num='0012' WHERE alembic_version.version_num = '0011';

COMMIT;

