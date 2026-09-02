# -*- coding: utf-8 -*-
"""The full DRG backlog, assembled and ordered by issue key.

Keys are allocated in creation order, so a low key means an early ticket:
  DRG-1 .. DRG-16     epics cut in the inception workshop, 02 Jan 2025
  DRG-17              the QA epic, cut 15 Jun 2026 when the QA analyst joined
  DRG-18              the BA epic, cut 17 Aug 2026 ahead of the BA starting
  DRG-19 .. DRG-78    year one, sprints 1-26 (2025)
  DRG-79 .. DRG-125   year two, sprints 27-44 (2026)
  DRG-126 .. DRG-130  backlog items, raised at the point of deferral
"""

from backlog_common import PEOPLE, JOINED, EMAIL      # noqa: F401 (re-exported)
from backlog_epics import EPICS
from backlog_year1 import YEAR1
from backlog_year2 import YEAR2

ISSUES = sorted(
    EPICS + YEAR1 + YEAR2,
    key=lambda i: int(i["key"].split("-")[1]),
)
