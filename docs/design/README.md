# Design documentation

Two formal deliverables, authored as self-contained HTML and rendered to PDF.

| Document | Ref | Pages | Contents |
|---|---|---|---|
| [DRG_Business_Requirements.pdf](DRG_Business_Requirements.pdf) | DRG-BRD-001 | 28 | Business context, objectives with measurable success criteria, scope, stakeholder analysis and RACI, as-is/to-be process, 18 business + 33 functional + 12 non-functional requirements, data requirements, risks, 20 acceptance criteria, benefits, glossary, full traceability matrix |
| [DRG_Architecture_Design.pdf](DRG_Architecture_Design.pdf) | DRG-SAD-001 | 37 | Project overview and scope, system context, layered architecture, **10 UML diagrams**, data architecture, ML architecture, security and governance, NFR realisation, technology stack, risks and limitations, repository map, API reference |

## UML model (in DRG-SAD-001, section 7)

| # | Diagram | Answers |
|---|---|---|
| 7.1 | Use case | Who uses the system and for what |
| 7.2 | Component | How the system decomposes, and which package realises each part |
| 7.3 | Class | The domain model: stress, electrification and model types |
| 7.4 | Sequence - scenario evaluation | How a scenario is computed, and why thresholds are frozen first |
| 7.5 | Sequence - replay tick | How a rolling forecast and pre-emptive alert are produced |
| 7.6 | Sequence - model release | How a retrained model is gated, staged, verified and released |
| 7.7 | Activity | The end-to-end pipeline, including the adoption-grid loop |
| 7.8 | State machine - stress severity | Normal -> Watch -> Elevated -> High -> Critical |
| 7.9 | State machine - model lifecycle | Trained -> Gated -> Registered -> Staged -> Serving -> Retired |
| 7.10 | Deployment | The Azure topology and the shared-volume design |

## Regenerating the PDFs

The HTML sources are the masters. To re-render after an edit:

```bash
chrome --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="docs/design/DRG_Architecture_Design.pdf" \
  "docs/design/DRG_Architecture_Design.html"
```

Any Chromium-based browser works (`msedge` on Windows). The documents use `@page` rules for A4
sizing and margins, CSS counters for section, figure and table numbering, and inline SVG for every
diagram, so no external tooling, fonts or image assets are required.
