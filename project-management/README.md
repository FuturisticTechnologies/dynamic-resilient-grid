# DynamicResilientGrid — Jira backlog and Slack transcript

Generated project-management artefacts for DRG, covering the project from its
start on **02 Jan 2025** to the current sprint (today: 09 Sep 2026) — 20 months
and 43 two-week sprints. Content is derived from the repository itself, so
every ticket references real modules, real results and the real proposal
objectives.

## The team

| Person | Role | On the project from |
| --- | --- | --- |
| Geetha Nallamada | Data Analyst — modelling lead | 02 Jan 2025 |
| Divya Maram | Data Analyst — data, features, simulation | 02 Jan 2025 |
| Devendranath Singam | DevOps Engineer | 02 Jan 2025 |
| Sabitha Lingala | Project Coordinator | 02 Jan 2025 |
| Neha Chauhan | QA Analyst | 15 Jun 2026 |
| Amit Shinde | Business Analyst | 24 Aug 2026 |

All addresses are `firstname.lastname@futuristictechnologies.co.uk`.

The build **enforces** the joining dates: no ticket is assigned to, and no
comment or Slack message written by, someone who had not yet joined. Neha's
first contribution is 16 Jun 2026, Amit's 25 Aug 2026.

## Files

| File | What it is |
| --- | --- |
| `drg_jira_issues.csv` | 130 issues (18 epics, 76 stories, 23 tasks, 13 bugs) with inline `Comment` columns — the Jira import file |
| `drg_jira_comments.csv` | the same 265 comments in long form, one row per comment, with author role and email |
| `drg_slack_messages.csv` | 279 Slack messages across 6 channels, 56 threaded — the readable version |
| `drg_slack_import.csv` | the same messages in Slack's CSV import format, ticket key in the text |
| `drg_slack_import_<channel>.csv` | one file per channel, importable on its own |

Regenerate with:

```
python project-management/build_jira_csv.py
```

Source data: `backlog_common.py` (people, the 43-sprint calendar),
`backlog_epics.py`, `backlog_year1.py` (2025), `backlog_year2.py` (2026),
`data_slack.py` (the narrative transcript) and `data_slack_extra.py`
(ceremonies, releases, monthly reporting).

## Importing

**Jira Cloud** → Settings → System → External System Import → CSV. Set the date
format to `yyyy-MM-dd HH:mm:ss`, map `Epic Link` to Parent (team-managed) or
Epic Link (company-managed), and map all four `Comment` columns to Comment —
each cell is `date;author;body`.

**Slack** → Settings → Import/Export Data → CSV, using `drg_slack_import.csv`.
Slack reads columns **positionally** (`timestamp, channel, username, message`),
not by header, so importing the readable transcript by mistake creates one
channel per message. Timestamps are Unix epoch seconds; set `SLACK_EPOCH =
False` to emit ISO instead. Channels must already exist — edit `SLACK_CHANNELS`
in the builder to point at the ones in your workspace.

## Working hours

Every timestamp — ticket dates, comments and Slack — falls Monday to Friday,
09:00–17:00, and the build fails otherwise. Set `BUSINESS_HOURS = False` to
keep the authored times instead.

## Structure

**18 epics.** DRG-1 to DRG-16 were cut in the inception workshop on 02 Jan
2025; DRG-17 (Quality Engineering) was added the day the QA analyst joined and
DRG-18 (Business Analysis) a week before the BA started. Keys are allocated in
creation order, so a low key is an early ticket.

**43 sprints** from Mon 06 Jan 2025, plus 5 backlog items with no sprint.
Sprint 44 is current: 109 issues Done, 12 In Progress, 9 To Do.

The sequence follows the seven proposal objectives: data → analysis → features
→ models → stress → scenarios → sensitivity → explainability → interfaces →
deployment. No forecasting model existed until Q3 2025, deliberately — the
first quarter went on making the data trustworthy, and the Q1 stakeholder
review has the exchange about it.

## The bugs are the interesting part

Thirteen bugs, and twelve of them produced a **plausible wrong number** rather
than a failure:

| Key | What went wrong |
| --- | --- |
| DRG-27 | Half-hourly index broke at both BST clock changes — duplicate timestamps in October, missing in March |
| DRG-37 | Missing half-hours silently forward-filled during aggregation, fabricating evening peaks |
| DRG-46 | Rolling window was centred, so a feature contained the half-hour it was predicting — 0.11 MAE |
| DRG-53 | Naive baseline docstring said "last week", the code shifted a day |
| DRG-58 | Scaler fitted on the full series including the test window |
| DRG-65 | PyTorch installed cleanly on Windows and failed on import — missing MSVC runtime |
| DRG-69 | Stress threshold computed over the whole series, flattering every model equally |
| DRG-80 | Diversity lost — combined EV and heat pump peak came out additive, overstating by 29 points |
| DRG-87 | Replay windows driven by wall clock, so replays were non-deterministic |
| DRG-95 | SHAP computed on scaled features and labelled with raw units |
| DRG-103 | API responses omitted the model version the OpenAPI schema promised |
| DRG-107 | A retrain improved MAE and got worse at stress — the promotion gate blocked it |
| DRG-110 | Dashboard served one neighbourhood's data under another's label |

Three of those (DRG-46, DRG-58, DRG-69) are the same class — something fitted
on more data than it should have seen. The third one produced a standing rule
rather than a third individual fix, and DRG-100 later turned that rule into
enforced assertions.

## Slack channels

`#drg-general` (decisions), `#drg-eng` (platform, CI, infrastructure),
`#drg-modelling` (features, models, stress, simulation, explainability),
`#drg-standup` (standups and ceremonies), `#drg-releases` (tags and hotfixes),
`#drg-stakeholders` (monthly reporting to network planning, sustainability and
the academic partner).

The transcript tracks the tickets: the week the dataset licence answer landed
and reshaped the plan, the three leakage bugs and the rule that came out of
them, the morning the combined electrification scenario came out suspiciously
round, and the retrain the promotion gate refused.

## Git history

`build_git_history.py` reconstructs the repository as it would have been
built, 02 Jan 2025 – 09 Sep 2026:

| | |
| --- | --- |
| `main` | release branch — a merge of `development` at the end of every sprint that delivered work (37 releases) |
| `development` | integration branch |
| `drg/DRG-nn-<slug>` | 77 working branches, one per ticket — **kept, never deleted** |

Each working branch is cut off `development`, carries commits by the ticket's
assignee, takes a **merge of `development` back in** when development has moved
on underneath it (32 of the 77 did), and is then merged in with a merge commit.
242 commits in all.

```
python project-management/build_git_history.py --dry-run   # plan only
python project-management/build_git_history.py --force     # rebuild
```

**Real diffs, not file drops.** Where a later ticket changed a file an earlier
one wrote, the earlier commit carries the file as it stood before, and the
later one carries the change: `engineering.py` grows across DRG-42, 44, 43, 45
and 48; the dashboard gains its panels in DRG-97, 104 and 108; the API its
endpoints in DRG-102. Twelve of the thirteen bugs above are real fixes on
their branch (DRG-107 changed no code — the gate did its job). The build fails
if any revision pattern stops matching, so none can silently become an empty
diff.

**Safety.** Commits are written with git plumbing from the objects of the
current `main` commit — nothing is checked out and nothing is pushed. The
original `main` is kept as the tag `pre-history-snapshot`, and the build
asserts the final `development` and `main` trees are **identical** to the
source tree, so no file can be lost, added or altered.

**Authors and dates** match the Jira export: every commit is by the ticket's
assignee, on a weekday between 09:00 and 17:00 UK time (GMT or BST as the date
requires), and never before its author joined — Neha's first commit is after
15 Jun 2026, Amit's after 24 Aug 2026. Release merges into `main` are by
Devendranath Singam.
