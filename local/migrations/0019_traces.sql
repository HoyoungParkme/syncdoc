BEGIN;

-- Running upgrade 0018 -> 0019

CREATE TABLE traces (
    id SERIAL NOT NULL, 
    project_id INTEGER NOT NULL, 
    user_id INTEGER NOT NULL, 
    trace_key VARCHAR(64) NOT NULL, 
    kind VARCHAR(8) NOT NULL, 
    method VARCHAR(10), 
    path VARCHAR(500) NOT NULL, 
    status INTEGER, 
    error VARCHAR(300), 
    started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    ms INTEGER NOT NULL, 
    commit_hash VARCHAR(40), 
    event_count INTEGER NOT NULL, 
    truncated BOOLEAN DEFAULT false NOT NULL, 
    record JSONB NOT NULL, 
    received_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_traces_project_key UNIQUE (project_id, trace_key), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_traces_project_recent ON traces (project_id, id DESC);

CREATE INDEX ix_traces_user_id ON traces (user_id);

UPDATE alembic_version SET version_num='0019' WHERE alembic_version.version_num = '0018';

COMMIT;

