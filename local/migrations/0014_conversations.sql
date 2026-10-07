BEGIN;

-- Running upgrade 0013 -> 0014

CREATE TABLE conversations (
    id SERIAL NOT NULL, 
    project_id INTEGER NOT NULL, 
    user_id INTEGER NOT NULL, 
    title VARCHAR(80) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(project_id) REFERENCES projects (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_conversations_project_user ON conversations (project_id, user_id);

CREATE INDEX ix_conversations_user_id ON conversations (user_id);

CREATE TABLE turns (
    id SERIAL NOT NULL, 
    conversation_id INTEGER NOT NULL, 
    seq INTEGER NOT NULL, 
    question TEXT NOT NULL, 
    answer TEXT, 
    progress JSONB DEFAULT '[]'::jsonb NOT NULL, 
    context_item_ids JSONB DEFAULT '[]'::jsonb NOT NULL, 
    error VARCHAR(300), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_turns_conversation_seq UNIQUE (conversation_id, seq), 
    FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
);

CREATE TABLE attachments (
    id SERIAL NOT NULL, 
    conversation_id INTEGER NOT NULL, 
    turn_id INTEGER, 
    user_id INTEGER NOT NULL, 
    name VARCHAR(200) NOT NULL, 
    mime VARCHAR(80) NOT NULL, 
    size INTEGER NOT NULL, 
    bytes BYTEA NOT NULL, 
    text_cache TEXT, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(conversation_id) REFERENCES conversations (id) ON DELETE CASCADE, 
    FOREIGN KEY(turn_id) REFERENCES turns (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_attachments_conversation ON attachments (conversation_id);

CREATE INDEX ix_attachments_turn_id ON attachments (turn_id);

CREATE INDEX ix_attachments_user_id ON attachments (user_id);

UPDATE alembic_version SET version_num='0014' WHERE alembic_version.version_num = '0013';

COMMIT;

