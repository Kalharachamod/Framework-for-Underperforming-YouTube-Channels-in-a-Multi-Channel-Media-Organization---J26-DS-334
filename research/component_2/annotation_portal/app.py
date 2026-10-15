"""Streamlit interface for Component 2 human annotation."""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit may execute this file by path with the entry-point directory as
# sys.path[0]. Add the repository root explicitly so package imports work from
# both the repository root and a Cloud-style file launch.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import pandas as pd

from research.component_2.src.annotation import DEMAND_SUBTYPES
from research.component_2.annotation_portal.assignments import (
    create_development_annotators,
    generate_assignments,
    load_annotation_comments,
    section_options,
)
from research.component_2.annotation_portal.auth import ResumeAttemptLimiter
from research.component_2.annotation_portal.config import load_config
from research.component_2.annotation_portal.db import DatabaseConnectionError
from research.component_2.annotation_portal.local_store import LocalAnnotationStore
from research.component_2.annotation_portal.supabase_store import SupabaseAnnotationStore
from research.component_2.annotation_portal.validation import AnnotationResponse


RESUME_LIMITER = ResumeAttemptLimiter()


def main() -> None:
    try:
        import streamlit as st
    except ImportError as exc:  # pragma: no cover - exercised manually
        raise SystemExit("Streamlit is not installed. Run: pip install streamlit") from exc

    st.set_page_config(page_title="Component 2 Annotation Portal", layout="centered")
    try:
        config = load_config(_read_streamlit_secrets(st))
    except (ValueError, DatabaseConnectionError) as exc:
        st.error(str(exc))
        st.stop()
    st.title("Component 2 Annotation Portal")

    try:
        store = _load_store(config)
    except DatabaseConnectionError:
        st.error("The annotation database is temporarily unavailable. Please try again later.")
        st.stop()

    participant = _current_participant(st, store)
    if participant is None:
        _render_session_start(st, store, config)
        st.stop()

    st.caption(f"Session active for {participant.display_name} · {participant.section_label}")
    if st.session_state.get("new_return_code"):
        st.success("Your private return code was created. Save it before closing this page.")
        st.code(st.session_state.new_return_code)
        st.caption("This code resumes only your own answers. Name-only identification is not verified authentication.")
    if st.button("Leave this session"):
        _clear_participant_state(st)
        st.rerun()

    assigned = store.assigned_comments_for_participant(participant.participant_id)
    if not assigned:
        st.warning("No comments are assigned to this section.")
        st.stop()

    progress = store.progress_for_participant(participant.participant_id)
    st.progress(progress["saved"] / progress["assigned"] if progress["assigned"] else 0)
    st.write(f"Saved {progress['saved']} of {progress['assigned']} assigned comments.")

    if "comment_index" not in st.session_state:
        st.session_state.comment_index = _first_incomplete_index(assigned)
    st.session_state.comment_index = max(0, min(st.session_state.comment_index, len(assigned) - 1))
    current = assigned[st.session_state.comment_index]

    _render_context(st, current, st.session_state.comment_index + 1, len(assigned))
    response = _render_response_form(st, current, participant.participant_id)

    col_prev, col_save, col_next = st.columns(3)
    with col_prev:
        if st.button("Previous", disabled=st.session_state.comment_index == 0):
            st.session_state.comment_index -= 1
            st.rerun()
    with col_save:
        if st.button("Save and Next", type="primary"):
            try:
                store.save_participant_response(participant.participant_id, current["comment_id"], response)
            except (ValueError, PermissionError, DatabaseConnectionError) as exc:
                st.error(f"Response was not saved: {exc}")
            else:
                st.session_state.new_return_code = ""
                st.success("Saved")
                if st.session_state.comment_index < len(assigned) - 1:
                    st.session_state.comment_index += 1
                st.rerun()
    with col_next:
        if st.button("Next", disabled=st.session_state.comment_index == len(assigned) - 1):
            st.session_state.comment_index += 1
            st.rerun()

    with st.expander("Review my progress"):
        review = pd.DataFrame(assigned)[["position", "comment_id", "demand_label", "spam_status", "is_submitted"]]
        st.dataframe(review, use_container_width=True, hide_index=True)

    if store.progress_for_participant(participant.participant_id)["saved"] == len(assigned):
        st.success("All assigned comments have saved responses. You can still review and edit them.")


def _read_streamlit_secrets(st) -> dict[str, object]:
    keys = {
        "COMPONENT2_ANNOTATION_MODE",
        "COMPONENT2_ANNOTATION_RUN_ID",
        "COMPONENT2_ASSIGNMENT_SEED",
        "COMPONENT2_PORTAL_SECRET",
        "COMPONENT2_DB_CONNECT_TIMEOUT",
        "SUPABASE_DB_URL",
    }
    try:
        return {key: st.secrets[key] for key in keys if key in st.secrets}
    except Exception:
        return {}


def _load_store(config):
    if config.mode == "supabase":
        store = SupabaseAnnotationStore(
            config.supabase_db_url,
            run_id=config.annotation_run_id,
            connect_timeout=config.db_connect_timeout,
        )
        store.ping()
        return store
    comments = load_annotation_comments(config.annotation_csv_path)
    assignments = generate_assignments(comments, seed=config.assignment_seed)
    annotators = create_development_annotators(config.portal_secret)
    store = LocalAnnotationStore(config.local_db_path)
    store.initialize(comments, assignments, annotators)
    return store


def _render_session_start(st, store, config) -> None:
    st.info("Enter a display name and choose a section, or resume with your private return code.")
    st.caption("Names are for coordination only. They are not verified authentication.")
    _render_instructions(st)

    tab_start, tab_resume = st.tabs(["Start", "Resume"])
    options = section_options()
    labels = {option.label: option for option in options}

    with tab_start:
        display_name = st.text_input("Display name or nickname")
        selected_label = st.selectbox(
            "Section",
            list(labels.keys()),
            format_func=lambda value: f"{value} ({labels[value].assigned_count} comments)",
        )
        if st.button("Start annotation", type="primary"):
            try:
                participant = store.create_participant(
                    display_name,
                    labels[selected_label].section_id,
                    config.portal_secret,
                )
            except (ValueError, DatabaseConnectionError) as exc:
                st.error(str(exc))
            else:
                st.session_state.participant_id = participant.participant_id
                st.session_state.new_return_code = participant.return_code
                st.session_state.comment_index = 0
                st.rerun()

    with tab_resume:
        return_code = st.text_input("Private return code", type="password")
        if st.button("Resume annotation"):
            if not RESUME_LIMITER.allow():
                st.error("Too many resume attempts. Please wait a minute and try again.")
                return
            try:
                participant = store.resume_participant(return_code, config.portal_secret)
            except DatabaseConnectionError as exc:
                st.error(str(exc))
                return
            if participant is None:
                st.error("No active participant session matches that return code.")
            else:
                st.session_state.participant_id = participant.participant_id
                st.session_state.new_return_code = ""
                st.session_state.comment_index = _first_incomplete_index(
                    store.assigned_comments_for_participant(participant.participant_id)
                )
                st.rerun()


def _current_participant(st, store: LocalAnnotationStore):
    participant_id = st.session_state.get("participant_id")
    if not participant_id:
        return None
    participant = store.participant_by_id(participant_id)
    if participant is None:
        _clear_participant_state(st)
        return None
    return participant


def _clear_participant_state(st) -> None:
    for key in ("participant_id", "new_return_code", "comment_index"):
        if key in st.session_state:
            del st.session_state[key]


def _render_instructions(st) -> None:
    st.markdown("### Before you begin")
    st.markdown(
        "Read the video title and comment, check the video context when needed, and choose both labels. "
        "Work independently, save your private return code, and use `UNCLEAR` rather than guessing."
    )
    with st.expander("Quick label guide"):
        st.markdown(
            "**Demand**  \n"
            "- `DEMAND`: The commenter requests or suggests content, an explanation, another topic, or an improvement.  \n"
            "- `NON_DEMAND`: General feedback, reactions, or discussion without an identifiable content request.  \n"
            "- `UNCLEAR`: There is not enough information to determine the intention.\n\n"
            "**Spam**  \n"
            "- `SPAM`: Advertisements, suspicious promotions, scams, or unrelated self-promotion.  \n"
            "- `NOT_SPAM`: Genuine comments, feedback, opinions, or requests.  \n"
            "- `UNCLEAR`: There is not enough information."
        )
        st.markdown(
            "**Examples**  \n"
            "- English: `English subtitles please` -> `DEMAND`; `Good video` -> `NON_DEMAND`.  \n"
            "- Sinhala: `මේ ගැන තව වීඩියෝ කරන්න` (make another video about this) -> `DEMAND`.  \n"
            "- Singlish: `Part 2 ekak one` (need a part 2) -> `DEMAND`; `Ado meka patta` (great video) -> `NON_DEMAND`.  \n"
            "- Praise alone is not unmet demand. Topic-specific interest or a clear request may be demand."
        )


def _render_context(st, row: dict, position: int, total: int) -> None:
    st.subheader(f"Comment {position} of {total}")
    st.write(f"**Channel:** {row.get('channel_name', '')}")
    st.write(f"**Video:** {row.get('video_title', '')}")
    if row.get("video_url"):
        st.link_button("Open YouTube video", row["video_url"])
    if row.get("video_description"):
        with st.expander("Video description"):
            st.write(row["video_description"])
    if row.get("parent_comment_text"):
        with st.expander("Parent comment"):
            st.write(row["parent_comment_text"])

    st.markdown("### Comment")
    st.write(row.get("original_text", ""))
    if row.get("cleaned_text") and row.get("cleaned_text") != row.get("original_text"):
        with st.expander("Cleaned text"):
            st.write(row["cleaned_text"])


def _render_response_form(st, row: dict, participant_id: str) -> AnnotationResponse:
    existing_demand = row.get("demand_label") or "UNCLEAR"
    existing_spam = row.get("spam_status") or "UNCLEAR"
    key_prefix = f"{participant_id}_{row.get('comment_id', '')}"
    demand_label = st.radio(
        "Audience demand classification",
        ["DEMAND", "NON_DEMAND", "UNCLEAR"],
        index=["DEMAND", "NON_DEMAND", "UNCLEAR"].index(existing_demand),
        help="DEMAND means a content-related request, preference, suggestion, unmet need, or actionable improvement.",
        key=f"demand_{key_prefix}",
    )
    demand_subtype = ""
    if demand_label == "DEMAND":
        current_subtype = row.get("demand_subtype") if row.get("demand_subtype") in DEMAND_SUBTYPES else DEMAND_SUBTYPES[0]
        demand_subtype = st.selectbox(
            "Demand subtype",
            DEMAND_SUBTYPES,
            index=DEMAND_SUBTYPES.index(current_subtype),
            key=f"subtype_{key_prefix}",
        )
    spam_status = st.radio(
        "Spam classification",
        ["SPAM", "NOT_SPAM", "UNCLEAR"],
        index=["SPAM", "NOT_SPAM", "UNCLEAR"].index(existing_spam),
        help="Spam is separate from demand. Do not mark genuine content requests as spam only because they are unusual or short.",
        key=f"spam_{key_prefix}",
    )
    annotation_notes = st.text_area(
        "Annotation notes",
        value=row.get("annotation_notes") or "",
        key=f"notes_{key_prefix}",
    )
    spam_notes = st.text_area(
        "Spam notes",
        value=row.get("spam_notes") or "",
        key=f"spam_notes_{key_prefix}",
    )
    submit = st.checkbox(
        "Mark this response as ready for review",
        value=bool(row.get("is_submitted")),
        key=f"submitted_{key_prefix}",
    )
    return AnnotationResponse(
        demand_label=demand_label,
        spam_status=spam_status,
        demand_subtype=demand_subtype,
        annotation_notes=annotation_notes,
        spam_notes=spam_notes,
        is_submitted=submit,
    )


def _first_incomplete_index(rows: list[dict]) -> int:
    for index, row in enumerate(rows):
        if not row.get("demand_label") or not row.get("spam_status"):
            return index
    return 0


if __name__ == "__main__":
    main()
