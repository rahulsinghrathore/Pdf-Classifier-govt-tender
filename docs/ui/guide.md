# Using the app: the page and its controls

Part of the user guide; next page: [the result tabs](tabs.md). Start it with `streamlit run app/streamlit_app.py` and open http://localhost:8501.

The app finds where the five business sections of a tender start and end: PQC (pre-qualification criteria), ATC (agreed terms and conditions), SCC (special conditions of contract), SOR (schedule of rates) and Tech Specs (technical specifications). It shows the PDF next to what it found, so you can check every answer against the page.

```
┌ Sidebar ─────────┐ ┌ Tender Section Extractor ──────────────────────────────────────────────┐
│ Settings         │ │ [Upload PDF]  [Run]   ingest ✓ · boilerplate ✓ · … · llm (1) ✓        │
│ LLM toggle       │ ├─────────────────────────────────┬──────────────────────────────────────┤
│ Model            │ │ ◀  Page (of 85) [58]  ▶         │ Targets: 🟢 PQC p11–13  🟢 ATC p15–16 │
│ Accept / Reject  │ │ ┌─────────────────────────────┐ │          🟢 SCC p69–78  🟢 SOR p58–68 │
│ Deepest level    │ │ │ the page, headings framed   │ │          🟢 Tech Specs p79–85        │
│ Target labels    │ │ │ in red                      │ │ Sections | JSON | Checks | Debug     │
│ Show debug       │ │ └─────────────────────────────┘ │ ▸ NOTICE INVITING TENDER · p2–10     │
└──────────────────┘ │ [ ] Embed original PDF          │ ▸ LIST OF ANNEXURES · p17–85         │
                     └─────────────────────────────────┴──────────────────────────────────────┘
```

## Top bar

| Control | What it does |
|---|---|
| **Upload PDF** | Choose one tender PDF from your computer. The page viewer opens on page 1 straight away; nothing is extracted yet. |
| **Run** | Extracts the sections with the current sidebar settings. Greyed out while the settings conflict (the sidebar shows why). |
| *Extracting…* box | Appears while Run works, one line per stage (ingest, boilerplate, index, scoring, llm, assemble, validate, labels). It closes as *Done · LLM calls: N*. |
| Stage line | Stays beside the buttons after a run, e.g. `ingest ✓ · … · llm (1) ✓`; the number is how many Claude calls the run made. |

## Sidebar: Settings

Any change here needs a new **Run**. Results already computed are kept, so switching back to earlier settings shows that result again without re-running.

| Control | What it does | Default |
|---|---|---|
| **Ask the LLM about unsure lines** | On: lines the rules are unsure about (score 4–7) go to Claude, which must quote the page to say yes. One call per tender, about a cent. Off: those lines are rejected, rules only, free. | on when `.env` has a key |
| **Model** | Which Claude model judges. *default* means `LLM_MODEL` from `.env`, else claude-sonnet-5-5. Greyed out while the LLM is off. | default |
| **Accept at score ≥** | Every heading-like line gets a score from 0 to 10; at or above this it is a section heading. Higher = stricter. | 8 |
| **Reject at score ≤** | At or below this a line is not a heading. Between the two numbers is the "unsure" band. Must stay below the accept score, or Run is disabled. | 3 |
| **Deepest level emitted** | How deep the section tree goes: 1 = top sections, 2 = Annexure N, 3 = Annexure N.M, and so on. Deeper headings are found but not listed. | 4 |
| **Target labels** | Which sections get a tile in the targets strip. Add or remove labels; at least one is needed. | the five above |
| **Show debug** | Adds the Debug tab (the raw evidence behind the result). No new run needed. | off |

## PDF viewer (left half)

| Control | What it does |
|---|---|
| **◀** / **▶** | Previous / next page; greyed out on the first / last page. |
| **Page (of N)** | Type or step to any page. Tiles and **Go** buttons on the right set it too. |
| Red frame | Drawn around every section heading that starts on the shown page, once a run has finished. |
| **Embed original PDF** | Also shows the real PDF, opened at the current page, with its own scrolling and search. Off by default: some browsers block it. |

## Targets strip (top of the right half)

One tile per target label. Click a tile to jump the viewer to it; hover to see where the answer came from.

| Tile | Meaning | Click goes to |
|---|---|---|
| 🟢 **PQC** p11–13 | Found: the section's first and last page. Hover shows its heading. | its first page |
| ⚪ **SCC** N/A | The tender itself lists it as Not Applicable; hover names the page, e.g. "listed as Not Applicable on p15 (Annexure 20)". | that listing page |
| 🔴 **SOR** absent | Not found. If the tender's index lists it, hover says where ("listed on p17 … but no section was found") — check that page. | the listing page, if any |

## Messages you may see

| Message | Meaning |
|---|---|
| *Upload a tender PDF to begin.* / *Press Run to extract.* | Nothing to show yet. |
| *Settings changed: press Run again.* | This file has a result, but for other settings. |
| *Cannot read …* | The file is not a readable PDF (damaged, or not a PDF). |
| *Extraction failed: …* | The run stopped. *ANTHROPIC_API_KEY is not set* means: turn the LLM toggle off, or add the key to `.env`. |
