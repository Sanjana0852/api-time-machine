# Comparison Engine: Design

**Status:** proposed (Phase 1)

The comparison engine takes two JSON documents, an **old** response and a **new** one, and returns the list of differences between them. Each difference is classified as **breaking**, **safe** or **info**.

It is the core of API Time Machine. Everything else (API replay, history, dashboard, AI explanations) either feeds JSON into it or displays its output.

---

## 1. Goals and non-goals

**Goals**

- **Deterministic:** the same two inputs always produce the same list of changes, in the same order.
- **Pure:** no network, files, database or clock. Input in, output out. This makes it trivial to test.
- **Explainable:** every severity comes from a written rule (section 5), not a guess.
- **Conservative:** when unsure, report a possible break. A false alarm costs a developer a minute; a missed break can cost an outage.

**Non-goals for Phase 1** (may come later)

- Comparing HTTP status codes and headers (Phase 2 deals with HTTP)
- Matching array items by an ID field instead of by position (see section 7)
- User-configurable rules
- JSON Schema / OpenAPI comparison (we compare *sample responses*, not specifications)

---

## 2. JSON types

JSON has six kinds of value. Python's `json` module turns them into Python types:

| JSON | Example | Python |
|---|---|---|
| object | `{"a": 1}` | `dict` |
| array | `[1, 2]` | `list` |
| string | `"250"` | `str` |
| number | `250`, `2.5` | `int` or `float` |
| boolean | `true` | `bool` |
| null | `null` | `None` |

The engine names each value's type with a function `json_type(value)`, which returns a `JsonType` enum member:

`OBJECT`, `ARRAY`, `STRING`, `INTEGER`, `FLOAT`, `BOOLEAN`, `NULL`

It is a `StrEnum`, so each member also equals its lowercase string (`JsonType.INTEGER == "integer"`). Using an enum rather than bare strings means a typo is an immediate error instead of a silent mismatch.

Values that JSON cannot represent (tuples, sets, bytes, ...) raise `TypeError`.

**Decision 1: integer and float are separate types.** JSON has a single "number" type, but many client languages (Java, Go, C#, Kotlin) store whole numbers in an `int` field. If `250` becomes `250.5`, those clients fail to parse the response. Keeping the two separate lets us catch this.

**Gotcha: in Python, `bool` is a subtype of `int`.** `isinstance(True, int)` is `True`, so a naive type check would call `true` an integer. `json_type` must check for `bool` *before* `int`. This gets its own test.

---

## 3. Data model

```python
type JsonValue = dict[str, JsonValue] | list[JsonValue] | str | int | float | bool | None

class JsonType(StrEnum): ...  # see section 2

class ChangeKind(StrEnum):
    FIELD_ADDED   = "field_added"    # object key only in new
    FIELD_REMOVED = "field_removed"  # object key only in old
    TYPE_CHANGED  = "type_changed"   # same location, different json_type
    VALUE_CHANGED = "value_changed"  # same location, same type, different value
    ITEM_ADDED    = "item_added"     # array is longer in new
    ITEM_REMOVED  = "item_removed"   # array is shorter in new

class Severity(StrEnum):
    BREAKING = "breaking"  # likely to break existing clients
    SAFE     = "safe"      # structural change that well-behaved clients tolerate
    INFO     = "info"      # data changed, structure did not

@dataclass(frozen=True)
class Change:
    path: str              # where, e.g. "$.items[0].price"
    kind: ChangeKind       # what happened
    severity: Severity     # how bad
    old_value: JsonValue   # None for FIELD_ADDED / ITEM_ADDED
    new_value: JsonValue   # None for FIELD_REMOVED / ITEM_REMOVED
```

**Decision 2: `frozen=True`.** A `Change` is a fact about two documents and should never be modified after it is created, so it is safe to pass around without defensive copies. (It is not hashable in general: `old_value` and `new_value` can be dicts or lists.)

**Decision 3: absent vs. `null`.** `{"price": null}` and `{}` are different: in one the key exists with value null, in the other it doesn't exist. The engine keeps them separate: a missing key gives `FIELD_REMOVED`, while a value that becomes null gives `TYPE_CHANGED`.

One trade-off: for added/removed changes, the missing side is stored as `None`, which looks the same as JSON `null`. The `kind` field always disambiguates, so we accept this rather than adding a special "missing" marker.

---

## 4. Paths

Every change has a **path** saying where it is, in JSONPath-style notation:

| Location | Path |
|---|---|
| The whole document | `$` |
| Key `price` at the top level | `$.price` |
| Key `id` inside `seller` | `$.seller.id` |
| First element of `items` | `$.items[0]` |
| `price` of that element | `$.items[0].price` |
| A key that isn't a simple name, e.g. `first name` | `$["first name"]` |

A key uses dot notation only if it looks like an identifier: a letter or `_`, followed by letters, digits or `_`. Anything else uses bracket notation with the key JSON-quoted, so keys containing dots, spaces or quotes stay unambiguous. `$["a.b"]` is one key; `$.a.b` is two.

---

## 5. Severity rules

These rules are the policy of the tool. They live in one module (`rules.py`), separate from the code that detects changes (`diff.py`).

| # | Change | Kind | Severity | Why |
|---|---|---|---|---|
| R1 | Object key removed | `field_removed` | **breaking** | Clients reading it get a missing key or crash. |
| R2 | Object key added | `field_added` | **safe** | Well-behaved clients ignore fields they don't know. |
| R3 | Type changed (e.g. integer → string, object → array) | `type_changed` | **breaking** | Client code written for the old type fails: `price * qty` with a string. |
| R4 | Any type → `null` | `type_changed` | **breaking** | Clients that don't null-check crash: `name.upper()` on `None`. |
| R5 | `null` → any type | `type_changed` | **safe** | Clients already had to handle the old value, null. See note below. |
| R6 | integer → float | `type_changed` | **breaking** | Clients with an `int` field can't parse `250.5`. |
| R7 | float → integer | `type_changed` | **safe** | Every integer is a valid float; float clients parse it fine. |
| R8 | Same type, different value | `value_changed` | **info** | Data changed; structure didn't. |
| R9 | Array element added or removed | `item_added` / `item_removed` | **info** | List length is data (more products, fewer orders), not structure. |

**Note on R5:** we compare *samples*, not specifications. A field that is `null` in one response (`"discount": null`) and `10` in the next usually means "this one has a discount now," not "the API changed." Calling that breaking would make the tool noisy, and noisy tools get ignored.

**Rule precedence:** R4–R7 are special cases of R3. They are checked first; R3 is the fallback for any other type change.

---

## 6. Algorithm

`compare(old, new)` walks both documents together, starting at path `$`:

```
compare_at(path, old, new):
    if json_type(old) != json_type(new):
        report TYPE_CHANGED at path          # don't look inside: structures differ
    else if both are objects:
        for each key in old (in old's order):
            if key not in new: report FIELD_REMOVED
            else:              compare_at(path + key, old[key], new[key])
        for each key in new but not in old (in new's order):
            report FIELD_ADDED
    else if both are arrays:
        for each index present in both:  compare_at(path + [i], old[i], new[i])
        for each extra index in new:      report ITEM_ADDED
        for each extra index in old:      report ITEM_REMOVED
    else (both are the same scalar type):
        if old != new: report VALUE_CHANGED
```

This is **recursion**: a function that calls itself on smaller pieces until it reaches plain values. It runs in time proportional to the size of the documents, visiting each value once.

**Order of results:** changes come out in the order the walk finds them, following the old document's key order, then keys that are new. `json.load` keeps key order, so the same input always gives the same output. Changing only the *order* of keys produces no changes at all, because JSON objects are unordered.

---

## 7. Known limitations

**Arrays are compared by position.** If a new item is inserted at the *start* of a list, every element shifts by one, and the engine reports a value change for each element instead of one "item added."

Fixing this properly means matching items by an identifier (like `"id"`) or using a sequence-matching algorithm. Both add real complexity, so they are left for later, if real usage shows the need.

**One sample isn't a contract.** Comparing two responses can only see what those responses contain. A field that happens to be absent in both samples is invisible. Phase 2 (replaying several requests) and Phase 3 (history over time) reduce this.

---

## 8. Command-line interface

```
python -m api_time_machine compare old.json new.json
```

Prints one line per change, then a summary:

```
BREAKING  $.price       type changed: integer → string  (250 → "250")
BREAKING  $.seller.id   field removed
SAFE      $.discount    field added (integer)
INFO      $.stock       value changed: 12 → 9

4 changes: 2 breaking, 1 safe, 1 info
```

**Exit codes**, so scripts and CI pipelines can react without reading the text:

| Code | Meaning |
|---|---|
| `0` | Compared successfully; no breaking changes |
| `1` | Compared successfully; at least one breaking change |
| `2` | Could not compare: file missing, unreadable, or not valid JSON |

**Input validation:** Python's `json` module accepts `NaN` and `Infinity` by default, but they aren't valid JSON. `NaN` is also never equal to itself, which would create fake value changes. The CLI rejects them as invalid input (exit code `2`).

---

## 9. Module layout

```
src/api_time_machine/
├── models.py     JsonValue, JsonType, ChangeKind, Severity, Change: data only, no logic
├── diff.py       json_type(), compare(): detects what changed
├── rules.py      classify(): decides how severe each change is
├── report.py     format_report(): turns changes into text
├── cli.py        argument parsing, reading files, exit codes
└── __main__.py   lets you run `python -m api_time_machine`
```

**Why split detection (`diff.py`) from classification (`rules.py`)?** Detection is objective: a key either exists or it doesn't. Severity is a policy that people can disagree on. Keeping the policy in one small module means it can be read, tested and later made configurable without touching the tree-walking code.

**Why keep `cli.py` separate from the engine?** The engine knows nothing about files or terminals. In Phase 2, the web API will call the very same `compare()` function. Only the input and output layer changes.

---

## 10. Implementation plan

Each step is small, tested and committed separately.

1. **Models and `json_type()`**, with tests for every JSON type (including the `bool`/`int` gotcha)
2. **Flat objects:** field added, removed, type changed and value changed, plus severity rules R1–R3 and R8
3. **Nested objects and paths:** recursion, dot vs. bracket notation
4. **Arrays:** compare by index, item added and removed (R9)
5. **Null and number rules:** R4–R7, and an empty-input and identical-input check
6. **Report and CLI:** text output, exit codes, input validation, sample JSON files in `examples/`
