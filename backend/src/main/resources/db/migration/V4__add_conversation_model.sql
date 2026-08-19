ALTER TABLE conversations
    ADD COLUMN selected_model VARCHAR(40) NOT NULL
        DEFAULT 'STEP_FLASH_3_7';

CREATE INDEX idx_conversations_selected_model
    ON conversations (selected_model);
