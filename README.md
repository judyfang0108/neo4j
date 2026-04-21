# neo4j-graph

Builds a Neo4j graph from `schema.json` and uses it to generate validated JSON queries from natural language.

## What's in this repo

| File | Purpose |
|---|---|
| [build_graph.py](build_graph.py) | Reads `schema.json` and writes nodes + relationships into Neo4j |
| [query_generator.py](query_generator.py) | LLM-powered query generator — natural language → validated `QueryConfig` JSON |
| [prompt.py](prompt.py) | System prompt template with schema, rules, and examples |
| [dataclass.py](dataclass.py) | Pydantic models for `QueryConfig` and all its components |
| [schema.json](schema.json) | Source schema — drop your real schema here |
| [Dockerfile](Dockerfile) | Slim Python image that runs `build_graph.py` |
| [docker-compose.yml](docker-compose.yml) | Neo4j 5 service + the `build_graph` one-shot job |
| [requirements.txt](requirements.txt) | Python dependencies |

## Docs

| Doc | What's in it |
|---|---|
| [docs/graph.md](docs/graph.md) | Graph design — nodes, properties, relationships, join rules with examples |
| [docs/query-flow.md](docs/query-flow.md) | End-to-end walkthrough of how a question becomes a validated query |
| [docs/query-config-reference.md](docs/query-config-reference.md) | Complete `QueryConfig` reference — every field, operator, and SQL equivalent |
| [docs/analytics-design.md](docs/analytics-design.md) | Design doc for advanced analytics (ratios, YoY, percentages) |
| [docs/feedback-responses.md](docs/feedback-responses.md) | Responses to QueryConfig design feedback |

## Quick start

```bash
# 1. Start Neo4j and build the graph
docker compose up --build

# 2. Open the Neo4j Browser
open http://localhost:7474
```

Browser login: `bolt://localhost:7687` / `neo4j` / `testpassword`

The `build_graph` container exits after it finishes; Neo4j stays running.

### Run the query generator

```bash
pip install neo4j openai httpx python-dotenv pydantic

# Create a .env file with your LLM credentials
cat > .env << 'EOF'
API_KEY=your-api-key
BASE_URL=your-llm-endpoint
MODEL=qwen3-coder-next
NEO4J_PASSWORD=testpassword
EOF

python query_generator.py
```

Type natural language questions, get validated JSON queries back.

## Common commands

```bash
# Start Neo4j only, in the background
docker compose up -d neo4j

# Re-run graph build (after editing schema.json — no rebuild needed, it's bind-mounted)
docker compose run --rm build_graph

# Re-run graph build (after editing build_graph.py — rebuild required)
docker compose run --rm --build build_graph

# Stop everything
docker compose down

# Stop everything AND wipe the Neo4j data volume
docker compose down -v
```

## Viewing the graph

In the Browser at http://localhost:7474:

```cypher
-- Everything
MATCH (n) RETURN n

-- Modules and their fields
MATCH (m:Module)-[:HAS_FIELD]->(f:Field) RETURN m, f LIMIT 200

-- JOINS_WITH edges (within and cross-module)
MATCH (a:Field)-[r:JOINS_WITH]-(b:Field) RETURN a, r, b

-- Cross-module SAME_AS links
MATCH (a:Field)-[r:SAME_AS]-(b:Field) RETURN a, r, b

-- Sanity-check counts
MATCH (m:Module) RETURN count(m) AS modules;
MATCH (f:Field)  RETURN count(f) AS fields;
MATCH ()-[r:HAS_FIELD]->()  RETURN count(r) AS has_field;
MATCH ()-[r:JOINS_WITH]-()  RETURN count(r)/2 AS joins_with;
MATCH ()-[r:SAME_AS]-()     RETURN count(r)/2 AS same_as;
```

## Configuration

Connection settings are read from environment variables ([build_graph.py:5-8](build_graph.py#L5-L8)):

| Variable | Default | Notes |
|---|---|---|
| `NEO4J_URI` | `bolt://localhost:7687` | Compose overrides to `bolt://neo4j:7687` |
| `NEO4J_USER` | `neo4j` | |
| `NEO4J_PASSWORD` | `testpassword` | Must match `NEO4J_AUTH` in compose |
| `SCHEMA_FILE` | `schema.json` | Path inside the container |

## Running locally without Docker

```bash
pip install -r requirements.txt
docker compose up -d neo4j        # still need a Neo4j instance
NEO4J_PASSWORD=testpassword python build_graph.py
```

## Making changes

The build is idempotent: every run wipes existing nodes and rebuilds from `schema.json`. Workflow: **edit → re-run → verify in the Browser**.

For details on adding properties, relationships, or node labels, see [docs/graph.md](docs/graph.md).
