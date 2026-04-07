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

**`(Field)-[:JOINS_WITH]-(Field)`** *(undirected, scoped within a module)*
- Links join-key fields between different data sources inside the same module
- Built from `joinColumnMappings` in the source JSON
- Tells the agent: "these data sources can be combined in one query via these fields"
- Only meaningful in `MultiSelect` modules

**`(Field)-[:SAME_AS]-(Field)`** *(undirected, across modules)*
- Links fields that share the same `onlineSource`
- Tells the agent: "these refer to the same real-world entity, even though they live in different query contexts — coordinate via multiple queries, don't try to join in one"

## Stable identity

- `Module` keyed on `moduleId`
- `Field` keyed on `(moduleId, dataSourceId, fieldId)`
- All ingest operations use `MERGE` on these keys so that description updates and re-embeddings modify existing nodes rather than creating duplicates

## How the agent uses this

1. **Embed** the user's question.
2. *(Optional)* Vector-search `Module.embedding` to narrow scope.
3. Vector-search `Field.embedding` to find candidate fields by semantic similarity.
4. For each candidate, walk to its `Module` via `HAS_FIELD` to read `selectType` and plan whether multiple data sources can be combined.
5. Walk `JOINS_WITH` edges within a module to expand the field set into a single joinable query.
6. Walk `SAME_AS` edges across modules to detect when a question requires multiple coordinated queries stitched together.
7. Use Field properties (`type`, `enumOptions`, `is_freeform`, `example_data`, `filterType`, `filterLabel`) to construct valid filter clauses — including mapping user phrases like "California" to stored values like "CA" via `example_data`.

## Deferred (clear triggers for adding later)

- **`SIMILAR_TO` edges between Fields** — add when you want hard, traversable soft-match links derived from embedding similarity. For now, do ad-hoc vector search on demand.
- **Enum nodes** — add when enum values need their own metadata, are reused across many fields, or need to be embedded individually.
- **ExampleValue nodes** — add when the agent demonstrably fails to map user phrases to stored values via Field-level embeddings alone. Most useful for `is_freeform=false` fields with shared values across multiple fields.