/** Curated public-safe evidence, verified on 19 October 2026. Never import research CSVs here. */
export const COMPONENT_TITLE = "Quantified Audience Demand Mining and Content-Gap Divergence";
export const EVIDENCE_DATE = "19 October 2026";
export const REPO_URL = "https://github.com/Kalharachamod/Framework-for-Underperforming-YouTube-Channels-in-a-Multi-Channel-Media-Organization---J26-DS-334";
export const evidenceUrl = `${REPO_URL}/blob/component-2/docs/research/component2_evidence_register.md`;

export const pilot = { comments: 2000, channels: 5, perChannel: 400, catalogueVideos: 327, coveredVideos: 255 };
export const calibration = { total: 40, candidates: 20, controls: 20, yes: 6, no: 32, unclear: 2, evaluated: 38, tp: 5, fp: 13, fn: 1, tn: 19, categoryMatches: 15 };
export const corpus = { comments: 84002, channels: 8, videos: 10104, months: 19, trainingPool: 70184, expandedHeldOut: 11399 };
export const annotationBatch = { rows: 504, yes: 79, randomYes: 12, randomRows: 200 };
export const bestClassifier = { name: "e5 embeddings + logistic regression", f1: 0.54, recall: 0.79, ruleF1: 0.35 };
export const supplyTopics = { videos: 10104, topics: 151, bertopic: 0.687, lda: 0.407 };
export const partitions = [
  { role: "Calibration only", comments: 396, videos: 37, className: "calibration", description: "All comments from the videos used in the 40-comment calibration; kept out of training and evaluation." },
  { role: "Development", comments: 1293, videos: 175, className: "development", description: "Training and video-grouped validation." },
  { role: "Held-out evaluation", comments: 311, videos: 43, className: "held-out", description: "Frozen final-evaluation set, labelled blind for the final classifier test." },
];
export const reviewQueue = { rule: 41, supplementary: 6, controls: 47, total: 94 };
export const partitionFingerprint = "fbc2bdaca6ff73987e257a3408d23ea405e062168a4a535218f5ac4117a46f9f";

export type StageStatus = "Completed" | "Diagnostic" | "Redesigned" | "In progress" | "Planned";
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
    data: "2,000 comments, five channels and 400 comments per channel. The local catalogue has 327 videos; comments cover 255 of them. Sinhala, Singlish, English, mixed scripts and emoji are present.",
    implementation: "The shared collectors store channels, videos, comments and reply metadata. Component 2 SQL selects up to 400 non-empty comments per channel using deterministic MD5 ordering across videos. Validation checks IDs, joins, empty text and channel consistency. Unicode NFC, whitespace and URL normalization retain emoji; short, repeated and spam-like text is flagged.",
    evidence: "Quality summary: 2,000 unique comment IDs, zero duplicate comment/video IDs, zero empty comments, zero missing video context and zero channel mismatches.",
    problem: "Latin script can be English or Singlish, and a single word or emoji cannot establish demand, so meaning must be judged with context.",
    next: "Prepare annotation with source text and video context; keep the exact raw text separately from NFC processing text.",
  },
  {
    id: "annotation", title: "Initial 300-comment annotation workflow", status: "Completed",
    date: "14–15 Oct 2026 · Git checkpoints", source: "7969e08, bd9f7d0, 3e7603f; annotation_portal/README.md",
    intent: "Let annotators distinguish DEMAND, NON_DEMAND and UNCLEAR, with a separate spam decision.",
    rationale: "Human interpretation with video and parent-comment context is needed before supervised learning. A Streamlit portal supports saving, resuming and editing responses.",
    data: "300 comments, 60 per channel. Five sections of 30 comments each, plus a full 300-comment researcher view.",
    implementation: "Deterministic strata cover scripts, emoji, replies and short text. The Streamlit tool shows title/description context, missing-parent flags, private return codes and protected exports, backed by Supabase with row-level security.",
    evidence: "Deployed portal with 300 comments, 6 sections and 450 assignments; 67 live security checks passed.",
    problem: "A three-way DEMAND label could not explain why a comment was or was not demand, which led to the refined eight-category taxonomy.",
    next: "Separate the primary audience signal from actionability and record the requested action, topic and target.",
  },
  {
    id: "taxonomy", title: "Refined audience-demand taxonomy", status: "Completed",
    date: "16 Oct checkpoint; canonical contract 18 Oct 2026", source: "6afa033; decision_guide.md; annotation_schema_v1.md",
    intent: "Explain what a comment expresses independently of whether it requests a channel action.",
    rationale: "A single DEMAND label hides whether a viewer asks for a new video, expresses a preference, seeks information or merely reacts. Eight categories plus separate actionability retain that distinction.",
    data: "The decision guide and the 40 researcher-labelled calibration comments.",
    implementation: "One primary signal; optional secondary signals; YES/NO/UNCLEAR actionability; requested topic, action, format and target; raw-text evidence; separate spam decision.",
    evidence: "Schema version component2.audience-demand.v1 validates vocabulary and text hashes, with exact raw text and NFC text kept separately.",
    problem: "A schedule question can be an information need without requesting new content, and praise does not imply a content change, so actionability is decided separately.",
    next: "Diagnose the rule screener on a calibration set before any model training.",
  },
  {
    id: "calibration", title: "Experiment 1 · 40-comment calibration", status: "Diagnostic",
    date: "16 Oct 2026 · tooling checkpoint", source: "6afa033; first_calibration_report.md; metrics.json",
    intent: "Test whether a transparent multilingual rule screener captures genuine actionable requests.",
    rationale: "A small diagnostic makes false positives and missed requests visible before investing in a multilingual classifier.",
    data: "40 comments: 20 rule candidates and 20 controls, four of each per channel. Researcher decisions: 6 YES, 32 NO and 2 UNCLEAR.",
    implementation: "Run the original rules unchanged. Exclude the two UNCLEAR rows from binary evaluation; keep all 40 in the eight-category comparison.",
    evidence: "38 evaluable rows: TP 5, FP 13, FN 1, TN 19. Precision 27.78%, recall 83.33%, F1 41.67%. Eight-category agreement between rules and researcher labels: 15/40 = 37.50%.",
    problem: "Recall is high but precision is low: 13 of 18 flagged comments were not requests. Keyword rules cannot separate requests from praise and discussion.",
    next: "Freeze the calibration and analyse every error before designing the next experiment.",
  },
  {
    id: "errors", title: "Experiment 1B · Error analysis", status: "Completed",
    date: "16 Oct 2026 · tooling checkpoint", source: "6afa033; experiment_1b_error_analysis.md (local)",
    intent: "Explain the 13 false positives and one false negative in their linguistic and video context.",
    rationale: "Lexical triggers do not resolve sentence meaning, request targets or implied creative preferences.",
    data: "The frozen 40-comment calibration with per-comment baseline evidence and researcher notes.",
    implementation: "Assign one main error explanation to each of the 14 binary errors and inspect secondary factors. The rules and labels stay unchanged.",
    evidence: "Main categories: contextual Sinhala/Singlish misunderstanding 3; praise/reaction 4; keyword overreach 1; missing context 2; external request target 2; implicit storyline preference 1; broad-candidate/actionability mismatch 1.",
    problem: "Tokens such as one, new and episode occur in grammar, names, programme references and praise. Requests to outside institutions are not channel requests.",
    next: "Record target and context in the schema; prepare separate representative and demand-enriched samples.",
  },
  {
    id: "sample", title: "Experiment 2A · Initial 500-comment sample", status: "Redesigned",
    date: "16 Oct 2026 · implementation checkpoint", source: "prepare_experiment_2a.py; experiment_2a_methodology.md (local)",
    intent: "Create a 500-comment exploratory pool and a separate candidate-enriched development pool.",
    rationale: "100 comments per channel supports channel-balanced exploration; testing requires keeping related video context out of model development.",
    data: "500 comments from the 2,000-comment pilot, 100 per channel, with video and reply context.",
    implementation: "Sample comments first, then reserve every associated video and its other comments.",
    evidence: "The 500 rows touch 197 of 255 comment-covered videos, leaving only five rows for the enriched queue.",
    problem: "Comment-first sampling spreads across videos, so protecting whole video groups consumes nearly the full pilot.",
    next: "Audit video allocation, candidate attrition and calibration overlap.",
  },
  {
    id: "leakage", title: "Experiment 2A.1 · Leakage investigation", status: "Completed",
    date: "16 Oct 2026 · commit 6afa033", source: "dataset_split_and_leakage_audit.md",
    intent: "Check whether the original evaluation split leaves usable, independent development data.",
    rationale: "Comments from the same video share topic and context. Splitting them across development and test rewards memorization rather than generalization.",
    data: "The full pilot, the 500-comment sample, the video split manifest and the 40 calibration IDs.",
    implementation: "Join comment IDs to video groups, count full-video partitions, compare calibration IDs and videos, and trace candidate losses.",
    evidence: "197 evaluation videos contain 1,825 comments (91.25% of the pilot); only 155 comments across 53 videos remained for training.",
    problem: "The old grouping avoided video overlap but caused severe data attrition and overlapped the calibration set.",
    next: "Freeze a video-first partition that excludes every calibration-source video.",
  },
  {
    id: "split", title: "Experiment 2A.2 · Corrected video-grouped split", status: "Completed",
    date: "18 Oct 2026 · partition lock seed 20261018", source: "experiment_2a2_protocol.md; experiment_2a2_partition_lock.json",
    intent: "Establish a reproducible boundary before annotation and model development.",
    rationale: "Sample videos first and keep their comments together, preserving a viable development pool and a separate evaluation set.",
    data: "All 2,000 pilot comments across 255 videos; every calibration video is excluded from development and evaluation.",
    implementation: "Within each channel and chronological quartile, seeded SHA-256 ranking selects about 20% of videos. Source hashes, roles and the partition fingerprint are frozen; a training guard rejects protected, unknown, duplicate and conflicting IDs.",
    evidence: "Calibration-only: 396 comments / 37 videos. Development: 1,293 / 175. Held-out: 311 / 43. A blinded 94-comment development queue (41 rule candidates, 6 supplementary, 47 matched controls).",
    problem: "The enriched 47:47 queue is designed for training, not for estimating how common demand is, so a random sample is added later.",
    next: "Expand the corpus over time and add retrieval-based candidates.",
  },
  {
    id: "expansion", title: "Experiment 2B and 3A · Retrieval and expanded corpus", status: "Completed",
    date: "19 Oct 2026", source: "prepare_experiment_2b.py; build_expanded_corpus.py; experiment_3a_corpus_lock.json",
    intent: "Find more demand candidates and collect enough history for topic modelling and temporal validation.",
    rationale: "Demand is rare and the pilot covered only days for some channels. Entertainment channels publish in seasons, which supports season-to-season validation.",
    data: "84,002 comments from 8 Derana channels over 19 months, and metadata for 10,104 videos.",
    implementation: "Word, character and combined TF-IDF retrieval from the six calibration requests (Experiment 2B). Read-only YouTube Data API collection with salted commenter hashes; new comments on protected videos are quarantined and a fresh video-grouped held-out slice is reserved (Experiment 3A).",
    evidence: "A frozen v2 corpus lock; 70,184 training-pool comments, 11,399 expanded held-out comments, and the original 2A.2 partition unchanged.",
    problem: "Most demand on these channels concerns existing programmes (judges, songs, storylines) rather than entirely new topics.",
    next: "Annotate a mixed batch and model content supply.",
  },
  {
    id: "supply", title: "Experiment 3B · Content-supply topics", status: "Completed",
    date: "19 Oct 2026", source: "supply_topics.py; experiment_3_protocol.md",
    intent: "Describe what each channel publishes as topic distributions.",
    rationale: "Supply must be represented in the same semantic space as audience demand before divergence is computed.",
    data: "10,104 video titles and descriptions; channel boilerplate and crew credits removed automatically.",
    implementation: "BERTopic on multilingual-e5-small embeddings (pinned revision shared with Component 3), compared with LDA using the same number of topics and c_v coherence.",
    evidence: "151 topics. Mean c_v: BERTopic 0.687 vs LDA 0.407; 0.577 vs 0.371 after excluding cast-list topics.",
    problem: "One channel (TV Derana) dominates an organisation-wide model, so channel-specific topic spaces are used for the gap analysis.",
    next: "Build demand topics anchored on audience comments.",
  },
  {
    id: "classifier", title: "Experiment 3C and 3D · Annotation batch and first classifiers", status: "Completed",
    date: "19 Oct 2026", source: "prepare_experiment_3c.py; experiment_3d_classifiers.py",
    intent: "Label a mixed sample and train the first demand classifiers.",
    rationale: "A random sample measures how common demand is; retrieval samples supply enough positive examples to train on.",
    data: "504 comments: 154 queue, 200 random, 150 retrieval candidates (rules, TF-IDF, e5). Researcher-reviewed labels with AI-assisted pre-labelling: 79 YES.",
    implementation: "Video-grouped stratified 5-fold cross-validation over 5 seeds: TF-IDF + logistic regression, TF-IDF + linear SVM and e5 embeddings + logistic regression, against the frozen rule baseline.",
    evidence: "Demand in the random sample: 6.0% (12/200). Similarity retrieval found demand at 36% vs 20% for rules. F1: e5 + LR 0.54, TF-IDF + LR 0.50, linear SVM 0.47, rules 0.35.",
    problem: "TF-IDF models are precise but miss requests; e5 finds most requests with more false alarms, so a two-stage filter is used.",
    next: "Separate meaningful comments from reactions, build demand topics and compute JSD per channel.",
  },
  {
    id: "next", title: "Next stage · Demand topics and divergence", status: "In progress",
    date: "From 20 Oct 2026", source: "experiment_3_protocol.md",
    intent: "Quantify where audience demand and channel supply diverge.",
    rationale: "JSD measures overall mismatch; per-topic contributions and unique-requester counts show where the gaps are.",
    data: "Meaningful comments and detected requests from the 70,184-comment training pool; supply topics for the same channels.",
    implementation: "Channel-specific shared topic space, demand and supply distributions, JSD with per-topic contributions, and season-to-season validation on Dream Star and Derana 60 Plus.",
    evidence: "Inputs are ready: expanded corpus, supply topics and trained classifiers.",
    problem: "Comments are attached to existing videos, so demand is read as mismatch in emphasis and supported by explicit request counts.",
    next: "Final classifier evaluation on the blind held-out set and the gap report per channel.",
  },
];

export const taxonomy = [
  ["EXPLICIT_CONTENT_REQUEST", "Explicit content request", "A direct request for a topic, guest, video, full version or re-upload aimed at the channel."],
  ["CONTENT_CHANGE_PREFERENCE", "Content-change preference", "A requested change in storyline, cast, judges, format, subtitles, language or presentation; simple enjoyment is insufficient."],
  ["INFORMATION_NEED", "Information need", "A question or request for clarification. Actionability depends on whether it asks for a channel content action."],
  ["CONTENT_QUALITY_FEEDBACK", "Content-quality feedback", "Comments about production or story quality. A complaint alone need not contain a specific requested action."],
  ["TOPICAL_INTEREST_OR_DISCUSSION", "Topical discussion", "An opinion or discussion of the current subject without a future channel content request."],
  ["ORDINARY_REACTION", "Ordinary reaction", "Praise, criticism, thanks or emoji without an actionable request."],
  ["SPAM_OR_IRRELEVANT", "Spam or irrelevant", "Promotion or unrelated material. Spam is also recorded as a separate decision."],
  ["UNCLEAR", "Unclear signal", "Insufficient or ambiguous evidence; uncertainty is recorded instead of forcing a decision."],
] as const;

export type SignalCode = (typeof taxonomy)[number][0];
export interface ResearchExample {
  title: string; signal: SignalCode; text: string; human: string; baseline: string; ruleOutcome: string; explanation: string; source: string; illustrative?: boolean;
}
export const examples: ResearchExample[] = [
  { title: "A specific re-upload request", signal: "EXPLICIT_CONTENT_REQUEST", text: "Season 10 eke group songs tika ain kralane. Ee tika aye upload krnne nadda", human: "YES", baseline: "Candidate · EXPLICIT_CONTENT_REQUEST", ruleOutcome: "True positive", explanation: "This Singlish question asks the channel to restore the removed group songs. It names a concrete content operation, not just liking the programme.", source: "Calibration row 27" },
  { title: "Implicit storyline preference", signal: "CONTENT_CHANGE_PREFERENCE", text: "වෙනස් කරන්න එපා.", human: "YES", baseline: "Not a candidate · UNCLEAR", ruleOutcome: "False negative", explanation: "Excerpt: ‘do not change’. The full comment addresses the writer and asks for a specific storyline direction. The rules missed it because it contains no request keyword.", source: "Calibration row 24 · excerpt; character references omitted" },
  { title: "A broadcast-time question", signal: "INFORMATION_NEED", text: "Redio eke yanne kiyatada kawadda dan", human: "NO", baseline: "Not a candidate · UNCLEAR", ruleOutcome: "True negative", explanation: "The viewer asks when the programme airs on radio. It is an information need about the schedule, not a request for new or changed content.", source: "Calibration row 8" },
  { title: "A full-video availability question", signal: "INFORMATION_NEED", text: "මේකේ full video එකක් නැද්ද", human: "UNCLEAR", baseline: "Candidate · CONTENT_CHANGE_PREFERENCE", ruleOutcome: "Excluded (UNCLEAR)", explanation: "Asking whether a full video exists may imply a request to upload it, but no direct request is made, so actionability is recorded as UNCLEAR and excluded from the binary metrics.", source: "Calibration row 29" },
  { title: "Concern about story quality", signal: "CONTENT_QUALITY_FEEDBACK", text: "Me kathavanm supri kalayak yaddi pata kurullo vage epa karaviyda danna", human: "NO", baseline: "Candidate · EXPLICIT_CONTENT_REQUEST", ruleOutcome: "False positive", explanation: "The viewer praises the drama but worries its quality may fall later. It is quality feedback without a specific requested change; the rules were triggered by the word danna.", source: "Calibration row 36" },
  { title: "Discussion of the current match", signal: "TOPICAL_INTEREST_OR_DISCUSSION", text: "Me wage media walata kiyannethuwa confident eka match eke penanna balanna one", human: "NO", baseline: "Candidate · EXPLICIT_CONTENT_REQUEST", ruleOutcome: "False positive", explanation: "The Singlish word one refers to the player's performance in the match. The comment discusses the topic without asking the channel to produce anything.", source: "Calibration row 4" },
  { title: "Praise mistaken for demand", signal: "ORDINARY_REACTION", text: "One of my fav❤ singers ♥️♥️♥️🔥🔥🔥", human: "NO", baseline: "Candidate · EXPLICIT_CONTENT_REQUEST", ruleOutcome: "False positive", explanation: "The rules read one as a request cue, but here it is an English quantifier in praise. Positive sentiment does not request a channel action.", source: "Calibration row 16" },
  { title: "Promotional spam", signal: "SPAM_OR_IRRELEVANT", text: "Earn Rs. 50,000 daily! Contact me for investment opportunities.", human: "NO · SPAM", baseline: "Not applied", ruleOutcome: "Illustrative", explanation: "Unrelated promotion and solicitation. It is recorded as SPAM_OR_IRRELEVANT with a separate SPAM decision and never counted as demand.", source: "decision_guide.md · illustrative example", illustrative: true },
  { title: "An ambiguous short question", signal: "UNCLEAR", text: "Peace is ongoing show only\nDo you know?", human: "UNCLEAR", baseline: "Candidate · EXPLICIT_CONTENT_REQUEST", ruleOutcome: "Excluded (UNCLEAR)", explanation: "It is not clear whether the viewer is asking for information or suggesting content, so the signal is recorded as UNCLEAR instead of guessing.", source: "Calibration row 31" },
];

export const comparisons = [
  { title: "Annotation taxonomy", before: "DEMAND / NON_DEMAND / UNCLEAR compresses the audience signal into one decision.", after: "Eight primary signals plus independent actionability, action, topic, format and target explain the decision.", why: "A question can remain INFORMATION_NEED without becoming actionable demand, and every error becomes explainable by category." },
  { title: "Sampling unit", before: "Sample 500 comments, then reserve all 197 videos they touch: 1,825 comments are consumed by evaluation groups.", after: "Exclude calibration videos, sample eligible videos within channel/time strata, and keep all comments from a video in one role.", why: "The corrected boundary preserves 1,293 development comments and 311 held-out comments without crossing video roles." },
  { title: "Rules and human decisions", before: "84 automatic pilot candidates could be mistaken for 84 verified requests.", after: "Rules, TF-IDF and e5 retrieval nominate candidates; researcher decisions establish actionability.", why: "The calibration's 13 false positives show why a candidate flag cannot become ground truth or a prevalence count." },
  { title: "Rules versus trained classifiers", before: "Keyword rules: F1 0.35 on the 490 binary batch-1 labels.", after: "Trained classifiers with video-grouped cross-validation: F1 0.47–0.54; e5 embeddings recover 79% of requests.", why: "Learning from labelled examples captures meaning across Sinhala, Singlish and English that fixed keywords miss." },
  { title: "Global JSD and topic direction", before: "A single symmetric divergence value summarizes overall demand–supply mismatch, without saying which side has more of a topic.", after: "Compare aligned demand share P(topic) and supply share Q(topic); report the signed P−Q contribution alongside global JSD.", why: "A positive topic difference indicates undersupply relative to audience attention, supported by explicit request counts." },
];

export const futurePipeline = [
  { name: "Multilingual comments", status: "Implemented", detail: "84,002 comments from 8 Derana channels over 19 months, with validation and conservative multilingual preprocessing." },
  { name: "Demand identification", status: "Implemented", detail: "Eight-category taxonomy, 544 labelled comments and trained classifiers (best F1 0.54 vs 0.35 for rules)." },
  { name: "Content-supply modelling", status: "Implemented", detail: "BERTopic on 10,104 videos with LDA comparison (c_v 0.687 vs 0.407)." },
  { name: "Demand-topic modelling", status: "Partial", detail: "Channel-specific topics from meaningful comments and detected requests." },
  { name: "Aligned topic distributions", status: "Partial", detail: "Demand and supply represented in the same multilingual e5 semantic space." },
  { name: "Jensen–Shannon Divergence", status: "Planned", detail: "Overall demand–supply mismatch per channel and season." },
  { name: "Directional gap analysis", status: "Planned", detail: "Per-topic contributions and unique-requester counts identify under-supplied topics." },
  { name: "Validated content opportunities", status: "Planned", detail: "Season-to-season validation on Dream Star and Derana 60 Plus, plus manual review of the top gaps." },
];

export const researchQuestions = [
  ["What problem does Component 2 solve?", "Channels receive many reactions but need to know which comments express genuine content requests. Component 2 identifies that demand in Sinhala, Singlish and English comments, aligns it with what the channel publishes in a shared topic space, and quantifies the gaps."],
  ["Why use multilingual NLP?", "The comments mix Sinhala script, Singlish, English and emoji. Meaning depends on code-mixing and context, so preprocessing preserves the original language and multilingual embeddings compare meaning across scripts."],
  ["Why was the initial annotation approach insufficient?", "DEMAND/NON_DEMAND/UNCLEAR does not explain whether a viewer is reacting, asking a factual question, requesting a re-upload or expressing a storyline preference. The refined schema separates eight primary signals from actionability and structured request details."],
  ["What did the 40-comment calibration show?", "On 38 binary-evaluable rows, the unchanged rules produced 5 TP, 13 FP, 1 FN and 19 TN: 27.78% precision, 83.33% recall and 41.67% F1. Keyword rules find requests but raise many false alarms."],
  ["What is precision versus recall?", "Precision asks how many flagged cases were actionable: 5/(5+13). Recall asks how many actionable cases were found: 5/(5+1). F1 balances the two."],
  ["What is data leakage?", "Information from evaluation leaking into development. Comments from one video share context, so splitting them between training and test exaggerates performance. Every split in this study keeps whole videos together."],
  ["Why did we change the dataset split?", "The original 500-comment sample touched 197 videos, reserving 1,825 comments and leaving 155 for training. Video-first splitting now separates 396 calibration-only, 1,293 development and 311 held-out comments."],
  ["How well do the classifiers work?", "With video-grouped 5-fold cross-validation over 5 seeds, e5 embeddings + logistic regression reach F1 0.54 and find 79% of requests; TF-IDF models reach 0.47–0.50 with higher precision. All beat the keyword rules (F1 0.35)."],
  ["How common is genuine demand?", "In a random sample of 200 comments, 6.0% were actionable requests (95% CI 3.5–10.2%). Similarity retrieval raises the yield to 36%, which is how enough training examples were collected."],
  ["What is JSD?", "Jensen–Shannon Divergence is the average KL divergence of two distributions from their mean: JSD(P,Q) = ½ KL(P‖M) + ½ KL(Q‖M), M=(P+Q)/2. It is symmetric and, with base-2 logarithms, ranges from 0 to 1. SciPy's jensenshannon returns the square-root distance, so the divergence itself is computed directly."],
  ["What comes next?", "Separate meaningful comments from reactions, build channel-specific demand topics, compute JSD and per-topic gaps against supply, validate season to season, and report final classifier results on the blind held-out set."],
] as const;
