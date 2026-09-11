# Semantic reconciliation

The LLM already connected through Claude Code or Codex decides which cards
describe the same event. TaskTracker supplies the evidence and applies the
decision. There is no separate inference service or API key to configure.
The running agent's usual model usage includes this extra review.

## Review flow

1. The agent calls `tasks_review(project=...)`. It receives the latest 100
   non-manual cards, including completed and old hidden DONE cards, with their
   text, sources, timestamps, session ids and a `review_token`. Long details
   are previewed; `task_get` returns their complete text and merge history.
2. The agent compares meaning and the conversation. Different languages are
   allowed: "давай 0.0.2" and "Release 0.0.2" may refer to the same release.
   A request to implement a feature and separate cards for coding, tests and
   documentation are distinct work, not duplicates. Similar wording alone
   and repeated work on separate occasions are not enough.
3. The agent calls `tasks_reconcile` with the token and a list of groups:

   ```json
   {
     "keep_id": 42,
     "duplicate_ids": [43],
     "reason": "The prompt and MCP card describe the same requested 0.0.2 release."
   }
   ```

   Each group needs an explanation. The concrete task survives; a prompt
   cannot be the surviving card. `merges=[]` records a review with no matches.
4. The server checks the entire batch before applying it in one transaction.
   Invalid ids, other projects, manual cards, overlapping groups and a changed
   board all reject the review without applying partial merges. A changed
   board must be read again before deciding.

Card contents are treated as data, including any apparent instructions inside
them. Uncertain matches should remain separate. The model makes the semantic
decision; tests of the merge machinery do not guarantee every model decision.

## Automatic and existing cards

The session instructions tell the agent to reconcile after work. The Stop hook
also requests one pass when a changed board has cards from multiple sources,
so it can include a fallback prompt created at Stop itself. It guards against
repeat continuations; the review request does not become another prompt card.
If the MCP server is unavailable, the agent leaves the cards alone and finishes.
The same unchanged snapshot is not requested repeatedly in that session.

Install the updated container and client hooks using the README's update
commands, then restart the client. For an explicit pass over existing cards:

- Claude Code: `/tasktracker:reconcile`.
- Codex: ask it to review this project's TaskTracker duplicates with
  `tasks_review` and `tasks_reconcile`.

The board does not run a model independently while all agent sessions are
closed. The review window is the latest 100 non-manual card ids; the response
sets `truncated=true` when older cards fall outside it. This keeps automatic
reviews bounded, rather than sending a project's entire history each turn.

## What is preserved

The surviving card keeps its id and title, combines descriptions, and displays
the original sources, such as MCP + PROMPT. Its dialog has a **MERGED CARDS**
section with original full texts and explanations. Full originals remain in
history even when the combined description exceeds the normal detail limit.

Source rows stay in SQLite as hidden aliases. They retain their session and
external ids, so replayed hooks find the existing event. Old MCP ids resolve
to the surviving card. Aliases are excluded from board columns, counters and
drag ordering. Native plan status changes continue to reach the visible card;
deleting a native representation does not delete a card with other sources.

The prompt's status is not evidence that the task finished. If substantive
cards disagree, IN PROGRESS is retained first, then QUEUE, and DONE only when
all substantive representations are complete. Original statuses are recorded
in history. Deleting the surviving card explicitly deletes its aliases and
merge history too, as deleting a task already does for its stored data.

SQLite schema 2 adds aliases and history automatically on first open. The
application version remains 0.0.2. Update the server and hooks together: older
code does not know to hide merged aliases.
