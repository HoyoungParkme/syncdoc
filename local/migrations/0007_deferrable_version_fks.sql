BEGIN;

-- Running upgrade 0006 -> 0007

ALTER TABLE propagation_decisions ALTER CONSTRAINT propagation_decisions_version_id_fkey DEFERRABLE INITIALLY IMMEDIATE;

ALTER TABLE flags ALTER CONSTRAINT flags_cause_version_id_fkey DEFERRABLE INITIALLY IMMEDIATE;

UPDATE alembic_version SET version_num='0007' WHERE alembic_version.version_num = '0006';

COMMIT;

