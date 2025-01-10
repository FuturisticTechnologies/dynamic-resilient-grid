# -*- coding: utf-8 -*-
"""Shared people, sprint calendar and the issue constructor for DRG.

Project start: 02 Jan 2025. Today: 09 Sep 2026.
Two-week sprints from Mon 06 Jan 2025.
"""

import datetime as dt

G = "geetha.nallamada"      # Data Analyst - modelling lead
D = "divya.maram"           # Data Analyst - data, features, simulation
V = "devendranath.singam"   # DevOps Engineer
N = "neha.chauhan"          # QA Analyst          - from 15 Jun 2026
A = "amit.shinde"           # Business Analyst    - from 24 Aug 2026
S = "sabitha.lingala"       # Project Coordinator

DOMAIN = "futuristictechnologies.co.uk"

PEOPLE = {
    G: {"name": "Geetha Nallamada", "role": "Data Analyst", "slack": "@geetha"},
    D: {"name": "Divya Maram", "role": "Data Analyst", "slack": "@divya"},
    V: {"name": "Devendranath Singam", "role": "DevOps Engineer", "slack": "@deven"},
    N: {"name": "Neha Chauhan", "role": "QA Analyst", "slack": "@neha"},
    A: {"name": "Amit Shinde", "role": "Business Analyst", "slack": "@amit"},
    S: {"name": "Sabitha Lingala", "role": "Project Coordinator", "slack": "@sabitha"},
}

EMAIL = {key: f"{key}@{DOMAIN}" for key in PEOPLE}

JOINED = {
    G: dt.date(2025, 1, 2),
    D: dt.date(2025, 1, 2),
    V: dt.date(2025, 1, 2),
    S: dt.date(2025, 1, 2),
    N: dt.date(2026, 6, 15),
    A: dt.date(2026, 8, 24),
}

PROJECT_START = dt.date(2025, 1, 2)
SPRINT_ONE_START = dt.date(2025, 1, 6)      # the Monday after kickoff
SPRINT_LENGTH_DAYS = 14


def sprint_bounds(number):
    """(start, end) dates of sprint `number`, 1-based. Ends on the Friday."""
    start = SPRINT_ONE_START + dt.timedelta(days=(number - 1) * SPRINT_LENGTH_DAYS)
    return start, start + dt.timedelta(days=11)


def sprint_label(number):
    start, end = sprint_bounds(number)
    if start.year == end.year:
        return f"Sprint {number} ({start:%d %b} - {end:%d %b %Y})"
    return f"Sprint {number} ({start:%d %b %Y} - {end:%d %b %Y})"


def sprint_for(stamp):
    """The sprint a timestamp falls in. Dates before sprint 1 belong to it."""
    when = dt.datetime.strptime(stamp[:10], "%Y-%m-%d").date()
    if when < SPRINT_ONE_START:
        return sprint_label(1)
    number = (when - SPRINT_ONE_START).days // SPRINT_LENGTH_DAYS + 1
    return sprint_label(number)


def I(key, type, summary, status, description, parent=None, epic_name=None,
      assignee=None, reporter=S, priority="Medium", points="", sprint=None,
      components="", labels="", created="", resolved="", updated="", due="",
      comments=()):
    """One Jira issue.

    `sprint` is derived from the created date unless given explicitly, so the
    43-sprint calendar never has to be typed out by hand. Backlog items pass
    sprint="" to stay out of a sprint entirely.
    """
    if sprint is None:
        sprint = sprint_for(created) if created else ""
    return dict(
        key=key, type=type, summary=summary, status=status,
        description=description.strip(), parent=parent or "",
        epic_name=epic_name or "", assignee=assignee or "", reporter=reporter,
        priority=priority, points=points, sprint=sprint, components=components,
        labels=labels, created=created, resolved=resolved, updated=updated,
        due=due, comments=list(comments),
    )
