BEGIN;

-- Running upgrade 0009 -> 0010

ALTER TABLE documents ADD COLUMN trashed_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE documents ADD COLUMN trashed_by_user_id INTEGER;

ALTER TABLE documents ADD FOREIGN KEY(trashed_by_user_id) REFERENCES users (id);

CREATE INDEX ix_documents_trashed_by_user_id ON documents (trashed_by_user_id);

UPDATE alembic_version SET version_num='0010' WHERE alembic_version.version_num = '0009';

COMMIT;

