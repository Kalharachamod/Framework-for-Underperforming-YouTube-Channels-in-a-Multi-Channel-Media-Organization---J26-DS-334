-- 0001_annotation_schema.sql
-- Component 2 annotation portal schema.
-- Prepared only; do not apply until reviewed and approved.

CREATE SCHEMA IF NOT EXISTS annotation;

CREATE TABLE annotation.annotation_runs (
    run_id              text PRIMARY KEY,
    source_name         text NOT NULL,
    assignment_seed     integer NOT NULL,
    comment_count       integer NOT NULL CHECK (comment_count = 300),
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE annotation.sections (
    run_id              text NOT NULL REFERENCES annotation.annotation_runs (run_id) ON DELETE RESTRICT,
    section_id          text NOT NULL,
    section_label       text NOT NULL,
    assignment_template text NOT NULL,
    assigned_count      integer NOT NULL CHECK (assigned_count IN (30, 300)),
    is_primary_mode     boolean NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, section_id),
    UNIQUE (run_id, assignment_template),
    CHECK (
        (is_primary_mode = true AND assigned_count = 300)
        OR (is_primary_mode = false AND assigned_count = 30)
    )
);

CREATE TABLE annotation.comments (
    run_id              text NOT NULL REFERENCES annotation.annotation_runs (run_id) ON DELETE RESTRICT,
    comment_id          text NOT NULL,
    channel_id          text NOT NULL,
    channel_name        text NOT NULL,
    video_id            text NOT NULL,
    video_title         text,
    video_description   text,
    video_url           text,
    parent_comment_text text,
    published_at        timestamptz,
    is_reply            boolean,
    original_text       text NOT NULL,
    cleaned_text        text,
    script_category     text NOT NULL,
    preprocessing_flags text,
    sampling_stratum    text,
    source_row_index    integer NOT NULL,
    created_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, comment_id)
);

CREATE TABLE annotation.section_assignments (
    run_id              text NOT NULL,
    section_id          text NOT NULL,
    comment_id          text NOT NULL,
    batch_name          text NOT NULL,
    position            integer NOT NULL CHECK (position > 0),
    assigned_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, section_id, comment_id),
    UNIQUE (run_id, section_id, position),
    FOREIGN KEY (run_id, section_id) REFERENCES annotation.sections (run_id, section_id) ON DELETE RESTRICT,
    FOREIGN KEY (run_id, comment_id) REFERENCES annotation.comments (run_id, comment_id) ON DELETE RESTRICT
);

CREATE TABLE annotation.participants (
    run_id              text NOT NULL,
    participant_id      text NOT NULL,
    display_name        text NOT NULL,
    section_id          text NOT NULL,
    participant_role    text NOT NULL CHECK (participant_role IN ('section_annotator', 'primary_researcher')),
    return_code_hash    text NOT NULL UNIQUE,
    active              boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, participant_id),
    UNIQUE (run_id, participant_id, section_id),
    FOREIGN KEY (run_id, section_id) REFERENCES annotation.sections (run_id, section_id) ON DELETE RESTRICT
);

CREATE TABLE annotation.responses (
    run_id              text NOT NULL,
    participant_id      text NOT NULL,
    section_id          text NOT NULL,
    comment_id          text NOT NULL,
    demand_label        text NOT NULL CHECK (demand_label IN ('DEMAND', 'NON_DEMAND', 'UNCLEAR')),
    spam_status         text NOT NULL CHECK (spam_status IN ('SPAM', 'NOT_SPAM', 'UNCLEAR')),
    demand_subtype      text NOT NULL DEFAULT '',
    annotation_notes    text NOT NULL DEFAULT '',
    spam_notes          text NOT NULL DEFAULT '',
    is_submitted        boolean NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, participant_id, comment_id),
    FOREIGN KEY (run_id, participant_id, section_id)
        REFERENCES annotation.participants (run_id, participant_id, section_id) ON DELETE RESTRICT,
    FOREIGN KEY (run_id, section_id, comment_id)
        REFERENCES annotation.section_assignments (run_id, section_id, comment_id) ON DELETE RESTRICT,
    CHECK (
        (demand_label = 'DEMAND' AND demand_subtype <> '')
        OR (demand_label <> 'DEMAND' AND demand_subtype = '')
    )
);

CREATE TABLE annotation.researcher_admins (
    admin_id            text PRIMARY KEY,
    auth_user_id        uuid UNIQUE,
    display_name        text NOT NULL,
    active              boolean NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE annotation.adjudications (
    run_id              text NOT NULL,
    comment_id          text NOT NULL,
    final_demand_label  text CHECK (final_demand_label IN ('DEMAND', 'NON_DEMAND', 'UNCLEAR')),
    final_spam_status   text CHECK (final_spam_status IN ('SPAM', 'NOT_SPAM', 'UNCLEAR')),
    final_demand_subtype text NOT NULL DEFAULT '',
    adjudication_notes  text NOT NULL DEFAULT '',
    adjudicated_by      text NOT NULL REFERENCES annotation.researcher_admins (admin_id) ON DELETE RESTRICT,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, comment_id),
    FOREIGN KEY (run_id, comment_id) REFERENCES annotation.comments (run_id, comment_id) ON DELETE RESTRICT
);

CREATE INDEX annotation_section_assignments_section_idx ON annotation.section_assignments (run_id, section_id, position);
CREATE INDEX annotation_participants_section_idx ON annotation.participants (run_id, section_id, active);
CREATE INDEX annotation_responses_comment_idx ON annotation.responses (run_id, comment_id);
CREATE INDEX annotation_responses_participant_idx ON annotation.responses (run_id, participant_id);
CREATE INDEX annotation_comments_video_idx ON annotation.comments (video_id);
