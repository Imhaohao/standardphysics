CREATE TABLE scan_answers (
    scan_id     uuid NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    subject_id  text NOT NULL,
    metric      text NOT NULL,
    value       jsonb NOT NULL,
    answered_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (scan_id, subject_id, metric)
);

CREATE TABLE scan_shares (
    token      text PRIMARY KEY,
    scan_id    uuid NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX scan_shares_scan_idx ON scan_shares (scan_id, created_at DESC);
