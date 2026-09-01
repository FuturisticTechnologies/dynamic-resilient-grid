"""Generate Jira import CSVs + a Slack transcript for DynamicResilientGrid.

Project start: 2025-01-02. Today: 2026-09-09. 43 two-week sprints.

Outputs (project-management/):
  drg_jira_issues.csv     Jira Cloud CSV import file (epics, stories, tasks,
                          bugs) with inline Comment columns.
  drg_jira_comments.csv   the same comments, long form, one row per comment.
  drg_slack_messages.csv  readable Slack transcript keyed to the Jira issues.
  drg_slack_import.csv    the same messages in Slack's CSV import format,
                          plus one file per channel.

Import notes for Jira Cloud (External System Import -> CSV):
  * Date format:  yyyy-MM-dd HH:mm:ss
  * Map every "Comment" column to the Comment field.
  * Map "Epic Link" to Parent (team-managed) or Epic Link (company-managed).

Import notes for Slack (Settings -> Import/Export Data -> CSV):
  * Slack reads columns positionally: timestamp, channel, username, message.
    If the channel is not in column 2, Slack offers to create one channel per
    value it finds there.
  * Timestamps are Unix epoch seconds (UTC). Set SLACK_EPOCH = False to emit
    "yyyy-MM-dd HH:mm:ss" instead.
  * Edit SLACK_CHANNELS to point at channels that exist in the workspace.
"""

import csv
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from data_issues import ISSUES, PEOPLE, JOINED, EMAIL     # noqa: E402
from data_slack import SLACK                              # noqa: E402
from data_slack_extra import EXTRA                        # noqa: E402

# Ceremonies, releases and monthly reporting live in a second module; they are
# one transcript for every purpose after this point.
SLACK.extend(EXTRA)

PROJECT_START = dt.date(2025, 1, 2)

# --------------------------------------------------------------------------
# Slack target channels. Left: the channel the transcript was written against.
# Right: the channel in the workspace. Edit the right-hand side only.
# --------------------------------------------------------------------------

SLACK_CHANNELS = {
    "#drg-general":      "#drg-general",
    "#drg-eng":          "#drg-eng",
    "#drg-modelling":    "#drg-modelling",
    "#drg-standup":      "#drg-standup",
    "#drg-releases":     "#drg-releases",
    "#drg-stakeholders": "#drg-stakeholders",
}

SLACK_IMPORT_COLUMNS = ["timestamp", "channel", "username", "message"]
SLACK_EPOCH = True

# Everything happens Mon-Fri, 09:00-17:00. Set False to keep authored times.
BUSINESS_HOURS = True
FMT = "%Y-%m-%d %H:%M:%S"
DAY_START = dt.time(9, 0)
DAY_END = dt.time(17, 0)          # exclusive; last usable minute is 16:59


# --------------------------------------------------------------------------
# business hours: one monotonic remap shared by issues, comments and Slack, so
# ordering, thread parents and "resolved after created" all survive the shift
# --------------------------------------------------------------------------

def _timestamp_fields():
    for issue in ISSUES:
        for field in ("created", "resolved", "updated", "due"):
            if issue.get(field):
                yield issue, field
        for n, _ in enumerate(issue["comments"]):
            yield issue["comments"], n
    for msg in SLACK:
        yield msg, "ts"
        if msg.get("thread"):
            yield msg, "thread"


def _read(container, key):
    value = container[key]
    return value[0] if isinstance(value, tuple) else value


def build_business_hours_map():
    originals = {_read(c, k) for c, k in _timestamp_fields()}

    shifted = {}
    for stamp in originals:
        when = dt.datetime.strptime(stamp, FMT)
        if when.weekday() >= 5:                 # weekend -> preceding Friday
            when -= dt.timedelta(days=when.weekday() - 4)
        shifted[stamp] = when

    by_day = {}
    for stamp, when in shifted.items():
        by_day.setdefault(when.date(), []).append((when, stamp))

    mapping = {}
    for day, entries in by_day.items():
        entries.sort()
        floor = dt.datetime.combine(day, DAY_START)
        ceiling = dt.datetime.combine(day, DAY_END) - dt.timedelta(minutes=1)

        placed = []
        for when, stamp in entries:
            new = max(when, floor)
            if placed and new <= placed[-1][0]:
                new = placed[-1][0] + dt.timedelta(minutes=1)
            placed.append((new, stamp))

        for i in range(len(placed) - 1, -1, -1):
            limit = (ceiling if i == len(placed) - 1
                     else placed[i + 1][0] - dt.timedelta(minutes=1))
            if placed[i][0] > limit:
                placed[i] = (limit, placed[i][1])

        if placed and placed[0][0] < floor:
            raise RuntimeError(
                f"{day}: {len(placed)} timestamps will not fit in 09:00-17:00")

        for new, stamp in placed:
            mapping[stamp] = new.strftime(FMT)

    return mapping


def apply_business_hours():
    if not BUSINESS_HOURS:
        return 0
    mapping = build_business_hours_map()
    moved = 0
    for container, key in _timestamp_fields():
        value = container[key]
        if isinstance(value, tuple):                  # comment: (when, who, body)
            when, who, body = value
            moved += mapping[when] != when
            container[key] = (mapping[when], who, body)
        else:
            moved += mapping[value] != value
            container[key] = mapping[value]
    return moved


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def _d(stamp):
    return dt.datetime.strptime(stamp[:10], "%Y-%m-%d").date()


def validate():
    errors = []
    keys = {i["key"] for i in ISSUES}

    for issue in ISSUES:
        created = _d(issue["created"])
        if created < PROJECT_START:
            errors.append(f"{issue['key']}: created {created} before project start")

        for field in ("assignee", "reporter"):
            who = issue.get(field)
            if who and created < JOINED[who]:
                errors.append(f"{issue['key']}: {field} {who} assigned {created}, "
                              f"joined {JOINED[who]}")

        if issue.get("parent") and issue["parent"] not in keys:
            errors.append(f"{issue['key']}: unknown parent {issue['parent']}")

        previous = None
        for when, who, _ in issue["comments"]:
            if _d(when) < JOINED[who]:
                errors.append(f"{issue['key']}: comment by {who} on {when}, "
                              f"joined {JOINED[who]}")
            if _d(when) < created:
                errors.append(f"{issue['key']}: comment by {who} precedes created")
            if previous and when < previous:
                errors.append(f"{issue['key']}: comments out of order at {when}")
            previous = when

        if issue.get("resolved") and issue["resolved"] < issue["created"]:
            errors.append(f"{issue['key']}: resolved before created")

    posted = {}
    for msg in SLACK:
        if _d(msg["ts"]) < JOINED[msg["author"]]:
            errors.append(f"slack {msg['ts']}: {msg['author']} posted before "
                          f"joining {JOINED[msg['author']]}")
        if msg.get("issue") and msg["issue"] not in keys:
            errors.append(f"slack {msg['ts']}: unknown issue {msg['issue']}")
        if msg["channel"] not in SLACK_CHANNELS:
            errors.append(f"slack {msg['ts']}: {msg['channel']} has no target channel")
        posted[msg["ts"]] = msg
    for msg in SLACK:
        if msg.get("thread"):
            if msg["thread"] not in posted:
                errors.append(f"slack {msg['ts']}: thread parent not found")
            elif msg["thread"] > msg["ts"]:
                errors.append(f"slack {msg['ts']}: reply precedes its parent")

    if BUSINESS_HOURS:
        for container, key in _timestamp_fields():
            stamp = _read(container, key)
            when = dt.datetime.strptime(stamp, FMT)
            if when.weekday() >= 5 or not (DAY_START <= when.time() < DAY_END):
                errors.append(f"{stamp} is outside Mon-Fri 09:00-17:00")

    return errors


# --------------------------------------------------------------------------
# writers
# --------------------------------------------------------------------------

ISSUE_COLUMNS = [
    "Issue Type", "Issue Key", "Issue ID", "Summary", "Description",
    "Epic Name", "Epic Link", "Status", "Resolution", "Priority",
    "Assignee", "Reporter", "Story Points", "Sprint", "Components",
    "Labels", "Created", "Updated", "Resolved", "Due Date",
]


def write_issues(path):
    max_comments = max(len(i["comments"]) for i in ISSUES)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        out = csv.writer(fh)
        out.writerow(ISSUE_COLUMNS + ["Comment"] * max_comments)
        for n, issue in enumerate(ISSUES, start=1):
            comments = [f"{w};{who};{body}" for w, who, body in issue["comments"]]
            comments += [""] * (max_comments - len(comments))
            out.writerow([
                issue["type"], issue["key"], str(10000 + n), issue["summary"],
                issue["description"], issue["epic_name"], issue["parent"],
                issue["status"], "Done" if issue["status"] == "Done" else "",
                issue["priority"], issue["assignee"], issue["reporter"],
                issue["points"], issue["sprint"], issue["components"],
                issue["labels"], issue["created"],
                issue["updated"] or issue["resolved"] or issue["created"],
                issue["resolved"], issue["due"],
            ] + comments)
    return len(ISSUES), max_comments


def write_comments(path):
    rows = 0
    with open(path, "w", newline="", encoding="utf-8") as fh:
        out = csv.writer(fh)
        out.writerow(["Issue Key", "Issue Type", "Summary", "Sprint",
                      "Comment Date", "Author", "Author Name", "Author Email",
                      "Author Role", "Comment Body"])
        for issue in ISSUES:
            for when, who, body in issue["comments"]:
                out.writerow([issue["key"], issue["type"], issue["summary"],
                              issue["sprint"], when, who, PEOPLE[who]["name"],
                              EMAIL[who], PEOPLE[who]["role"], body])
                rows += 1
    return rows


def _ordered_slack():
    return sorted(SLACK, key=lambda m: (SLACK_CHANNELS[m["channel"]],
                                        m.get("thread") or m["ts"], m["ts"]))


def _slack_stamp(ts):
    if not SLACK_EPOCH:
        return ts
    when = dt.datetime.strptime(ts, FMT)
    return str(int(when.replace(tzinfo=dt.timezone.utc).timestamp()))


def _with_issue_key(msg):
    text, key = msg["text"], msg.get("issue")
    return f"[{key}] {text}" if key and key not in text else text


def write_slack(path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        out = csv.writer(fh)
        out.writerow(["Slack Channel", "Source Channel", "Timestamp", "Author",
                      "Author Name", "Author Email", "Author Role",
                      "Thread Parent", "Related Jira Key", "Message",
                      "Reactions"])
        for msg in SLACK:
            who = msg["author"]
            out.writerow([SLACK_CHANNELS[msg["channel"]], msg["channel"],
                          msg["ts"], who, PEOPLE[who]["name"], EMAIL[who],
                          PEOPLE[who]["role"], msg.get("thread", ""),
                          msg.get("issue", ""), msg["text"],
                          msg.get("reactions", "")])
    return len(SLACK)


def _write_import(path, messages):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        out = csv.writer(fh)
        out.writerow(SLACK_IMPORT_COLUMNS)
        for msg in messages:
            out.writerow([_slack_stamp(msg["ts"]),
                          SLACK_CHANNELS[msg["channel"]], msg["author"],
                          _with_issue_key(msg)])
    return len(messages)


def write_slack_import(directory):
    messages = _ordered_slack()
    written = [("drg_slack_import.csv",
                _write_import(os.path.join(directory, "drg_slack_import.csv"),
                              messages), "all channels")]
    for channel in sorted(set(SLACK_CHANNELS.values())):
        subset = [m for m in messages if SLACK_CHANNELS[m["channel"]] == channel]
        name = f"drg_slack_import_{channel.lstrip('#').replace('drg-', '')}.csv"
        written.append((name, _write_import(os.path.join(directory, name), subset),
                        channel))
    return written


def main():
    moved = apply_business_hours()
    errors = validate()
    if errors:
        print("VALIDATION FAILED")
        for e in errors[:40]:
            print("  -", e)
        if len(errors) > 40:
            print(f"  ... and {len(errors) - 40} more")
        return 1

    n_issues, max_c = write_issues(os.path.join(HERE, "drg_jira_issues.csv"))
    n_comments = write_comments(os.path.join(HERE, "drg_jira_comments.csv"))
    n_slack = write_slack(os.path.join(HERE, "drg_slack_messages.csv"))
    import_files = write_slack_import(HERE)

    by_type, by_status = {}, {}
    for i in ISSUES:
        by_type[i["type"]] = by_type.get(i["type"], 0) + 1
        by_status[i["status"]] = by_status.get(i["status"], 0) + 1
    sprints = {i["sprint"] for i in ISSUES if i["sprint"]}

    print(f"issues        {n_issues}  {dict(sorted(by_type.items()))}")
    print(f"status        {dict(sorted(by_status.items()))}")
    print(f"sprints       {len(sprints)} distinct")
    print(f"comments      {n_comments} (max {max_c} on one issue)")
    print(f"slack msgs    {n_slack}")
    for name, count, scope in import_files:
        print(f"  {name:<34} {count:>3}  {scope}")
    print(f"hours         {moved} timestamps moved into Mon-Fri 09:00-17:00")
    print("validation    OK - joining dates respected, ordering intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
