# Candidate schema and routing

## Counting unit

One independent conversation/incident is one `case_id` and one `trajectory_id`. Multiple prefixes from it may create multiple JSONL rows, but readiness counts it once.

## Source record

`source/case-NNN.md` must state:

- source type: verbatim export, user summary, screenshot transcription, or authored reconstruction
- timestamp precision and timezone
- de-identification performed
- whether Assistant/tool contents are verbatim
- which claims remain unsupported

## Case record

Required fields:

```json
{
  "case_id": "case-NNN",
  "trajectory_id": "case-NNN",
  "source_record": "source/case-NNN.md",
  "privacy": {
    "deidentified": true,
    "raw_private_chat_included": false
  },
  "task_family": "...",
  "semantic_cluster": "...",
  "readiness_bucket": "search_and_read",
  "factual_claim_status": "quarantined_unverified",
  "status": "safe_prefix_trainable",
  "trainable_row_ids": ["case-NNN-step-1"]
}
```

Allowed readiness buckets are defined by the dataset's `readiness-policy.json`. A trajectory occupies exactly one bucket even if it exercises several skills.

## Trainable row

Rows follow the existing Qwen agentic data shape:

- unique `id`
- `case_id`, `trajectory_id`, `trajectory_step`, `trajectory_steps`
- `family_id`, `semantic_cluster`, `split`
- `provenance`, `source_record`, `review_status`, `task_status`
- `target_kind`: safe prefixes use `clarification` or `next_tool_action`
- exact tool schemas available to the model
- `messages`
- assistant-only `supervise_message_indices`
- trajectory-normalized `task_weight`

For `safe_prefix`, tool-role messages are forbidden. A clarification target must be nonempty assistant text without tool calls; a next-action target must call a tool declared in that row. Stopping at the assistant tool call is valid. Captured tool results belong only in a stronger, explicitly reviewed provenance class.

## Evidence routing

| Evidence available | Allowed target |
|---|---|
| User prompt only | clarification, direct/no-tool, or next safe action |
| User summary of old Agent search | safe prefix only; old claims quarantined |
| Raw search result but no page read | search follow-up or crawl call; not detailed factual answer |
| Captured page text supporting claims | grounded completion candidate after review |
| Conflicting/failed/unavailable evidence | bounded answer, clarification, additional search, or quarantine |

## Split and leakage

- All rows from one `trajectory_id` stay together.
- Related venue/event/source/paraphrase families require group-aware split.
- Heldout data cannot be used to tune prompts, labels, or hyperparameters and still be called independent.
- A newly collected failure used to design the training policy is not a pristine independent test unless reserved before inspection.

## Readiness interpretation

The validator reports two project gates:

- **Bounded pilot:** minimum diverse candidate pool for a limited experiment.
- **Full candidate:** larger pool for a formal v12 training proposal.

Neither report is training approval. Before any run, separately require independent dataset review, tokenizer/chat-template round-trip, assistant-mask validation, no truncation, group-aware split checks, GPU preflight, and explicit user authorization tied to exact hashes.
