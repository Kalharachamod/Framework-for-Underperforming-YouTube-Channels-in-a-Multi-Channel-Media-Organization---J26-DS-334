/** Curated public-safe evidence, verified on 18 October 2026. Never import research CSVs here. */
export const COMPONENT_TITLE = "Quantified Audience Demand Mining and Content-Gap Divergence";
export const EVIDENCE_DATE = "18 October 2026";
export const REPO_URL = "https://github.com/Kalharachamod/Framework-for-Underperforming-YouTube-Channels-in-a-Multi-Channel-Media-Organization---J26-DS-334";
export const evidenceUrl = `${REPO_URL}/blob/component-2/docs/research/component2_evidence_register.md`;

export const pilot = { comments: 2000, channels: 5, perChannel: 400, catalogueVideos: 327, coveredVideos: 255 };
export const calibration = { total: 40, candidates: 20, controls: 20, yes: 6, no: 32, unclear: 2, evaluated: 38, tp: 5, fp: 13, fn: 1, tn: 19, categoryMatches: 15 };
export const partitions = [
  { role: "Calibration only", comments: 396, videos: 37, className: "calibration", description: "All comments from videos used in the 40-row calibration; excluded from new model partitions." },
  { role: "Development", comments: 1293, videos: 175, className: "development", description: "Future training and grouped validation, after independently reviewed labels are available." },
  { role: "Held-out evaluation", comments: 311, videos: 43, className: "held-out", description: "Frozen evaluation frame with blank labels. Historical exposure must be resolved before claiming it is unseen." },
];
export const reviewQueue = { rule: 41, supplementary: 6, controls: 47, total: 94 };
export const partitionFingerprint = "fbc2bdaca6ff73987e257a3408d23ea405e062168a4a535218f5ac4117a46f9f";

export type StageStatus = "Completed" | "Diagnostic" | "Redesigned" | "Prepared" | "Pending";
export interface ResearchStage {
  id: string; title: string; status: StageStatus; date: string; source: string;
  intent: string; rationale: string; data: string; implementation: string; evidence: string; problem: string; next: string;
}
export const stages: ResearchStage[] = [
  {
    id: "preparation", title: "Data collection and preparation", status: "Completed",
    date: "14 Oct 2026 · implementation checkpoint", source: "d08d1c3; pilot extraction SQL; dataset_quality_summary.csv (local)",
    intent: "Prepare an auditable multilingual pilot from the team's shared YouTube collection pipeline.",
    rationale: "Use a traceable local snapshot and conservative cleaning so request meaning, negation, Sinhala and code-mixing survive preprocessing.",
    data: "2,000 comments, five channels and 400 comments per channel. The local catalogue has 327 videos; comments cover 255 of them. Sinhala, Singlish, English, mixed scripts and emoji are present; script is not a verified language label.",
    implementation: "The shared collectors store channels, videos, comments and reply metadata. Component 2 SQL selects up to 400 non-empty comments per channel using deterministic MD5 ordering across videos. Validation checks IDs, joins, empty text and channel consistency. Unicode NFC, whitespace and URL normalization retain emoji; short, repeated and spam-like text is flagged for review. Duplicate IDs are checked and annotation sampling deduplicates IDs; ordinary repeated reactions are not silently deleted.",
    evidence: "Quality summary: 2,000 unique comment IDs, zero duplicate comment/video IDs, zero empty comments, zero missing video context and zero channel mismatches. Current processed files match 2,000 comments and 327 videos.",
    problem: "A balanced, deterministic pilot is not representative of all viewers. Latin script can be English or Singlish. A word or emoji alone cannot establish demand.",
    next: "Prepare human review with source text and video context; retain an exact raw-text field separately from NFC processing text in the canonical schema.",
  },
  {
    id: "annotation", title: "Initial 300-comment annotation workflow", status: "Prepared",
    date: "14–15 Oct 2026 · Git checkpoints", source: "7969e08, bd9f7d0, 3e7603f; annotation_portal/README.md; local read-only audit",
    intent: "Let reviewers distinguish DEMAND, NON_DEMAND and UNCLEAR, with a separate spam decision.",
    rationale: "Human interpretation and video/parent context are needed before any supervised learning. A Streamlit portal supports saving, resuming and editing responses.",
    data: "300 template comments, 60 per channel. Five volunteer sections contain 30 rows each; the primary researcher can review all 300. These are assignment capacities, not completed annotations.",
    implementation: "Deterministic strata cover scripts, emoji, replies and short text. The separate Streamlit tool provides title/description context, missing-parent flags, private return codes and protected exports. The original portal taxonomy remains unchanged.",
    evidence: "The current local 300-row CSV has zero nonblank demand-label fields. The local portal database has two participant records and one saved response; identity, role and completeness cannot be inferred from those totals. No live Supabase audit was performed.",
    problem: "Two volunteers' preliminary feedback is reported by the researcher, but records do not establish exactly what Reviewer 1 or Reviewer 2 completed. No verified independent agreement or completed 300-row annotation can be claimed. Names and attribution are withheld.",
    next: "Confirm the feedback scope and ethics position; separate primary audience signal from actionability and preserve independent annotation provenance.",
  },
  {
    id: "taxonomy", title: "Refined audience-demand taxonomy", status: "Prepared",
    date: "16 Oct checkpoint; canonical contract reviewed 18 Oct 2026", source: "6afa033; decision_guide.md; annotation_schema_v1.md",
    intent: "Explain what a comment expresses independently of whether it requests a channel action.",
    rationale: "A single DEMAND label hides whether a viewer asks for a new video, expresses a preference, seeks information or merely reacts. Eight categories plus separate actionability retain that distinction.",
    data: "The experimental decision guide and the 40 researcher-reviewed calibration comments informed methodological inspection; new review templates remain unlabelled.",
    implementation: "One primary signal; optional secondary signals; YES/NO/UNCLEAR actionability; requested topic, action, format and target; raw-text evidence; separate spam decision; two independent annotators and adjudication fields.",
    evidence: "Version component2.audience-demand.v1 validates vocabulary and text hashes. Exact raw text and NFC text have separate provenance. There is no automatic migration from legacy DEMAND into an eight-category primary signal.",
    problem: "A schedule question may be an information need without a request for new content. Praise, topical interest and a positive programme preference do not automatically imply a content change. Legacy actionability mappings still require researcher confirmation.",
    next: "Use a small calibration to diagnose the unchanged rule screener and refine review guidance, without inventing human labels.",
  },
  {
    id: "calibration", title: "Experiment 1 · 40-comment calibration", status: "Diagnostic",
    date: "16 Oct 2026 · tooling checkpoint; exact review date not recorded", source: "6afa033; first_calibration_report.md; metrics.json; calibration_40_selection_key.csv (local)",
    intent: "Test whether a transparent multilingual rule screener captures genuine actionable requests.",
    rationale: "A small diagnostic makes false positives and missed requests visible before investing in a larger multilingual classifier.",
    data: "40 deliberately selected comments: 20 prior rule candidates and 20 controls, four of each per channel. Researcher-approved decisions: 6 YES, 32 NO and 2 UNCLEAR. AI-assisted suggestions were available; final decisions belong to the researcher.",
    implementation: "Run the original rules unchanged. Exclude only the two human-actionability UNCLEAR rows from binary evaluation. Retain all 40 in the eight-category comparison.",
    evidence: "38 evaluable rows: TP 5, FP 13, FN 1, TN 19. Precision 27.78%, recall 83.33%, F1 41.67%. Primary-signal exact agreement is 15/40 = 37.50%; this compares rules to researcher labels, not two human annotators.",
    problem: "High recall finds five of the six actionable requests but precision is low: 13 of 18 evaluable flagged comments are false positives. This selected set cannot establish population classifier performance or demand prevalence.",
    next: "Freeze the calibration and investigate errors; do not tune historical results to make the baseline appear successful.",
  },
  {
    id: "errors", title: "Experiment 1B · Error analysis", status: "Completed",
    date: "16 Oct 2026 · tooling checkpoint; exact analysis date not recorded", source: "6afa033; experiment_1b_error_analysis.md (local); evidence register E3",
    intent: "Explain the 13 false positives and one false negative in their linguistic and video context.",
    rationale: "Lexical triggers do not resolve sentence meaning, request targets or implied creative preferences.",
    data: "The frozen 40-comment calibration and per-comment baseline evidence, human decisions and contextual notes; no new labels were collected.",
    implementation: "Assign one main error explanation to each of 14 binary errors and inspect overlapping secondary factors. Neither the original rules nor the reviewed labels were changed.",
    evidence: "Main categories: contextual Sinhala/Singlish misunderstanding 3; praise/reaction 4; keyword overreach 1; missing context 2; external request target 2; implicit storyline preference 1; broad-candidate/actionability mismatch 1. Secondary lexical overreach affects all 13 false positives.",
    problem: "Tokens such as one, new and episode occur in grammar, names, programme references and praise. Requests to external institutions are not channel requests. The missed Sinhala storyline preference required narrative context.",
    next: "Retain target and context decisions in the schema; prepare separate representative and demand-enriched review purposes.",
  },
  {
    id: "sample", title: "Experiment 2A · Initial 500-comment sample", status: "Redesigned",
    date: "16 Oct 2026 · implementation checkpoint", source: "prepare_experiment_2a.py; experiment_2a_methodology.md (local)",
    intent: "Create a 500-comment exploratory review pool and a separate candidate-enriched development pool.",
    rationale: "100 comments per channel supports channel-balanced exploration; independent testing also requires keeping related video context out of model development.",
    data: "500 selected rows from the existing 2,000-comment pilot, 100 per channel, with blank annotation fields and available video/reply context.",
    implementation: "Sample comments first, then reserve every associated video and its other comments. Candidate retrieval occurs outside those video groups; the historical 500 rows are preserved.",
    evidence: "The 500 rows touch 197 of 255 comment-covered videos. Only five rows remained in the initial enriched queue: four rule candidates and one supplementary match, all unlabelled.",
    problem: "Comment-first sampling spreads widely across videos, so protecting entire video groups consumes nearly the full pilot. Calibration overlap also prevents a fresh independent evaluation claim.",
    next: "Audit video allocation, candidate attrition and calibration overlap before declaring a final test set.",
  },
  {
    id: "leakage", title: "Experiment 2A.1 · Leakage investigation", status: "Completed",
    date: "Recorded by 16 Oct 2026 · commit 6afa033", source: "dataset_split_and_leakage_audit.md",
    intent: "Check whether the original evaluation designation leaves usable, independent development data.",
    rationale: "Comments from the same video share topic and context. Splitting related comments across development and test can reward memorization rather than generalization.",
    data: "The full pilot, original 500-row sample, video split manifest and 40 calibration IDs; this was a read-only audit.",
    implementation: "Join comment IDs to video groups, count full video partitions, compare calibration IDs/videos, and trace candidate losses.",
    evidence: "197 evaluation videos contain 1,825 comments (91.25% of the pilot). Enriched development videos contain 20 comments; only 155 comments across 53 videos remain for future training. The 500 sample overlaps calibration by 10 exact comments and 35 videos.",
    problem: "The old grouping prevented development/test video overlap but caused severe data attrition and retained prior calibration exposure. Its automatic candidates are not verified training positives.",
    next: "Keep the 500 as exploratory data; freeze a smaller video-first partition that excludes every calibration-source video.",
  },
  {
    id: "split", title: "Experiment 2A.2 · Corrected video-grouped split", status: "Prepared",
    date: "Verified 18 Oct 2026 · partition lock seed 20261018", source: "experiment_2a2_protocol.md; partition lock; local dataset_summary.json",
    intent: "Establish a reproducible boundary before further annotation or model development.",
    rationale: "Sample videos first and retain their comments together, preserving a viable development pool and a separate evaluation frame.",
    data: "All 2,000 pilot comments across 255 videos. Every video contributing to the 40-row calibration is excluded from both new development and evaluation.",
    implementation: "Within each channel and chronological quartile, use seeded SHA-256 ranking to select approximately 20% of eligible videos. Freeze source hashes, IDs, roles and the canonical partition fingerprint. The training guard rejects protected, unknown, duplicate and conflicting IDs.",
    evidence: "Calibration-only: 396 comments / 37 videos. Development: 1,293 / 175. Held-out: 311 / 43. The blinded development queue has 41 rule candidates, 6 supplementary candidates and 47 matched controls: 94 rows with blank human fields. All 111 Component 2 software tests passed on 18 October.",
    problem: "The held-out frame is not a labelled final evaluation set. The earlier exploratory pool contains 86 rows now held out; prior reading or tuning must be verified. The 47:47 enriched queue cannot estimate natural prevalence. Saved local review CSVs predate six newer annotation fields and six provenance fields; prepare and verify fresh v1 templates before further annotation while preserving the frozen identity and human work.",
    next: "Confirm ethics, annotation mappings and historical exposure; independently annotate and adjudicate before classifier training and evaluation.",
  },
  {
    id: "next", title: "Current limitations and next research stage", status: "Pending",
    date: "Status reviewed 18 Oct 2026 · no future activity dates assigned", source: "experiment_2a2_protocol.md; annotation_schema_v1.md; Component 2 README",
    intent: "Progress from a defensible review workflow to validated demand detection and aligned demand–supply analysis.",
    rationale: "The approved end goal needs trustworthy demand labels, source-verified supply metadata and shared topic definitions before divergence is meaningful.",
    data: "Only 40 researcher-reviewed calibration comments, including 6 actionable YES decisions. Independent agreement is unmeasured; the new development and held-out templates are blank.",
    implementation: "Planned: confirm supervisor/ethics position and legacy mappings, audit the 86 potentially exposed held-out rows, verify programme/content-type metadata, collect independent labels and additional positives, then use video-grouped validation.",
    evidence: "Validation, multilingual preprocessing, rule screening, diagnostic evaluation and partition safeguards exist. No trained XLM-R classifier, BERTopic demand/supply clusters, JSD result or verified content opportunity is available.",
    problem: "Limited positives, unverified independent reliability, programme context and pilot coverage constrain generalization. A comment-level preference alone does not prove an unmet gap.",
    next: "Train and evaluate a justified multilingual method only after prerequisites, then align demand and supply topics and quantify divergence with directional topic interpretation.",
  },
];

export const taxonomy = [
  ["EXPLICIT_CONTENT_REQUEST", "Explicit content request", "A direct request for a topic, guest, video, full version or re-upload. Confirm the channel is the target."],
  ["CONTENT_CHANGE_PREFERENCE", "Content-change preference", "A requested change in storyline, format, subtitles, language or presentation; simple enjoyment is insufficient."],
  ["INFORMATION_NEED", "Information need", "A question or request for clarification. Actionability depends on whether it asks for a channel content action."],
  ["CONTENT_QUALITY_FEEDBACK", "Content-quality feedback", "Comments about production quality. A complaint alone need not contain a specific requested action."],
  ["TOPICAL_INTEREST_OR_DISCUSSION", "Topical discussion", "An opinion or discussion of the current subject without a future channel content request."],
  ["ORDINARY_REACTION", "Ordinary reaction", "Praise, criticism, thanks or emoji without an actionable request."],
  ["SPAM_OR_IRRELEVANT", "Spam or irrelevant", "Promotion or unrelated material. Irrelevance does not automatically imply spam; keep the spam decision separate."],
  ["UNCLEAR", "Unclear signal", "Insufficient or ambiguous evidence; preserve uncertainty instead of forcing a decision."],
] as const;

export interface ResearchExample {
  title: string; kind: string; text: string; signal: string; human: string; baseline: string; explanation: string; source: string; illustrative?: boolean;
}
export const examples: ResearchExample[] = [
  { title: "A specific re-upload request", kind: "Actionable request", text: "Season 10 eke group songs tika ain kralane. Ee tika aye upload krnne nadda", signal: "EXPLICIT_CONTENT_REQUEST", human: "YES", baseline: "Candidate · EXPLICIT_CONTENT_REQUEST", explanation: "The researcher interpreted this Singlish question as a request to restore the group songs. It specifies a content operation, rather than just liking the programme.", source: "Calibration row 27 · researcher-approved decision" },
  { title: "Praise mistaken for demand", kind: "False positive", text: "One of my fav❤ singers ♥️♥️♥️🔥🔥🔥", signal: "ORDINARY_REACTION", human: "NO", baseline: "Candidate · EXPLICIT_CONTENT_REQUEST", explanation: "The rule matched one as a request cue, but here it is an English quantifier in praise. Positive sentiment does not request a channel action.", source: "Calibration row 16 · Experiment 1B" },
  { title: "Discussion of the current match", kind: "Topical discussion", text: "Me wage media walata kiyannethuwa confident eka match eke penanna balanna one", signal: "TOPICAL_INTEREST_OR_DISCUSSION", human: "NO", baseline: "Candidate · EXPLICIT_CONTENT_REQUEST", explanation: "The contextual Singlish word one concerns performance in the match. The researcher found no request for the channel to produce content. This is also a false positive.", source: "Calibration row 4 · Experiment 1B" },
  { title: "A full-video question with uncertainty", kind: "Ambiguous", text: "මේකේ full video එකක් නැද්ද", signal: "INFORMATION_NEED", human: "UNCLEAR", baseline: "Candidate · CONTENT_CHANGE_PREFERENCE", explanation: "The researcher retained uncertainty about actionability. An information question is not automatically a demand label. This row is excluded from the binary metrics.", source: "Calibration row 29 · researcher-approved decision" },
  { title: "Implicit storyline preference missed", kind: "False negative", text: "වෙනස් කරන්න එපා.", signal: "CONTENT_CHANGE_PREFERENCE", human: "YES", baseline: "Not a candidate · UNCLEAR", explanation: "Minimized excerpt only: ‘do not change’. The full calibration comment addresses the writer and specifies a storyline preference. The researcher used that context to assign YES; the lexical rules missed it. The excerpt alone is insufficient to reproduce that judgement.", source: "Calibration row 24 · Experiment 1B · excerpt; character references omitted" },
  { title: "An ordinary reaction", kind: "Non-demand reaction", text: "Great video. 🔥", signal: "ORDINARY_REACTION", human: "Illustrative NO; not a human research label", baseline: "Not measured for this illustration", explanation: "An invented teaching example from the decision guide: enjoyment without a requested topic, action or format. It is not a study observation and is excluded from every metric.", source: "decision_guide.md · illustrative example", illustrative: true },
];

export const comparisons = [
  { title: "Annotation taxonomy", before: "DEMAND / NON_DEMAND / UNCLEAR compresses the audience signal into one decision.", after: "Eight primary signals plus independent actionability, action, topic, format and target explain the decision.", why: "A question can remain INFORMATION_NEED without becoming actionable demand. Historical labels are preserved and legacy mappings require human confirmation." },
  { title: "Sampling unit", before: "Sample 500 comments, then reserve all 197 videos they touch: 1,825 comments are consumed by evaluation groups.", after: "Exclude calibration videos, sample eligible videos within channel/time strata, and keep all comments from a video in one role.", why: "The corrected boundary preserves 1,293 development comments and 311 held-out comments without crossing video roles." },
  { title: "Rules and human decisions", before: "84 automatic pilot candidates could be mistaken for 84 verified requests.", after: "Rules retrieve possibilities; independently recorded human decisions establish actionability. Blank fields remain unlabelled.", why: "The calibration's 13 false positives show why a candidate flag cannot become ground truth or a prevalence count." },
  { title: "Diagnostics and independent evaluation", before: "A deliberately selected 40-row calibration reveals errors but is unsuitable for final performance claims.", after: "A frozen, video-disjoint evaluation frame awaits independent labels and historical-exposure clarification.", why: "Model choices belong inside development. The final evaluation must remain outside feature, threshold and model selection." },
  { title: "Global JSD and topic direction", before: "A single symmetric divergence value summarizes overall demand–supply mismatch, without saying which side has more of a topic.", after: "Planned: compare aligned demand share P(topic) and supply share Q(topic); interpret a signed P−Q alongside global JSD.", why: "A positive topic difference may suggest undersupply, but requires verified catalogue coverage, programme context and human interpretation. No such results exist yet." },
];

export const futurePipeline = [
  { name: "Multilingual comments", status: "Implemented", detail: "Pilot collection, validation and conservative preprocessing." },
  { name: "Genuine-demand identification", status: "Partial", detail: "Rule retrieval and 40-row diagnostic exist; independent annotation and trained classifier evaluation remain." },
  { name: "Demand-topic modelling", status: "Planned", detail: "Model verified actionable demands; no BERTopic clusters have been produced." },
  { name: "Content-supply modelling", status: "Planned", detail: "Model source-verified video/programme content, with an explicit analysis date and coverage audit." },
  { name: "Aligned topic distributions", status: "Planned", detail: "Represent demand and supply in the same semantic topic space and normalize comparable distributions." },
  { name: "Jensen–Shannon Divergence", status: "Planned", detail: "Quantify overall distribution mismatch; no research JSD value exists." },
  { name: "Directional gap analysis", status: "Planned", detail: "Inspect demand-minus-supply shares per aligned topic; global JSD has no direction." },
  { name: "Evidence-supported content opportunities", status: "Planned", detail: "Validate plausible undersupplied topics against catalogue, temporal and programme evidence." },
];

export const researchQuestions = [
  ["What problem does Component 2 solve?", "Channels receive many reactions but need to know which comments express genuine content requests. The approved goal is to identify that demand, align it with content supply in a shared semantic topic space, and quantify potential gaps."],
  ["Why use multilingual NLP?", "The pilot includes Sinhala, Singlish, English, mixed scripts and emoji. Meaning depends on code-mixing and context, so preprocessing preserves the language. Script flags are not language labels; multilingual model coverage still needs validation."],
  ["Why was the initial annotation approach insufficient?", "DEMAND/NON_DEMAND/UNCLEAR does not explain whether a viewer is reacting, asking a factual question, requesting a re-upload or expressing a storyline preference. The refined schema separates eight primary signals from actionability and structured request details."],
  ["What did the 40-comment calibration show?", "On 38 binary-evaluable rows, unchanged rules produced 5 TP, 13 FP, 1 FN and 19 TN: 27.78% precision, 83.33% recall and 41.67% F1. Two UNCLEAR decisions were excluded. These are selected calibration diagnostics, not population performance."],
  ["What is precision versus recall?", "Precision asks how many flagged cases were actionable: 5/(5+13). Recall asks how many actionable cases were found: 5/(5+1). Finding most requests can coexist with many false alarms. F1 balances precision and recall."],
  ["What is data leakage?", "Information used during development contaminates evaluation. Comments from one video share context, so putting some in training and others in test can exaggerate generalization. Prior calibration exposure is a separate concern, even when new video partitions are disjoint."],
  ["Why did we change the dataset split?", "The original 500-row sample touched 197 videos, reserving 1,825 comments and leaving 155 for future training. It also overlapped calibration. Video-first splitting now separates 396 calibration-only, 1,293 development and 311 held-out comments."],
  ["Why are we not training XLM-R yet?", "There are only six actionable YES labels in a deliberately selected 40-row calibration. Independent annotation reliability, ethics clarification, additional positives and historical test exposure need resolution first. The new review queue has blank labels."],
  ["Why is a held-out test necessary?", "It evaluates a finalized method on evidence that did not guide model choices. The current 311-row frame has a frozen identity but still needs independent labels and confirmation about 86 rows present in an earlier exploratory pool."],
  ["What is JSD?", "Jensen–Shannon Divergence is the average KL divergence of two distributions from their mean: JSD(P,Q) = ½ KL(P‖M) + ½ KL(Q‖M), M=(P+Q)/2. It is symmetric; with base-2 logarithms its range is 0 to 1. Planned aligned demand/supply distributions do not exist yet. SciPy's jensenshannon returns the square-root distance, so a future implementation must distinguish distance from divergence."],
  ["What remains to be developed?", "Resolve ethics, mapping and exposure questions; independently annotate, measure agreement and adjudicate; verify programme metadata; develop and evaluate multilingual demand detection; then model and align demand/supply topics, calculate JSD and validate directional opportunities."],
] as const;
