CREATE TABLE users (
    id CHAR(36) NOT NULL,
    username VARCHAR(50) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    updated_at TIMESTAMP(6) NOT NULL,
    CONSTRAINT pk_users PRIMARY KEY (id),
    CONSTRAINT uk_users_username UNIQUE (username)
);

-- Existing conversations are preserved under a deliberately non-login owner.
-- A later administrative migration can reassign them to real users if needed.
INSERT INTO users (id, username, password_hash, created_at, updated_at)
VALUES (
    '00000000-0000-0000-0000-000000000000',
    '__legacy_history_owner__',
    'NO_LOGIN_CREDENTIAL',
    CURRENT_TIMESTAMP(6),
    CURRENT_TIMESTAMP(6)
);

ALTER TABLE conversations
    ADD COLUMN user_id CHAR(36) NULL;

UPDATE conversations
SET user_id = '00000000-0000-0000-0000-000000000000'
WHERE user_id IS NULL;

ALTER TABLE conversations
    MODIFY COLUMN user_id CHAR(36) NOT NULL;

ALTER TABLE conversations
    ADD CONSTRAINT fk_conversations_user
        FOREIGN KEY (user_id)
        REFERENCES users (id);

CREATE INDEX idx_conversations_user_updated
    ON conversations (user_id, updated_at, id);
