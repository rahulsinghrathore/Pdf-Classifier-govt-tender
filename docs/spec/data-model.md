# Data model: pages, tables, index entries (§2)

Part of the design spec; index: [docs/SPEC.md](../SPEC.md).

## 2. Data model (`models.py`, pydantic v2)

```python
class Line(BaseModel):
    page: int                 # 1-based physical page
    text: str                 # merged logical line: NFKC, straight quotes, whitespace-collapsed (§3)
    x0: float; y0: float; x1: float; y1: float   # normalized 0..1 to page size
    font_size: float          # max span size on the line
    bold_ratio: float         # chars in bold spans / total chars
    caps_ratio: float         # uppercase letters / letters (0 if < 4 letters)
    in_table: bool            # centre inside a find_tables() table of ≥ 2 rows
    is_boilerplate: bool = False
    in_index_block: bool = False
    order: int                # index within page after y-sort

class TableRow(BaseModel):
    bbox: BBox                # normalized
    cells: list[str]          # "" for an empty cell

class Table(BaseModel):
    bbox: BBox
    rows: list[TableRow]

class Page(BaseModel):
    number: int               # physical, 1-based
    width: float; height: float   # points
    printed_number: int | None
    has_text_layer: bool | None   # decided in stage 2, AFTER boilerplate: ≥20 chars of non-boilerplate text
    is_image_only: bool | None    # no text layer and (an image or ≥ 50 vector paths); None before stage 2
    needs_ocr: bool | None        # image-only AND ocr enabled
    body_font_size: float     # char-weighted mode over non-boilerplate lines; the document's on sparse pages (§3)
    lines: list[Line]
    image_count: int
    drawing_count: int        # vector paths: a CAD drawing may have no raster image
    tables: list[Table]       # rows feed the index route of §5a
    is_index_page: bool = False
    ocr: bool = False         # OCR added lines to this image-only page (§3); off by default

class BoilerplateGroup(BaseModel):  # one repeated header/footer (§4); its first occurrence can be re-admitted
    band: Literal["top", "bottom"]
    text: str; pages: list[int]; first_page: int; first_order: int

class IndexEntry(BaseModel):
    id_norm: str              # "annexure_19", "sec_B"
    display_id: str           # "Annexure 19"
    description: str | None   # "Schedule Of Rates (SOR)"; None when the cell is empty or a placeholder ("None")
    applicability: Literal["applicable", "not_applicable", "external"]
    page: int                 # where the entry was read

class ParsedDocument(BaseModel):    # the document as stages 1–3 leave it
    file_name: str | None; page_count: int; pages: list[Page]; bookmarks: list[Bookmark]
    printed_page_offset: int | None; boilerplate_groups: list[BoilerplateGroup]
    index_entries: list[IndexEntry]; warnings: list[Warning]
```
