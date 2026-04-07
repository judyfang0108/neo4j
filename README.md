# neo4j-graph

Builds a Neo4j graph of modules, data sources, and fields from a `schema.json` file. The graph design lives in [graph.MD](graph.MD); this README is for running and extending it.

## What's in this repo

| File | Purpose |
|---|---|
| [build_graph.py](build_graph.py) | Reads `schema.json` and writes nodes + relationships into Neo4j |
| [schema.json](schema.json) | Source schema — drop your real schema here |
| [graph.MD](graph.MD) | Graph design: nodes, properties, relationships, agent usage |
| [Dockerfile](Dockerfile) | Slim Python image that runs `build_graph.py` |
| [docker-compose.yml](docker-compose.yml) | Neo4j 5 service + the `build_graph` one-shot job |
| [requirements.txt](requirements.txt) | Pins the `neo4j` Python driver |

## Prerequisites

- Docker Desktop (or any Docker engine with Compose v2)
- A populated `schema.json` in the repo root

## Quick start

```bash
# 1. Start Neo4j and run the graph build (first time, also builds the image)
docker compose up --build

# 2. Open the Neo4j Browser
open http://localhost:7474
```

Browser login (first time only):
- **Connect URL:** `bolt://localhost:7687`
- **Username:** `neo4j`
- **Password:** `testpassword`

The `build_graph` container exits after it finishes; Neo4j stays running.

## Common commands

```bash
# Start Neo4j only, in the background
docker compose up -d neo4j

# Re-run the script (after editing schema.json — no rebuild needed, it's bind-mounted)
docker compose run --rm build_graph

# Re-run the script (after editing build_graph.py — rebuild required)
docker compose run --rm --build build_graph

# Stop everything
docker compose down

# Stop everything AND wipe the Neo4j data volume
docker compose down -v

# Tail Neo4j logs
docker compose logs -f neo4j
```

## Viewing the graph

In the Browser at http://localhost:7474:

```cypher
// Everything (fine for small graphs)
MATCH (n) RETURN n

// Modules and their fields
MATCH (m:Module)-[:HAS_FIELD]->(f:Field) RETURN m, f LIMIT 200

// Cross-module SAME_AS links
MATCH (a:Field)-[r:SAME_AS]-(b:Field) RETURN a, r, b

// Joins within a single module
MATCH (a:Field)-[r:JOINS_WITH]-(b:Field)
WHERE a.moduleId = 'YOUR_MODULE_ID'
RETURN a, r, b

// Sanity-check counts
MATCH (m:Module) RETURN count(m) AS modules;
MATCH (f:Field)  RETURN count(f) AS fields;
MATCH ()-[r:HAS_FIELD]->()  RETURN count(r) AS has_field;
MATCH ()-[r:JOINS_WITH]-()  RETURN count(r)/2 AS joins_with;
MATCH ()-[r:SAME_AS]-()     RETURN count(r)/2 AS same_as;

// Inspect the property set on a field / module
MATCH (f:Field)  RETURN keys(f) AS props LIMIT 1
MATCH (m:Module) RETURN keys(m) AS props LIMIT 1
```

## Making future graph changes

The build is idempotent: every run wipes existing `:Module` and `:Field` nodes ([build_graph.py:56](build_graph.py#L56)) and rebuilds from `schema.json`. So the workflow is **edit → re-run → verify in the Browser** — never manually mutate the graph.

### Workflow

1. **Update [graph.MD](graph.MD) first.** Treat it as the design spec. If you're adding a property, relationship, or node label, write it down there before touching code. Keeps design and implementation aligned.
2. **Edit [build_graph.py](build_graph.py)** to match.
3. **Re-run with a rebuild** (the script is baked into the image):
   ```bash
   docker compose run --rm --build build_graph
   ```
4. **Verify in the Browser** with `keys(n)` and a few `MATCH` queries.

If you only changed `schema.json` (not `build_graph.py`), skip the rebuild — it's bind-mounted from the host:
```bash
docker compose run --rm build_graph
```

### Adding a new property to an existing node

1. Add it to the relevant section in [graph.MD](graph.MD) with its type and meaning.
2. In [build_graph.py](build_graph.py):
   - For **Field properties**: add it to the dict yielded by `flatten_fields` ([build_graph.py:25-42](build_graph.py#L25-L42)) with a type-appropriate default (see "Gotchas" below), then add it to the `SET` clause in the field-creation query ([build_graph.py:81-94](build_graph.py#L81-L94)).
   - For **Module properties**: add it to the module-creation `SET` clause and `tx.run` parameters ([build_graph.py:62-75](build_graph.py#L62-L75)).
3. Re-run with `--build`.

### Adding a new relationship type

1. Document it in [graph.MD](graph.MD) under "Relationships" — direction, scope, what it means semantically.
2. In `build_graph` ([build_graph.py:54](build_graph.py#L54)), add a new block that emits the edges. Use `MERGE` (not `CREATE`) so re-runs stay idempotent. Pattern:
   ```python
   tx.run("""
       MATCH (a:Field {...})
       MATCH (b:Field {...})
       MERGE (a)-[:NEW_REL_TYPE]->(b)
   """, ...)
   ```
3. If the edge is computed from a Cypher pattern over already-created nodes (like `SAME_AS` at [build_graph.py:121-130](build_graph.py#L121-L130)), put it **after** all node-creation blocks so the matched nodes exist.
4. Re-run with `--build`.

### Adding a new node label

1. Add a section to [graph.MD](graph.MD) listing its key, properties, and how it's connected.
2. Add a uniqueness constraint in `create_constraints` ([build_graph.py:44-51](build_graph.py#L44-L51)).
3. Add a creation block in `build_graph`. Use `MERGE` on the key.
4. Add the wipe pattern in [build_graph.py:56](build_graph.py#L56) so re-runs delete the new label too:
   ```cypher
   MATCH (n) WHERE n:Module OR n:Field OR n:NewLabel DETACH DELETE n
   ```
5. Re-run with `--build`.

### Gotchas (we hit all of these)

- **Neo4j drops `null` properties.** `SET x = null` *removes* the property — it doesn't store a null. To make a property show up on every node, always write a non-null default:
  - bool → `False`
  - string → `""`
  - list → `[]`
  See [build_graph.py:16-43](build_graph.py#L16-L43) for the pattern.
- **Schema and data writes can't share a transaction.** `CREATE CONSTRAINT` cannot run in the same transaction as `MATCH ... DELETE` or `MERGE`. That's why constraints live in their own function ([build_graph.py:44-51](build_graph.py#L44-L51)) called as a separate `execute_write` ([build_graph.py:140](build_graph.py#L140)).
- **Default password.** Neo4j 5 rejects the literal default `neo4j` as a password. We use `testpassword` in [docker-compose.yml:11](docker-compose.yml#L11) and the Python default at [build_graph.py:7](build_graph.py#L7) — change them together if you want something else.
- **Empty `schema.json` will crash the script** with `JSONDecodeError: Expecting value`. Make sure your schema is actually populated before running.

### Embeddings (deferred)

[graph.MD](graph.MD) lists `embedding` on both Module and Field, and `descriptionHash` on Module. Right now `build_graph.py` writes them as empty placeholders (`[]` / `""`) so the property exists. The actual embedding pipeline isn't built yet — when you add it:

1. Run it as a **separate pass** after `build_graph.py`. Keep structural ingest and embedding ingest decoupled — they have very different failure modes (network, API quota, model availability).
2. For each Module/Field, compute `sha256(description)`. If it matches the stored `descriptionHash`, skip re-embedding. Otherwise embed and update both `embedding` and `descriptionHash`.
3. After the first embedding run, create vector indexes once:
   ```cypher
   CREATE VECTOR INDEX field_embedding IF NOT EXISTS
   FOR (f:Field) ON (f.embedding)
   OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}};

   CREATE VECTOR INDEX module_embedding IF NOT EXISTS
   FOR (m:Module) ON (m.embedding)
   OPTIONS {indexConfig: {`vector.dimensions`: 1536, `vector.similarity_function`: 'cosine'}};
   ```
   Adjust `vector.dimensions` to match your model.

## Configuration

Connection settings are read from environment variables ([build_graph.py:5-8](build_graph.py#L5-L8)):

| Variable | Default | Notes |
|---|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` | Compose overrides to `bolt://neo4j:7687` |
| `NEO4J_USER` | `neo4j` | |
| `NEO4J_PASSWORD` | `testpassword` | Must match `NEO4J_AUTH` in compose |
| `SCHEMA_FILE` | `schema.json` | Path inside the container |

## Running locally without Docker

Also supported — useful for fast iteration:

```bash
pip install -r requirements.txt
docker compose up -d neo4j        # still need a Neo4j instance
NEO4J_PASSWORD=testpassword python build_graph.py
```

The defaults in [build_graph.py:5-8](build_graph.py#L5-L8) point at `localhost:7687`, which is what compose publishes.
