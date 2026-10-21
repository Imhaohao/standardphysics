ALTER TABLE scan_answers
    ADD COLUMN source text NOT NULL DEFAULT 'owner' CHECK (source IN ('owner', 'photo')),
    ADD COLUMN confidence double precision NOT NULL DEFAULT 1,
    ADD COLUMN photo_artifact_id uuid REFERENCES artifacts (id) ON DELETE SET NULL;
