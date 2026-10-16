# Human Review Decision Guide

This guide is for the offline feasibility experiment only. It does not change
the production portal labels `DEMAND`, `NON_DEMAND`, or `UNCLEAR`, and it does
not create labels for the existing 300-comment annotation sample.

## Review sequence

1. Read the original comment and the available video title and description.
2. Decide whether the comment expresses a future content opportunity, rather
   than merely reacting to the current video.
3. Select one primary signal and record secondary signals where useful.
4. Set `candidate_for_content_demand` only when the evidence is actionable
   enough to merit later demand review.
5. Use `UNCLEAR` when the available context is insufficient. Do not infer the
   author's intention or treat a keyword as proof.

## Experimental signal classes

| Class | Meaning | Illustrative examples |
| --- | --- | --- |
| `EXPLICIT_CONTENT_REQUEST` | Direct request for another video, topic, guest, update, or coverage. | “Please make another video about Sri Lankan cricket.” / “මේ ගැන තව video එකක් කරන්න.” / “Meka gena thawath video ekak danna.” |
| `CONTENT_CHANGE_PREFERENCE` | Request for a format, language, subtitles, length, or presentation change. | “Please add Sinhala subtitles.” / “සිංහල subtitles දාන්න.” / “Full video ekak danna.” |
| `INFORMATION_NEED` | Request for explanation, details, clarification, or a follow-up. | “Can you explain what happened?” / “මේක ගැන විස්තර කියන්න.” / “Meka gena wisthara kiyannako.” |
| `CONTENT_QUALITY_FEEDBACK` | Specific feedback that could guide production improvement. | “The audio is too low.” / “ශබ්දය පැහැදිලි නැහැ.” / “Sound eka madi.” |
| `TOPICAL_INTEREST_OR_DISCUSSION` | Interest in or discussion of the current topic without a clear future-content request. | “Is this news true?” / “මේක ඇත්තද?” / “Me news eka aththada?” |
| `ORDINARY_REACTION` | Praise, criticism, thanks, emojis, or a short reaction without an actionable request. | “Great video.” / “හොඳයි.” / “🔥” |
| `SPAM_OR_IRRELEVANT` | Promotional advertising, scams, phishing, unrelated self-promotion, or bot-like solicitation. | “Earn Rs. 50,000 daily! Contact me for investment opportunities.” |
| `UNCLEAR` | Evidence is too incomplete or ambiguous for a confident decision. | “Check my page” when its purpose is unclear. |

These examples are illustrative and are not verified samples from either local
dataset.

## Candidate flag boundaries

Set the candidate flag for direct content requests, clear presentation or
format changes, information requests that imply further coverage, and specific
quality feedback. A topic mention alone is not unmet demand. A question about
the current video's facts is not automatically a content request. Praise,
criticism, short comments, emojis, links, capital letters, unusual Unicode,
Sinhala, English, Singlish, and code-mixed text are not automatically spam or
demand.

Keep `primary_signal` and `candidate_for_content_demand` separate. A comment
may be `TOPICAL_INTEREST_OR_DISCUSSION` without being a candidate, while a
quality comment can be a candidate without asking for a new topic. Preserve
negation and uncertainty in notes instead of rewriting the comment into a
stronger claim.

## Independent review

Two annotators should review the blinded CSV independently. They should not
see the baseline predicted class or the sampling group. Record a short note
for ambiguous cases and keep the original `comment_id` unchanged. After both
reviews, calculate agreement by signal and adjudicate disagreements using the
video context and these rules. Do not copy the experimental labels into the
production annotation CSV.
