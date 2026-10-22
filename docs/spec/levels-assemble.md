# Stages 6 and 8: levels and assembly (§6, §8)

Part of the design spec; index: [docs/SPEC.md](../SPEC.md).

## 6. Stage 6 — Levels (`levels.py`)

```
level 1: kind=letter (caps title)
         kind=titled whose label ∈ LEVEL1_LABELS, first_on_page, no annexure open   (f2 NIT, PQC, BRC, ATC, LIST OF ANNEXURES)
         kind=named with keyword ∈ {section, part, chapter}
level 2: kind=named, keyword ∈ {annexure, appendix, schedule, form, format, exhibit}, id without dots   ("Annexure 19")
level 3: same, one dot                                                                                ("Annexure 3.2")
level 4: same, two dots                                                                               ("Annexure 2.6.1")
level ≥3: kind=numeric (depth = dots + 3)
sub-headings sit one level below the innermost structural heading (a level-1 section, a named id, an emitted clause),
so siblings share a level:
          kind=titled NOT first_on_page, or inside an annexure → max(3, that + 1)   (f2 p29 MSE sub-heading, f2 p81 …)
          kind=letter whose title is not in capitals → that + 1                    (Annexure 3's "E." "F." "G.")
          kind=layout_only → that + 1; a following layout_only ≥ 2 pt smaller is one deeper, the same size a sibling
```
`LEVEL1_LABELS = {nit, pqc, brc, atc, annexure_list, itb, gcc, scc, sor, tech_spec, scope, checklist}`.

Rules:
- A level-2+ `named` heading nests under the most recent level-1 section (f1: under `D`; f2: under `LIST OF ANNEXURES`).
- `Annexure 3.2` nests under `Annexure 3` if `3` exists. If the nominal parent does not exist (`Annexure 7.2` / `7.2.1` on both fixtures — there is no `Annexure 7`), the heading **keeps its nominal level** and attaches to the nearest existing ancestor. No warning; tender numbering is thematic.
- A `titled` candidate that is the looked-up title of a bare-id heading on the same page (§5b) is **consumed** by that heading, not a separate section (f2 p58 `SCHEDULE OF RATES` belongs to `Annexure 19`).
- `config.max_emit_level` (default 4): deeper headings are kept in debug but not emitted. `config.emit_numeric_clauses` default `False` — GPC clauses 1–41 inside f1 Annexure 18 and SCC clauses 1–30 inside f2 Annexure 20 stay internal.
- Font size as tie-break only: two consecutive `layout_only` headings differing by ≥ 2 pt → the smaller is one level deeper.

## 8. Stage 8 — Assemble (`assemble.py`)

Input: accepted candidates with `(page, y0, level)`.

1. Sort by `(page, y0)`.
2. `starts_mid_page = not first_on_page`.
3. End page rule:
   ```
   for each heading H (in order):
       N = the next heading outside H's subtree
       if N is None:            H.end = last_page
       elif N.starts_mid_page:  H.end = N.start            # the two share a page
       else:                    H.end = N.start - 1
   ```
   `end_page_exclusive` uses the same rule with N = the next heading of **any** level.
   The subtree decides, not the level: an orphan Annexure 7.2 (there is no Annexure 7) keeps level 3 but hangs under the level-1 section, so it ends Annexure 6 (f1 `[29, 31]`, f2 `[33, 35]`). "The next heading with level ≤ H.level" would run Annexure 6 on to Annexure 8.
4. The tree, built before the end pages: a heading hangs under the nearest open heading of a lower level; a dotted named id under its deepest existing ancestor id, or, as an orphan, under the nearest heading of another family (the level-1 section). `Section.children` in document order. A parent's `end_page` equals its last descendant's `end_page` by construction — assert it, and that every range ends on or after its start.
5. Flat views:
   - `flat_inclusive[id] = [start, end_page]` — parent includes children. f1 `annexure_list = [14, 67]`, `annexure_2 = [18, 23]`; f2 `annexure_list = [17, 85]`, `annexure_15 = [50, 54]`.
   - `flat_exclusive[id] = [start, end_page_exclusive]` — parent stops before its first child. f1 `annexure_list = [14, 15]`; f2 `annexure_15 = [50, 51]`.
   - Leaves are identical in both. Keys = canonical label for level 1 (`pqc`, `nit`, `annexure_list`; `sec_B` fallback), `<keyword>_<id with dots→_>` for named ids, `p{page}_{label}` for other sub-headings; a repeated key gets `_2`, `_3`.
6. `unassigned_pages` = pages not covered by any level-1 inclusive range (f1 `[1, 2]`; f2 `[1]`).

Walk-through (f2):
```
LIST OF ANNEXURES (L1) starts 17 → no later L1 → end 85; exclusive: Annexure 1 at 19 → 18
Annexure 1 (L2) starts 19 → 1.1 at 20 is in its subtree → Annexure 2 (L2) at 21 → end 20; exclusive 19
Annexure 6 (L2) starts 33 → 6.1 at 35 in its subtree → 7.2 (orphan, under LIST OF ANNEXURES) at 36 → end 35; exclusive 34
Annexure 7.2 (L3, orphan) starts 36 → 7.2.1 in its subtree → Annexure 8 (L2) at 40 → end 39; exclusive 38
Annexure 21 (L2) starts 79 → nothing after → end 85 (pp84–85 image-only, no OCR needed)
```
