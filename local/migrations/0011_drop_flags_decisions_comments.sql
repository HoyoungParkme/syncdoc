BEGIN;

-- Running upgrade 0010 -> 0011

DROP TABLE comments;

DROP TABLE propagation_decisions;

DROP TABLE flags;

UPDATE alembic_version SET version_num='0011' WHERE alembic_version.version_num = '0010';

COMMIT;

