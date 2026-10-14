# Component 2 Audience Demand Annotation Guide

## Purpose

This guide defines how to manually label YouTube comments for Component 2: Quantified Audience Demand Mining and Content-Gap Divergence. The goal is to identify whether a public audience comment contains an actionable content-related demand that can later support demand-intent classification, topic modelling, and demand-supply gap analysis.

Do not infer private user intent beyond the text. When the comment is too ambiguous, use `UNCLEAR`.

## Primary Labels

### DEMAND

Use `DEMAND` when the comment expresses an identifiable content-related request, preference, suggestion, unmet need, or actionable content improvement.

Examples of demand signals:

- asks for a new topic, person, event, explainer, update, or follow-up
- asks the channel to cover something differently
- requests more detail, context, source evidence, translation, language change, subtitles, or format change
- states a content need that the current video/channel could plausibly address

### NON_DEMAND

Use `NON_DEMAND` when the comment does not contain an identifiable audience demand.

Examples:

- appreciation, praise, dislike, laughter, simple reaction
- emoji-only reaction with no clear request
- political/social argument unrelated to a content need
- spam, promotion, repeated noise
- insult or complaint that does not ask for, imply, or specify a content improvement

### UNCLEAR

Use `UNCLEAR` when the available text is insufficient to decide.

Examples:

- very short comment where a demand may be implied but cannot be confirmed
- ambiguous reply without enough parent context
- unclear sarcasm
- code-mixed or slang text that annotators cannot confidently interpret

## Demand Subtypes

Use one subtype only when the primary label is `DEMAND`.

- `new_topic_content_request`: asks for a new topic, story, person, event, or issue to be covered
- `follow_up_or_additional_explanation`: asks for updates, more detail, context, or explanation
- `content_format_preference`: asks for a different format such as short clips, full episode, interview, live, subtitles, or highlights
- `language_preference`: asks for Sinhala, English, Tamil, subtitles, translation, or simpler language
- `content_improvement_request`: asks for improved accuracy, audio, visuals, moderation, structure, speed, or evidence
- `other_content_need`: actionable content demand that does not fit the above

Leave `demand_subtype` blank for `NON_DEMAND` and `UNCLEAR`.

## Decision Rules

1. Label the comment, not the commenter.
2. Do not treat all negative comments as demand.
3. Do not assume keyword presence proves demand. A word like "please" can appear in non-demand comments.
4. Do not automatically label every short comment as `NON_DEMAND`; use `UNCLEAR` if a demand may exist but is not interpretable.
5. Replies can be labelled if the reply itself contains enough context. If it depends on unavailable parent context, use `UNCLEAR`.
6. Use `DEMAND` only when the channel could reasonably act on the comment through future content or content presentation.
7. If a comment contains both reaction and a request, label `DEMAND` and choose the closest subtype.
8. If a complaint identifies a content improvement, label `DEMAND`. If it is only abuse or unrelated criticism, label `NON_DEMAND`.

## Multilingual and Script Guidance

### Sinhala Comments

Annotate based on meaning. Preserve Sinhala text as-is. If the annotator cannot interpret the Sinhala comment confidently, use `UNCLEAR` and note the issue.

### English Comments

Annotate normally using the same demand rules.

### Singlish and Tanglish

Latin-script comments may be English, Singlish, Tanglish, names, slang, or noise. Do not label Latin-script text as English automatically. If meaning is clear, annotate by demand content. If not, use `UNCLEAR`.

### Sinhala-English Code-Mixed Comments

If Sinhala and Latin-script text together express a content need, use `DEMAND`. If the mixed text is only reaction or praise, use `NON_DEMAND`. If the mixture is unclear, use `UNCLEAR`.

### Emoji-Only Comments

Usually `NON_DEMAND`, because they normally express reaction rather than a content need. Use `UNCLEAR` if the emoji sequence might refer to a request but cannot be interpreted safely.

### Very Short Comments

Very short comments can still be meaningful. Examples like "Part 2?", "More", or "English?" may be `DEMAND` depending on context. If there is no actionable content need, use `NON_DEMAND` or `UNCLEAR`.

### Complaints

Negative sentiment alone is not demand. Label `DEMAND` only if the complaint implies an actionable content need, such as better evidence, clearer explanation, translation, or coverage of a missing issue.

## Example Patterns

| Comment pattern | Primary label | Subtype | Rationale |
|---|---|---|---|
| "Please explain what happened after this" | DEMAND | follow_up_or_additional_explanation | asks for more explanation |
| "මේ ගැන තව වීඩියෝ එකක් කරන්න" | DEMAND | follow_up_or_additional_explanation | asks for more content on the issue |
| "English subtitles please" | DEMAND | language_preference | asks for language/accessibility support |
| "Full episode upload karanna" | DEMAND | content_format_preference | asks for a specific format |
| "Good video" | NON_DEMAND |  | appreciation only |
| "😂😂😂" | NON_DEMAND |  | reaction only |
| "What nonsense" | NON_DEMAND |  | negative reaction without actionable content need |
| "More details?" | DEMAND or UNCLEAR | follow_up_or_additional_explanation if context is clear | short but may request more detail |

These examples are illustrative decision patterns. They are not verified samples from the project dataset.

## Spam Status Labels

Spam annotation is a separate decision from demand annotation. A comment can be spam or not spam regardless of whether it contains a demand-like phrase. Do not automatically exclude any comment during manual annotation; record the spam status only.

### SPAM

Use `SPAM` when the comment is clearly promotional, deceptive, automated, or unrelated solicitation.

Examples of spam signals:

- promotional advertisements unrelated to the video or channel
- scams, phishing attempts, suspicious investment offers, or credential requests
- repeated unrelated promotional messages
- obvious bot-like solicitations
- links used mainly for promotion, scams, or unrelated traffic

### NOT_SPAM

Use `NOT_SPAM` when the comment appears to be a genuine viewer reaction, criticism, discussion, or content request, even if it is short, emotional, noisy, or low-information.

Do not label a comment as spam solely because it contains:

- a link
- capital letters
- repeated punctuation
- emojis
- unusual Unicode
- Sinhala, English, romanized Sinhala, Tanglish, or code-mixed text
- praise, criticism, insults, or low-information reactions

### UNCLEAR

Use `UNCLEAR` when there is not enough evidence to decide whether the comment is spam.

Examples:

- a bare link without enough surrounding context
- a repeated phrase that might be a meme, chant, or bot pattern
- ambiguous romanized or code-mixed text that could be promotional but is not clear
- a reply that may depend on unavailable parent context

## Spam Boundary Cases

| Comment pattern | Spam status | Rationale |
|---|---|---|
| "Buy followers fast, contact this number" | SPAM | promotional solicitation |
| "Click this link to earn money now" | SPAM | likely scam or unrelated promotion |
| "මේ ගැන තව වීඩියෝ කරන්න" | NOT_SPAM | Sinhala content request, not spam |
| "Me gana update ekak denna" | NOT_SPAM | romanized Sinhala/Singlish content request |
| "English subtitles please" | NOT_SPAM | language-access request |
| "Super video!!!" | NOT_SPAM | praise with repeated punctuation |
| "😂😂😂" | NOT_SPAM | low-information reaction, not automatically spam |
| "Visit my page" | UNCLEAR or SPAM | use SPAM if clearly promotional; use UNCLEAR if context is insufficient |
| "Free gift link" | UNCLEAR or SPAM | use SPAM when deceptive or promotional intent is clear |

These spam examples are illustrative decision patterns. They are not verified samples from the project dataset.

## Spam Annotation Instructions

1. Fill `annotator_1_spam_status` and `annotator_2_spam_status` independently using `SPAM`, `NOT_SPAM`, or `UNCLEAR`.
2. Use `spam_notes` for short explanations, especially for `SPAM` and `UNCLEAR`.
3. After independent annotation, resolve disagreements in `final_spam_status`.
4. Preserve legitimate demand comments. A genuine content request should remain available for demand analysis unless the team later approves an automated filtering rule.
5. Do not infer spam from language, script, emojis, repeated punctuation, or short length alone.
6. Do not train or apply automated spam filtering until human labels have been reviewed and adjudicated.

## Annotation Quality Plan

1. One annotator labels all sampled comments.
2. A second annotator independently labels a subset, preferably 20-30%.
3. Demand-label disagreements are discussed and adjudicated into `final_adjudicated_label`.
4. Spam-status disagreements are discussed and adjudicated into `final_spam_status`.
5. Cohen's Kappa is calculated only after real labels exist.
6. Class imbalance is reviewed before training any classifier.
7. Train/test splits should avoid leakage by grouping related comments from the same video where practical.
