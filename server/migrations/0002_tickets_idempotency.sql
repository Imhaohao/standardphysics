CREATE TABLE live_tickets (
    ticket_hash text PRIMARY KEY,
    user_id     uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    scan_id     uuid NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    expires_at  timestamptz NOT NULL
);
CREATE INDEX live_tickets_expiry_idx ON live_tickets (expires_at);

CREATE TABLE idempotency_keys (
    user_id      uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    scope        text NOT NULL,
    key          text NOT NULL,
    request_hash text NOT NULL,
    status       integer,
    response     jsonb,
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, scope, key)
);
CREATE INDEX idempotency_created_idx ON idempotency_keys (created_at);
