CREATE TABLE users (
    id            uuid PRIMARY KEY,
    email         text,
    password_hash text,
    apple_sub     text,
    created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX users_email_lower_key ON users (lower(email)) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX users_apple_sub_key ON users (apple_sub) WHERE apple_sub IS NOT NULL;

CREATE TABLE sessions (
    token_hash   text PRIMARY KEY,
    user_id      uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at   timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz NOT NULL,
    last_used_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX sessions_user_idx ON sessions (user_id);

CREATE TABLE scans (
    id         uuid PRIMARY KEY,
    user_id    uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name       text NOT NULL,
    site_name  text,
    status     text NOT NULL DEFAULT 'capturing'
               CHECK (status IN ('capturing', 'finishing', 'complete', 'failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX scans_user_idx ON scans (user_id, created_at DESC);

CREATE TABLE scan_rooms (
    scan_id       uuid NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    room_id       text NOT NULL,
    captured_room jsonb,
    observations  jsonb NOT NULL DEFAULT '{}'::jsonb,
    finalized     boolean NOT NULL DEFAULT false,
    updated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (scan_id, room_id)
);

CREATE TABLE uploads (
    id           uuid PRIMARY KEY,
    scan_id      uuid NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    kind         text NOT NULL,
    filename     text NOT NULL,
    content_type text NOT NULL,
    size_bytes   bigint NOT NULL CHECK (size_bytes > 0),
    part_size    bigint NOT NULL,
    part_count   integer NOT NULL,
    s3_key       text NOT NULL,
    s3_upload_id text NOT NULL,
    state        text NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'complete', 'aborted')),
    created_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz
);
CREATE INDEX uploads_scan_idx ON uploads (scan_id);

CREATE TABLE artifacts (
    id           uuid PRIMARY KEY,
    scan_id      uuid NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    upload_id    uuid NOT NULL REFERENCES uploads (id) ON DELETE CASCADE,
    kind         text NOT NULL,
    filename     text NOT NULL,
    content_type text NOT NULL,
    s3_key       text NOT NULL,
    size_bytes   bigint NOT NULL,
    sha256       text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX artifacts_scan_idx ON artifacts (scan_id);

CREATE TABLE assessments (
    id         uuid PRIMARY KEY,
    scan_id    uuid NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    findings   jsonb NOT NULL,
    summary    jsonb NOT NULL,
    timings_ms jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX assessments_scan_idx ON assessments (scan_id, created_at DESC);

CREATE TABLE jobs (
    id            uuid PRIMARY KEY,
    kind          text NOT NULL,
    payload       jsonb NOT NULL DEFAULT '{}'::jsonb,
    state         text NOT NULL DEFAULT 'queued'
                  CHECK (state IN ('queued', 'running', 'done', 'dead')),
    attempts      integer NOT NULL DEFAULT 0,
    max_attempts  integer NOT NULL DEFAULT 5,
    deadline_secs integer NOT NULL DEFAULT 600,
    run_at        timestamptz NOT NULL DEFAULT now(),
    locked_until  timestamptz,
    locked_by     text,
    last_error    text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz
);
CREATE INDEX jobs_claim_idx ON jobs (state, run_at);
