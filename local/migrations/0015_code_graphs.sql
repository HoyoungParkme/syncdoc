BEGIN;

-- Running upgrade 0014 -> 0015

CREATE TABLE code_graphs (
    project_id INTEGER NOT NULL, 
    commit_hash VARCHAR(40), 
    source VARCHAR(10), 
    graph JSONB NOT NULL, 
    function_count INTEGER DEFAULT '0' NOT NULL, 
    call_count INTEGER DEFAULT '0' NOT NULL, 
    built_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    error VARCHAR(300), 
    PRIMARY KEY (project_id), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE
);

UPDATE alembic_version SET version_num='0015' WHERE alembic_version.version_num = '0014';

COMMIT;

