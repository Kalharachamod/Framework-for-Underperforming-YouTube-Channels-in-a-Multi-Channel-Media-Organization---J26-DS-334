# Component 2 Canonical Annotation Schema v1

## Scope

Schema version `component2.audience-demand.v1` is the canonical contract for
new feasibility, development, and held-out annotation datasets. It preserves
the approved Component 2 objective while separating the comment's primary
audience signal from whether it contains actionable content demand.

This schema does not rewrite the historical 300-comment portal data or the
researcher-approved 40-comment calibration labels. It does not create labels
from rules, mappings, or model predictions.

## Independent decisions

The primary signal uses exactly one of these eight values:

- `EXPLICIT_CONTENT_REQUEST`
- `CONTENT_CHANGE_PREFERENCE`
- `INFORMATION_NEED`
- `CONTENT_QUALITY_FEEDBACK`
- `TOPICAL_INTEREST_OR_DISCUSSION`
- `ORDINARY_REACTION`
- `SPAM_OR_IRRELEVANT`
- `UNCLEAR`

Actionability is a separate `YES`, `NO`, or `UNCLEAR` decision. Requested
action, topic, format, request target, and evidence span explain that decision
without replacing it. Programme name and content type are contextual metadata,
not audience-demand labels.

`SPAM_OR_IRRELEVANT` records the primary audience-signal category. The separate
spam field records `SPAM`, `NOT_SPAM`, or `UNCLEAR`. A non-spam comment can be
irrelevant, so `SPAM_OR_IRRELEVANT` does not by itself imply `SPAM`. A confirmed
spam decision should ordinarily have primary signal `SPAM_OR_IRRELEVANT` and
actionability `NO`; exceptions require an adjudication note.

## Provenance and review fields

Each independent annotator has an identifier, workflow status, completion
timestamp, primary and secondary signals, actionability, requested action,
topic, format, request target, evidence span, notes, and spam decision. The
adjudication fields retain the adjudicator identifier, status, timestamp, final
decisions, and final request details. Independent labels must never be replaced
by the adjudicated result.

Secondary signals are stored as semicolon-separated values drawn from the same
eight-category vocabulary. Blank fields mean not yet annotated, not a negative
label. Timestamps use UTC when the annotation tool supports them.

## Text provenance

- `raw_comment_text` preserves the exact decoded Unicode code-point sequence
  read from the source CSV field.
- `raw_comment_text_sha256` hashes the UTF-8 encoding of that exact field.
- `normalized_text` is the explicit NFC representation used for Unicode-safe
  NLP processing.
- `cleaned_text` may additionally normalize whitespace and replace URLs.
- `original_text` is retained only as a compatibility field from the earlier
  preprocessing pipeline and may already be NFC-normalized.
- `evidence_text_field` is fixed to `raw_comment_text`.

Evidence spans must quote or index `raw_comment_text`, not normalized or cleaned
text. If offsets are later added, they must be zero-based Unicode code-point
intervals `[start, end)` in `raw_comment_text`. Changing that convention
requires a new schema version.

## Legacy mapping boundary

The portal's legacy `DEMAND`, `NON_DEMAND`, and `UNCLEAR` labels answer a
different question from the eight-class primary signal. There is no safe
automatic mapping from any legacy label to a specific eight-class category.

The following mappings are conditionally usable only after the researcher
confirms that the historical annotation followed the same actionability
definition:

| Legacy value | Conditional v1 actionability | Eight-class primary signal |
| --- | --- | --- |
| `DEMAND` | `YES` | Requires human review |
| `NON_DEMAND` | `NO` | Requires human review |
| `UNCLEAR` | `UNCLEAR` | Requires human review |

Legacy spam labels have the same literal values as the v1 spam field, but they
must remain attached to their original annotation provenance. Demand subtypes
can guide re-review but cannot be promoted automatically into an eight-class
label. No historical row is migrated unless the researcher approves a
documented migration and preserves the original columns.

## Versioning rule

New categories, changed meanings, evidence-offset conventions, or automatic
legacy mappings require a new schema version. Adding contextual metadata does
not change the annotation taxonomy, provided it is not used as a human label.
