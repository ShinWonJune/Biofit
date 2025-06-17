-- db/init/006_token_usage.sql
CREATE TABLE IF NOT EXISTS token_usage (
    id               SERIAL PRIMARY KEY,
    uid              TEXT,
    prompt_tokens    INT,
    completion_tokens INT,
    created_at       TIMESTAMPTZ DEFAULT now()
);
