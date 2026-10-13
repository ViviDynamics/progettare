# Issue 56: comment-thread participation

## Problem
The receiver fires on assignment and labeling only; comment events
answer ignored. The smoke test on #55 showed what users actually want:
the issue body is the task definition, and the comment thread is where
project management, developers, and progettare converge on the
strategy — with progettare as a participant.

## Rulings
- Trigger gates, in order, each cheap and each visible: the author is
  the bot itself (self-loop guard), then an authorized reviewer
  (configuration `PROGETTARE_REVIEWERS`, defaulting to the repository
  owner taken from the event), then an explicit address
  (`@vivi-progettare[bot]` in the body), then an open issue. Anything
  else answers ignored.
- Revision rounds are bounded: a per-issue counter in the delivery
  ledger, capped by `PROGETTARE_MAX_ROUNDS` (default 2). A comment
  past the cap posts a one-line exhaustion note and starts nothing; the
  delivery is still recorded, so a redelivery of it answers duplicate.
- `handle_event` widens its ceremony seam to `ceremony(ref, repo_path,
  revision)`: 0 for assignment/labeling, the round number for comment
  rounds. The revision flows into the outcome document and the
  comment lead.
- The ceremony reads the thread itself through the existing gh seam
  (`load_comments` beside `load_issue`), so the receiver needs no
  capturing gh seam. The thread enters at intake: `assemble` gains the
  conversation, `CardContext` carries it into the run artifacts, and
  `plan_for` adds a "conversation so far" section to the survey plan.
  The acceptance criteria still come from the body alone — the thread
  is context, not criteria.
- The outcome document gains a `revision` field; the comment lead says
  "revision N" when N > 0, so a thread shows its rounds at a glance.

## Acceptance
A maintainer's comment addressing the bot yields a revised plan that
consumes the thread; the bot's own comments are inert; an
unauthorized author's comment is ignored; the round cap holds and is
visible; redeliveries of comment events stay harmless.
