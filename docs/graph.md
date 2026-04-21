# Graph Design

## Nodes

**`Module`**
- `moduleId` — unique identifier (e.g. `EmployeeInformation`, `TimeAndAttendance`)
- `description` — human-readable module name
- `selectType` — `MultiSelect` or `SingleSelect`
- `embedding` — vector embedding of `description`
- `descriptionHash` — for detecting description changes and triggering re-embedding

**`Field`**
- `fieldId` — field identifier (e.g. `EmployeeCode`, `AnnualSalary`)
- `description` — human-readable field description (will be richer/more detailed soon)
- `type` — `string`, `decimal`, `date`, or `enum`
- `enumOptions` — hard schema constraint: complete list of allowed values if `type=enum`, else null
- `is_freeform` — bool; `true` = unbounded value space (names, emails), `false` = constrained value set (state codes, status codes)
- `example_data` — array of sample values; for `is_freeform=true` fields these are format hints, for `is_freeform=false` fields these are representative values
- `readOnly` — bool or null
- `dataSourceId` — which data source this field belongs to
- `dataSourceDescription` — human-readable data source name
- `filterable` — bool, true if any filter types are defined
- `filterType` — e.g. `MultiSelect`, `DateRange`
- `filterLabel` — human-readable filter label (e.g. "Select Employee Codes")
- `onlineSource` — reference entity for filter values (e.g. `BasicEmployee`, `BasicDepartment`), null if none
- `required` — bool
- `embedding` — vector embedding of `description` (and optionally low-cardinality `example_data`)
<!-- - `descriptionHash` — for change detection -->

## Relationships

**`(Module)-[:HAS_FIELD]->(Field)`**
- Connects each module to every field belonging to any of its data sources
- Primary structural edge

**`(Field)-[:JOINS_WITH]-(Field)`** *(undirected, within or across modules)*
- Links join-key fields between different data sources, built from `joinColumnMappings` in the source JSON
- Works **within** a module (e.g. two data sources sharing `EmployeeCode`) and **across** modules (e.g. `EmployeeInformation.EmployeeCode` ↔ `TotalEarnings.EmployeeCode`)
- Tells the agent: "these data sources can be combined in one query via these fields"
- **Note:** In `MultiSelect` modules, all data sources are implicitly combinable — no explicit join or `JOINS_WITH` edge is needed. The agent should use `selectType` on the Module node to determine this.

**`(Field)-[:SAME_AS]-(Field)`** *(undirected, across modules)*
- Links fields that share the same `onlineSource`
- Tells the agent: "these refer to the same real-world entity, even though they live in different query contexts — coordinate via multiple queries, don't try to join in one"

## Join rules (with schema.json example)

There are two ways data sources can be combined in a single query:

### 1. Implicit join — MultiSelect modules

If a module has `selectType: MultiSelect`, **all** data sources inside it can be combined freely — no explicit join or join column is needed.

**Example:** The `EmployeeInformation` module is `MultiSelect` and contains two data sources:
- `EmployeeInformation` (Employee Information)
- `PayInformation` (Pay Information)

`PayInformation` has no `EmployeeCode` field and no `joinColumnMappings`, but it can still be combined with `EmployeeInformation` because they share the same MultiSelect module. A query can select `EmployeeName` from `EmployeeInformation` and `AnnualSalary` from `PayInformation` with no join clause.

### 2. Explicit join — cross-module via `joinColumnMappings`

Data sources in **different** modules can be joined when their `joinColumnMappings` reference a common column that exists in both.

**Example:** `EmployeeInformation` data source (in `EmployeeInformation` module) has:
```json
"autoJoinColumns": ["EmployeeCode"],
"joinColumnMappings": { "EmployeeCode": ["EmployeeCode"] }
```
`TotalEarnings` data source (in `TimeAndAttendance` module) also has `EmployeeCode` as a field. This produces a `JOINS_WITH` edge between them, so a query can join the two via `EmployeeCode`.

### Full edge map for the current schema

| Module A | Data Source A | Module B | Data Source B | Join type | Via |
|---|---|---|---|---|---|
| `EmployeeInformation` | `EmployeeInformation` | `EmployeeInformation` | `PayInformation` | Implicit (MultiSelect) | Same module |
| `EmployeeInformation` | `EmployeeInformation` | `TimeAndAttendance` | `TotalEarnings` | Explicit (cross-module) | `EmployeeCode` |
| `EmployeeInformation` | `EmployeeInformation` | `TimeAndAttendance` | `PunchPairs` | Explicit (cross-module) | `EmployeeCode` |
| `TimeAndAttendance` | `TotalEarnings` | `TimeAndAttendance` | `PunchPairs` | Explicit (within module) | `EmployeeCode` |

`PayInformation` (in `EmployeeInformation` module) has no `EmployeeCode` field, so it has no `JOINS_WITH` edges — it is only reachable through the MultiSelect implicit join with other data sources in its module.

## Stable identity

- `Module` keyed on `moduleId`
- `Field` keyed on `(moduleId, dataSourceId, fieldId)`
- All ingest operations use `MERGE` on these keys so that description updates and re-embeddings modify existing nodes rather than creating duplicates

## How the agent uses this

1. **Embed** the user's question.
2. *(Optional)* Vector-search `Module.embedding` to narrow scope.
3. Vector-search `Field.embedding` to find candidate fields by semantic similarity.
4. For each candidate, walk to its `Module` via `HAS_FIELD` to read `selectType`. If `MultiSelect`, all data sources in that module can be freely combined without explicit joins.
5. Walk `JOINS_WITH` edges (within or across modules) to expand the field set into a single joinable query. Cross-module joins require explicit join fields.
6. Walk `SAME_AS` edges across modules to detect when a question requires multiple coordinated queries stitched together.
7. Use Field properties (`type`, `enumOptions`, `is_freeform`, `example_data`, `filterType`, `filterLabel`) to construct valid filter clauses — including mapping user phrases like "California" to stored values like "CA" via `example_data`.

## Deferred (clear triggers for adding later)

- **`SIMILAR_TO` edges between Fields** — add when you want hard, traversable soft-match links derived from embedding similarity. For now, do ad-hoc vector search on demand.
- **Enum nodes** — add when enum values need their own metadata, are reused across many fields, or need to be embedded individually.
- **ExampleValue nodes** — add when the agent demonstrably fails to map user phrases to stored values via Field-level embeddings alone. Most useful for `is_freeform=false` fields with shared values across multiple fields.