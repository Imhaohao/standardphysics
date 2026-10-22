CREATE TABLE vision_cache (
    key        text PRIMARY KEY,
    reply      jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
