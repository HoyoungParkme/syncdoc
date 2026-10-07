BEGIN;

-- Running upgrade 0007 -> 0008

ALTER TABLE flags ADD COLUMN target_version_id INTEGER;

ALTER TABLE flags ADD CONSTRAINT flags_target_version_id_fkey FOREIGN KEY(target_version_id) REFERENCES versions (id);

ALTER TABLE flags ALTER CONSTRAINT flags_target_version_id_fkey DEFERRABLE INITIALLY IMMEDIATE;

CREATE INDEX ix_flags_target_version_id ON flags (target_version_id);

UPDATE alembic_version SET version_num='0008' WHERE alembic_version.version_num = '0007';

COMMIT;

