import json
import os
from neo4j import GraphDatabase

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "testpassword")
SCHEMA_FILE = os.environ.get("SCHEMA_FILE", "schema.json")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")


def load_schema(path):
    with open(path, "r") as f:
        return json.load(f)


def flatten_fields(schema):
    """Yield one dict per Field node, carrying everything we need.

    Neo4j drops properties whose value is null, so every property listed in
    docs/graph.md is given a type-appropriate default ("" / false / []) to keep it
    visible on every node. Real values overwrite the defaults when present.
    """
    for module_id, module in schema.items():
        for ds_id, ds in module["dataSources"].items():
            for field_id, field in ds["dataSourceFields"].items():
                filter_types = field.get("filterTypes") or {}
                filterable = len(filter_types) > 0
                # Take the first filter definition if any (schema rarely has more than one)
                first_filter = next(iter(filter_types.values()), {}) if filterable else {}
                yield {
                    "moduleId": module_id,
                    "dataSourceId": ds_id,
                    "dataSourceDescription": ds.get("dataSourceDescription") or "",
                    "fieldId": field_id,
                    "description": field.get("description") or "",
                    "type": field.get("type") or "",
                    "enumOptions": field.get("enumOptions") or [],
                    "readOnly": bool(field.get("readOnly")),
                    "is_freeform": False,   # to be populated later
                    "example_data": [],     # to be populated later
                    "filterable": filterable,
                    "filterType": first_filter.get("filterType") or "",
                    "filterLabel": first_filter.get("filterLabel") or "",
                    "onlineSource": first_filter.get("onlineSource") or "",
                    "required": bool(first_filter.get("required")),
                    "embedding": [],        # to be populated later
                }


def create_constraints(tx):
    # Constraints for stable identity — must run in their own transaction,
    # Neo4j forbids mixing schema changes with data writes.
    tx.run("CREATE CONSTRAINT module_id IF NOT EXISTS FOR (m:Module) REQUIRE m.moduleId IS UNIQUE")
    tx.run(
        "CREATE CONSTRAINT field_key IF NOT EXISTS FOR (f:Field) "
        "REQUIRE (f.moduleId, f.dataSourceId, f.fieldId) IS UNIQUE"
    )


def build_graph(tx, schema):
    # Wipe any prior version so re-runs are clean
    tx.run("MATCH (n) WHERE n:Module OR n:Field DETACH DELETE n")

    # Create Module nodes — every property in docs/graph.md gets a default so it
    # is visible on the node even before the embedding pipeline populates it.
    for module_id, module in schema.items():
        tx.run(
            """
            MERGE (m:Module {moduleId: $moduleId})
            SET m.description = $description,
                m.selectType = $selectType,
                m.embedding = $embedding,
                m.descriptionHash = $descriptionHash
            """,
            moduleId=module_id,
            description=module.get("moduleDescription") or "",
            selectType=module.get("selectType") or "",
            embedding=[],            # to be populated later
            descriptionHash="",      # to be populated later
        )

    # Create Field nodes + HAS_FIELD edges
    for f in flatten_fields(schema):
        tx.run(
            """
            MERGE (field:Field {moduleId: $moduleId, dataSourceId: $dataSourceId, fieldId: $fieldId})
            SET field.description = $description,
                field.type = $type,
                field.enumOptions = $enumOptions,
                field.readOnly = $readOnly,
                field.dataSourceDescription = $dataSourceDescription,
                field.is_freeform = $is_freeform,
                field.example_data = $example_data,
                field.filterable = $filterable,
                field.filterType = $filterType,
                field.filterLabel = $filterLabel,
                field.onlineSource = $onlineSource,
                field.required = $required,
                field.embedding = $embedding
            WITH field
            MATCH (m:Module {moduleId: $moduleId})
            MERGE (m)-[:HAS_FIELD]->(field)
            """,
            **f,
        )

    # JOINS_WITH edges — between fields in different data sources (within AND across modules)
    # Build a reverse index: field_id → [(module_id, ds_id)] for fast lookup
    field_ds_index = {}  # field_id → [(module_id, ds_id), ...]
    for module_id, module in schema.items():
        for ds_id, ds in module["dataSources"].items():
            for fid in (ds.get("dataSourceFields") or {}):
                field_ds_index.setdefault(fid, []).append((module_id, ds_id))

    # Collect all join edges in Python, then batch into a single UNWIND query
    join_edges = []
    for module_id, module in schema.items():
        for ds_id, ds in module["dataSources"].items():
            for left_field, right_fields in (ds.get("joinColumnMappings") or {}).items():
                for right_field in right_fields:
                    for other_mod_id, other_ds_id in field_ds_index.get(right_field, []):
                        if other_ds_id != ds_id:
                            join_edges.append({
                                "modA": module_id, "dsA": ds_id, "fieldA": left_field,
                                "modB": other_mod_id, "dsB": other_ds_id, "fieldB": right_field,
                            })

    if join_edges:
        tx.run(
            """
            UNWIND $edges AS e
            MATCH (a:Field {moduleId: e.modA, dataSourceId: e.dsA, fieldId: e.fieldA})
            MATCH (b:Field {moduleId: e.modB, dataSourceId: e.dsB, fieldId: e.fieldB})
            MERGE (a)-[:JOINS_WITH]-(b)
            """,
            edges=join_edges,
        )

    # SAME_AS edges — across modules, fields sharing the same onlineSource
    tx.run(
        """
        MATCH (a:Field), (b:Field)
        WHERE a.onlineSource <> ''
          AND a.onlineSource = b.onlineSource
          AND a.moduleId <> b.moduleId
          AND id(a) < id(b)
        MERGE (a)-[:SAME_AS]-(b)
        """
    )


def main():
    schema = load_schema(SCHEMA_FILE)
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session(database=NEO4J_DATABASE) as session:
        session.execute_write(create_constraints)
        session.execute_write(build_graph, schema)
    driver.close()
    print("Graph built. Open Neo4j Browser and run:  MATCH (n) RETURN n")


if __name__ == "__main__":
    main()