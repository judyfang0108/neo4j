# Query Generation Flow

End-to-end walkthrough of how a natural language question becomes a validated JSON query.

## Overview

```
User question
    │
    ▼
┌─────────────────────────┐
│  1. Build the graph      │  (one-time setup)
│     schema.json → Neo4j  │
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  2. Initialize generator │  (once per session)
│     Neo4j → system prompt│
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  3. Send to LLM          │
│     system prompt + question → JSON
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  4. Parse JSON            │
│     raw text → QueryConfig│
└────────────┬────────────┘
             ▼
┌─────────────────────────┐
│  5. Validate              │
│     check fields, joins,  │
│     filters, data sources │
└────────────┬────────────┘
             ▼
        Valid? ─── No ──→ Retry once with error feedback → still fails? → raise error
             │
            Yes
             ▼
        Return QueryConfig
```

---

## Step 1: Build the graph (one-time setup)

**File:** [build_graph.py](build_graph.py)

Reads `schema.json` and writes nodes + relationships into Neo4j.

### What gets created

**Nodes:**
- **Module** — one per module (e.g. `EmployeeInformation`, `TimeAndAttendance`). Key properties: `moduleId`, `selectType` (`MultiSelect` or `SingleSelect`).
- **Field** — one per field per data source (e.g. `EmployeeCode` in `EmployeeInformation` DS). Key properties: `fieldId`, `dataSourceId`, `type`, `enumOptions`, `filterable`, etc.

**Relationships:**
- `(Module)-[:HAS_FIELD]->(Field)` — every field belongs to a module
- `(Field)-[:JOINS_WITH]-(Field)` — join-key pairs between data sources, built from `joinColumnMappings`. Works both within and across modules.
- `(Field)-[:SAME_AS]-(Field)` — fields sharing the same `onlineSource` across modules (same real-world entity).

### How to run

```bash
docker compose up --build      # starts Neo4j + runs build_graph.py
```

Or locally:
```bash
docker compose up -d neo4j
python build_graph.py
```

---

## Step 2: Initialize the generator (once per session)

**File:** [query_generator.py](query_generator.py) — `QueryGenerator.__init__`

On startup, the generator:

1. **Connects to Neo4j** and loads the full schema from the graph in a single session:
   - All Module → Field data (field names, types, enums, freeform flags, required filters)
   - All `JOINS_WITH` relationships (valid join pairs)
   - All `SAME_AS` relationships (cross-module equivalent fields)

2. **Builds helper lookups** used during validation:
   - `_field_lookup` — set of all valid `(dataSource, fieldId)` pairs
   - `_field_meta` — metadata per field (type, enum options, freeform flag)
   - `_join_pairs` — set of valid `(dsA, fieldA, dsB, fieldB)` join tuples
   - `_ds_to_module` — maps each data source to its parent module
   - `_module_select_type` — maps each module to its `selectType`
   - `_required_filters` — data sources that require certain filters

3. **Builds the system prompt** from the graph data. The prompt includes:
   - Full schema listing (modules → data sources → fields with types/enums)
   - **MultiSelect modules** — which modules allow implicit data source combining
   - **Joinable fields** — explicit join pairs (within and cross-module)
   - **Non-joinable data sources** — data sources that can't be joined at all
   - **Required filters** — data sources that need mandatory filters
   - **SAME_AS equivalences** — cross-module field equivalences
   - JSON format specification, rules, and examples

---

## Step 3: Send to LLM

**File:** [query_generator.py](query_generator.py) — `generate_query`

The generator sends two messages to the LLM:
- **System message:** the full system prompt (schema + rules + examples) built in step 2
- **User message:** `"Question: {user_question}\n\nRespond with JSON only."`

Configuration: model, base URL, and API key come from environment variables / `.env`.

---

## Step 4: Parse the response

**File:** [query_generator.py](query_generator.py) — `_extract_json`

The raw LLM response may contain markdown fences or think tags. The parser:
1. Strips `<think>...</think>` blocks (for models like Qwen3)
2. Strips markdown ` ```json ... ``` ` fences
3. Parses the remaining text as JSON
4. Constructs a `QueryConfig` Pydantic model ([dataclass.py](dataclass.py))

`QueryConfig` includes: `fields`, `calculated_fields`, `filters`, `joins`, `aggregation`, `subqueries`, `order_by`, `limit`, `offset`, `distinct`.

Pydantic validates structural correctness (required fields, enum values, operator/value consistency) at parse time.

---

## Step 5: Validate against the graph

**File:** [query_generator.py](query_generator.py) — `validate_query`

This is where the graph knowledge is used to catch errors the LLM might make. Validations run in order:

### 5a. Field existence
Every `field_name` + `dataSource` pair in `fields` must exist in `_field_lookup`. Date functions (`YEAR`/`MONTH`/`DAY`) must only be applied to date-type fields.

### 5b. Calculated fields
Every `dataSource` referenced in a calculated field must exist.

### 5c. Filter validation
For each filter condition:
- The field must exist in the specified data source
- Date functions must only apply to date fields
- **Non-freeform fields**: no `LIKE`/`NOT LIKE` allowed. If the field has `enumOptions`, values must be from the allowed set.
- **Freeform fields**: warns if using exact `=` instead of `LIKE` for keyword matching.
- Nested filter groups (`AND`/`OR`) are validated recursively.

### 5d. Join validation
For each explicit join entry:
- Both left and right fields must exist
- The field pair must have a `JOINS_WITH` edge in the graph, **unless** both data sources are in the same `MultiSelect` module (implicit join allowed)

### 5e. Aggregation validation
- Each aggregation function's field must exist (or be `*` for `COUNT(*)`)
- `SUM`/`AVG` must target numeric fields
- Date functions must target date fields
- `group_by` fields must exist and not be ambiguous across multiple data sources
- `having` aliases must match a defined aggregation function alias

### 5f. Subquery validation
Each subquery's inner `QueryConfig` is validated recursively through the same checks.

### 5g. Required filters
If a data source has mandatory filters (e.g. a date range filter for large tables), the query must include a filter on that field.

### 5h. Data source combinability (transitive reachability)

If the query uses fields from multiple data sources, they must all be **transitively connected**. Two data sources are directly connected if they:
- Are in the **same MultiSelect module** (implicit join), OR
- Have an **explicit `joins` entry** between them

Transitive reachability means: if A connects to B and B connects to C, then A, B, C are all combinable — no direct link is needed for every pair. The validator uses a union-find algorithm to build connected groups and rejects the query only if multiple disconnected groups remain.

#### Example

Given 3 modules:
```
Module A (MultiSelect): DS_1, DS_2
Module B (SingleSelect): DS_3
Module C (MultiSelect): DS_4, DS_5
```

A query uses `DS_1`, `DS_2`, `DS_3`, `DS_4` with explicit joins: `DS_1 ↔ DS_3` and `DS_1 ↔ DS_4`.

**Step 1 — MultiSelect connections:**
- `DS_1` and `DS_2` are in Module A (MultiSelect) → connected
- Group so far: `{DS_1, DS_2}`, `{DS_3}`, `{DS_4}`

**Step 2 — Explicit join connections:**
- `DS_1 ↔ DS_3` → group becomes `{DS_1, DS_2, DS_3}`
- `DS_1 ↔ DS_4` → group becomes `{DS_1, DS_2, DS_3, DS_4}`

**Step 3 — Check:** 1 connected group → **pass**

Note that `DS_2 ↔ DS_3` has no direct link, but passes because `DS_2` connects to `DS_1` (MultiSelect) and `DS_1` joins to `DS_3` (explicit join). Without transitive reachability, this would incorrectly fail.

#### What the error looks like

If the query used `DS_1`, `DS_3`, `DS_4` but only had a join for `DS_1 ↔ DS_3` (missing `DS_4`):

```
Data sources are not all connected. Disconnected groups: [DS_1, DS_3] / [DS_4].
Add explicit joins between groups or use data sources from the same MultiSelect module.
```

### On validation failure: self-correction

If validation finds errors on the first attempt, the generator **retries once**:
1. Appends the LLM's response as an assistant message
2. Appends the validation errors as a user message: `"Validation errors: ... Fix these errors using ONLY fields from the schema."`
3. Sends the full conversation back to the LLM for self-correction

If the second attempt also fails, the error is raised to the caller.

---

## Example trace

**User asks:** *"Show me detailed salary breakdown for all employees"*

1. **System prompt** includes `EmployeeInformation` module marked as `MultiSelect` with data sources `EmployeeInformation` and `PayInformation`.

2. **LLM generates:**
   ```json
   {
     "fields": [
       {"field_name": "EmployeeName", "dataSource": "EmployeeInformation"},
       {"field_name": "AnnualSalary", "dataSource": "PayInformation"},
       {"field_name": "PayFrequency", "dataSource": "PayInformation"}
     ]
   }
   ```

3. **Validation:**
   - Fields exist? `EmployeeName` in `EmployeeInformation` ✓, `AnnualSalary` in `PayInformation` ✓, `PayFrequency` in `PayInformation` ✓
   - No filters, joins, or aggregation to check
   - Data source combinability: `EmployeeInformation` + `PayInformation` are in the same `MultiSelect` module ✓
   - Result: **valid**

---

**User asks:** *"Show employee names with their total earning amounts"*

1. **LLM generates:**
   ```json
   {
     "fields": [
       {"field_name": "EmployeeName", "dataSource": "EmployeeInformation"},
       {"field_name": "EarnAmount", "dataSource": "TotalEarnings"}
     ],
     "joins": [{
       "left_data_source": "EmployeeInformation",
       "right_data_source": "TotalEarnings",
       "left_field": "EmployeeCode",
       "right_field": "EmployeeCode",
       "join_type": "INNER"
     }]
   }
   ```

2. **Validation:**
   - Fields exist? ✓
   - Join: `EmployeeInformation.EmployeeCode ↔ TotalEarnings.EmployeeCode` in `_join_pairs`? ✓ (cross-module JOINS_WITH edge exists)
   - Data source combinability: different modules, but explicit join present ✓
   - Result: **valid**

---

**LLM makes a mistake** — forgets the join for a cross-module query:
```json
{
  "fields": [
    {"field_name": "EmployeeName", "dataSource": "EmployeeInformation"},
    {"field_name": "EarnAmount", "dataSource": "TotalEarnings"}
  ]
}
```

Validation catches it:
> `Data sources 'EmployeeInformation' and 'TotalEarnings' are used together but have no explicit join and are not in the same MultiSelect module`

The error is fed back to the LLM, which self-corrects by adding the join.
