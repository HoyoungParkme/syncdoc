BEGIN;

-- Running upgrade 0005 -> 0006

CREATE TABLE commit_emails (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    email VARCHAR(255) NOT NULL, 
    added_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    UNIQUE (email)
);

CREATE INDEX ix_commit_emails_user_id ON commit_emails (user_id);

UPDATE alembic_version SET version_num='0006' WHERE alembic_version.version_num = '0005';

COMMIT;

