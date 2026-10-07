BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

CREATE TABLE projects (
    id SERIAL NOT NULL, 
    code VARCHAR(4) NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_projects_code CHECK (code ~ '^[A-Z]{1,4}$'), 
    UNIQUE (code)
);

CREATE TABLE users (
    id SERIAL NOT NULL, 
    github_login VARCHAR(50) NOT NULL, 
    github_user_id BIGINT, 
    display_name VARCHAR(100) NOT NULL, 
    github_token_encrypted BYTEA, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (github_login), 
    UNIQUE (github_user_id)
);

CREATE TABLE access_tokens (
    id SERIAL NOT NULL, 
    user_id INTEGER NOT NULL, 
    token_hash VARCHAR(64) NOT NULL, 
    label VARCHAR(50) NOT NULL, 
    issued_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    UNIQUE (token_hash)
);

CREATE INDEX ix_access_tokens_user_id ON access_tokens (user_id);

CREATE TABLE documents (
    id SERIAL NOT NULL, 
    project_id INTEGER NOT NULL, 
    doc_id VARCHAR(30) NOT NULL, 
    doc_type VARCHAR(10) NOT NULL, 
    status VARCHAR(10) NOT NULL, 
    current_body TEXT NOT NULL, 
    current_version_no INTEGER NOT NULL, 
    has_convention_error BOOLEAN DEFAULT false NOT NULL, 
    convention_error_detail TEXT, 
    incomplete_warnings TEXT, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_documents_version_no CHECK (current_version_no >= 1), 
    FOREIGN KEY(project_id) REFERENCES projects (id), 
    UNIQUE (doc_id)
);

CREATE INDEX ix_documents_has_convention_error ON documents (has_convention_error) WHERE has_convention_error;

CREATE INDEX ix_documents_project_id_doc_type ON documents (project_id, doc_type);

CREATE TABLE repositories (
    id SERIAL NOT NULL, 
    project_id INTEGER NOT NULL, 
    remote_url VARCHAR(300) NOT NULL, 
    workdir_path VARCHAR(300) NOT NULL, 
    last_processed_commit VARCHAR(40), 
    synced_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(project_id) REFERENCES projects (id), 
    UNIQUE (project_id)
);

CREATE TABLE comments (
    id SERIAL NOT NULL, 
    document_id INTEGER NOT NULL, 
    parent_comment_id INTEGER, 
    line_no INTEGER NOT NULL, 
    line_hash VARCHAR(64) NOT NULL, 
    body TEXT NOT NULL, 
    author_user_id INTEGER NOT NULL, 
    is_resolved BOOLEAN DEFAULT false NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    original_location VARCHAR(50), 
    PRIMARY KEY (id), 
    FOREIGN KEY(author_user_id) REFERENCES users (id), 
    FOREIGN KEY(document_id) REFERENCES documents (id), 
    FOREIGN KEY(parent_comment_id) REFERENCES comments (id)
);

CREATE INDEX ix_comments_author_user_id ON comments (author_user_id);

CREATE INDEX ix_comments_document_id_is_resolved ON comments (document_id, is_resolved);

CREATE INDEX ix_comments_parent_comment_id ON comments (parent_comment_id);

CREATE TABLE items (
    id SERIAL NOT NULL, 
    document_id INTEGER NOT NULL, 
    item_id VARCHAR(50) NOT NULL, 
    display_name VARCHAR(200), 
    is_deleted BOOLEAN DEFAULT false NOT NULL, 
    deleted_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(document_id) REFERENCES documents (id), 
    CONSTRAINT uq_items_document_id_item_id UNIQUE (document_id, item_id)
);

CREATE INDEX ix_items_document_id_is_deleted ON items (document_id, is_deleted);

CREATE TABLE status_changes (
    id SERIAL NOT NULL, 
    document_id INTEGER NOT NULL, 
    from_status VARCHAR(10), 
    to_status VARCHAR(10) NOT NULL, 
    changed_by_user_id INTEGER NOT NULL, 
    reason TEXT, 
    commit_hash VARCHAR(40), 
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(changed_by_user_id) REFERENCES users (id), 
    FOREIGN KEY(document_id) REFERENCES documents (id)
);

CREATE INDEX ix_status_changes_changed_by_user_id ON status_changes (changed_by_user_id);

CREATE INDEX ix_status_changes_document_id_changed_at ON status_changes (document_id, changed_at);

CREATE TABLE versions (
    id SERIAL NOT NULL, 
    document_id INTEGER NOT NULL, 
    version_no INTEGER NOT NULL, 
    commit_hash VARCHAR(40) NOT NULL, 
    body TEXT NOT NULL, 
    author_kind VARCHAR(10) NOT NULL, 
    author_user_id INTEGER NOT NULL, 
    instructed_by_user_id INTEGER, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(author_user_id) REFERENCES users (id), 
    FOREIGN KEY(document_id) REFERENCES documents (id), 
    FOREIGN KEY(instructed_by_user_id) REFERENCES users (id), 
    CONSTRAINT uq_versions_document_id_version_no UNIQUE (document_id, version_no)
);

CREATE INDEX ix_versions_author_user_id_created_at ON versions (author_user_id, created_at);

CREATE INDEX ix_versions_document_id_version_no_desc ON versions (document_id, version_no DESC);

CREATE INDEX ix_versions_instructed_by_user_id ON versions (instructed_by_user_id);

CREATE TABLE flags (
    id SERIAL NOT NULL, 
    kind VARCHAR(15) NOT NULL, 
    target_item_id INTEGER NOT NULL, 
    cause_item_id INTEGER, 
    cause_version_id INTEGER, 
    assignee_user_id INTEGER, 
    raised_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    resolved_by_user_id INTEGER, 
    resolved_at TIMESTAMP WITH TIME ZONE, 
    resolved_with_edit BOOLEAN, 
    PRIMARY KEY (id), 
    FOREIGN KEY(assignee_user_id) REFERENCES users (id), 
    FOREIGN KEY(cause_item_id) REFERENCES items (id), 
    FOREIGN KEY(cause_version_id) REFERENCES versions (id), 
    FOREIGN KEY(resolved_by_user_id) REFERENCES users (id), 
    FOREIGN KEY(target_item_id) REFERENCES items (id)
);

CREATE INDEX ix_flags_assignee_user_id_resolved_at ON flags (assignee_user_id, resolved_at);

CREATE INDEX ix_flags_cause_item_id ON flags (cause_item_id);

CREATE INDEX ix_flags_cause_version_id ON flags (cause_version_id);

CREATE INDEX ix_flags_kind_resolved_at ON flags (kind, resolved_at);

CREATE INDEX ix_flags_resolved_by_user_id ON flags (resolved_by_user_id);

CREATE INDEX ix_flags_target_item_id_resolved_at ON flags (target_item_id, resolved_at);

CREATE TABLE propagation_decisions (
    id SERIAL NOT NULL, 
    version_id INTEGER NOT NULL, 
    choice VARCHAR(12) NOT NULL, 
    affected_pks JSONB NOT NULL, 
    changed_pks JSONB NOT NULL, 
    reason TEXT, 
    decided_by_user_id INTEGER, 
    decided_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(decided_by_user_id) REFERENCES users (id), 
    FOREIGN KEY(version_id) REFERENCES versions (id), 
    UNIQUE (version_id)
);

CREATE INDEX ix_propagation_decisions_choice_undecided ON propagation_decisions (choice) WHERE choice = 'undecided';

CREATE INDEX ix_propagation_decisions_decided_by_user_id ON propagation_decisions (decided_by_user_id);

CREATE TABLE "references" (
    id SERIAL NOT NULL, 
    from_item_id INTEGER, 
    from_document_id INTEGER NOT NULL, 
    to_item_id INTEGER, 
    to_document_id INTEGER, 
    raw_target VARCHAR(100) NOT NULL, 
    is_missing BOOLEAN DEFAULT false NOT NULL, 
    extracted_version_id INTEGER NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT ck_references_target CHECK ((is_missing AND to_item_id IS NULL AND to_document_id IS NULL) OR (NOT is_missing AND ((to_item_id IS NULL) <> (to_document_id IS NULL)))), 
    FOREIGN KEY(extracted_version_id) REFERENCES versions (id), 
    FOREIGN KEY(from_document_id) REFERENCES documents (id), 
    FOREIGN KEY(from_item_id) REFERENCES items (id), 
    FOREIGN KEY(to_document_id) REFERENCES documents (id), 
    FOREIGN KEY(to_item_id) REFERENCES items (id)
);

CREATE INDEX ix_references_extracted_version_id ON "references" (extracted_version_id);

CREATE INDEX ix_references_from_document_id ON "references" (from_document_id);

CREATE INDEX ix_references_from_item_id ON "references" (from_item_id);

CREATE INDEX ix_references_is_missing ON "references" (is_missing) WHERE is_missing;

CREATE INDEX ix_references_to_document_id ON "references" (to_document_id);

CREATE INDEX ix_references_to_item_id ON "references" (to_item_id);

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

COMMIT;

