---
name: grill-me-softly
description: Smart design interview using an in-memory decision tree. Asks lowest-confidence questions first, supports "skip for now", and lets users stop early with recommendations auto-applied to skipped questions. Use when user wants to stress-test a plan with more control, or mentions "grill me softly".
---

STARTER_CHARACTER = 🔥

<what-to-do>

## Session Start

1. Greet the user and explain in one short paragraph:
   - Questions are asked one at a time, lowest-GPP first.
   - "Skip for now" moves a question to the end.
   - "Accept all remaining" stops early and applies recommendations.
   - Each question shows questions left.

2. Build initial decision tree from plan in memory. It is a dependency graph, not a positional tree: stable IDs never encode a branch position.

3. Ask lowest-GPP eligible node immediately. Do not use subagents, background reordering, answer patches, or unrelated fallback questions.

## In-Memory State

Maintain:

- meta
  - topic
  - remaining_count
  - question_index
  - num_reprioritizations
- nodes[]
  - id
  - question
  - topic
  - status                  # pending | answered | skipped-pending | pruned
  - no_input_retries        # 0 until re-asked after no input; max 1
  - answer_raw
  - answer_summary
  - selected_option_id
  - recommended_option_id
  - dependencies[]
  - when[]
  - options[]
    - id
    - text
    - gpp

Rules:

- Memory is source of truth while session is active.
- Keep `question` text stable unless user explicitly asks to rewrite it.
- An eligible node is `pending`, has all dependencies answered, and its conditions match recorded answers.
- Recommendation is highest-GPP option.
- After each resolved answer, write one complete recovery snapshot to `grill-me-decision-tree.yaml` in session `files/`. Snapshot supports recovery after compaction or interruption; never read it during normal routing.
- Treat a question as skipped only after an explicit selection of the "Skip for now" action or an exact, case-insensitive user reply of `skip for now`. Do not infer a skip from blank, pasted, unrelated, malformed, or ambiguous input.
- If input includes a recognizable option selection plus other pasted text, resolve that selected option. If no option or explicit action is recognizable, follow the no-input retry rule instead; retain the question in its current position.

## Per Question

- Label **`Q<N> (<remaining> left)`**.
- Show the question text.
- Always provide 2–4 distinct options with GPP scores and mark the recommendation: `1. Option text (GPP: 0.65) ✓ recommended`.
- Always print numbered options directly in the chat message, followed by:
  - `<N+1>. Skip for now`
  - `<N+2>. Accept all remaining`
- Users must be able to answer by typing only the option number (the numeric identifier serves as the quick-reply token).
- Always display all options directly in the chat message; do not use choice tools or `ask_user` dialogs that collapse or hide options.

## After Each Answer

### 0) No input

- If `no_input_retries` is `0`, set it to `1` and render identical question again without changing status, queue position, or remaining count. This is a retry, not a skip: do not move it to the end.
- If `no_input_retries` is `1`, apply highest-GPP option and process it as a recommended answer.
- Explicit quick replies, "skip for now", "accept all remaining", and "stop early" are not no input. Only the exact "Skip for now" action triggers skip behavior.

### 1) Recommended option

- Mark node `answered`, save selected option, write recovery snapshot, and ask next eligible pending node in current order.
- Do not reprioritize.

### 2) Another option or freeform answer

- For freeform input, save exact `answer_raw`, create concise `answer_summary`, and map it to closest option or add a materially distinct option.
- Mark node `answered`, save normalized option, increment `num_reprioritizations`, and reprioritize remaining pending nodes in memory.
- Prefer questions impacted by decision, prune now-redundant nodes, and add only clearly useful implied questions.
- Write recovery snapshot, briefly state what shifted, then ask next eligible question immediately.

### 3) Skip for now

- Set node `skipped-pending`, move it after normal pending nodes, and ask next eligible pending node.
- Do not reprioritize or write a snapshot; no answer has been resolved.

### 4) Accept all remaining or stop early

- Apply highest-GPP option to every `pending` and `skipped-pending` node, mark all `answered`, write recovery snapshot, and finish.

## Skipped Questions Phase

When normal pending nodes end, surface `skipped-pending` nodes one by one.

- **Accept recommendation** applies highest-GPP option, marks node answered, writes recovery snapshot, and asks next eligible node.
- **Accept all remaining** applies highest-GPP option to every skipped node and ends interview.
- Another answer follows normal handling.
- A repeated skip remains at end.

## Completion

Once all nodes are answered, accepted, or pruned, print 3-5 sentences covering pivotal decisions and tradeoffs, then:

`Number of reprioritizations: <N>`

Do not act on the plan until the user confirms shared understanding.

</what-to-do>

<tree-schema>

Recovery snapshot: `grill-me-decision-tree.yaml` in session `files/`.

```yaml
meta:
  workflow_version: 3.0
  topic: "<plan name>"
  remaining_count: 12
  question_index: 3
  num_reprioritizations: 1

nodes:
  - id: q-auth-model
    question: "Which authentication model?"
    topic: identity
    status: answered
    no_input_retries: 0
    answer_raw: "SSO"
    answer_summary: "Use SSO."
    selected_option_id: option-sso
    recommended_option_id: option-sso
    dependencies: []
    when: []
    options:
      - id: option-password
        text: Password
        gpp: 0.20
      - id: option-sso
        text: SSO
        gpp: 0.65
```

Snapshot is recovery-only. On resume, load it into memory, validate statuses and dependencies, then resume normal in-memory routing.

</tree-schema>

<supporting-info>

## Domain awareness

Before building tree, invoke `/agent-wiki-query`. Use known terminology, decisions, and gotchas. If no wiki exists, explore code.

### Issue Tracker context (optional)

At session start, check `.github/issue-tracker.md`. If absent, malformed, unsupported, inaccessible, or configured CLI unavailable, continue unchanged. Never block decision tree creation.

Validate supported `type`, AXI `cli` path, `project`, and token-env variable name. Invoke configured CLI only; never use REST or expose token values.

Perform at most one bounded lookup when user names an issue ID, feature, component, dependency, acceptance criterion, milestone, or requests tracker context. Ask only when policy requires consent, target is ambiguous, or lookup would be broad or disruptive. Tracker facts supplement wiki knowledge.

## During the session

Challenge terms against wiki definitions. Sharpen vague language into canonical terms. Stress-test with concrete edge cases, especially freeform or non-recommended answers. Check claims about code against code. Record resolved terminology with `/agent-wiki-update`.

## Visual Companion (just-in-time)

Offer `lavish` only for a genuinely visual question, in its own message:

> "This next question might be easier to answer visually — I can put together options in a browser tab. Want me to? I'll open it for you."

If accepted, invoke `lavish`; use `comparison` or `input` for option choices and `diagram` for architecture. Run `npx -y lavish-axi playbook <id>` before writing `.lavish/visual-options.html`. Do not offer again after decline unless user raises it.

</supporting-info>
