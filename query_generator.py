"""
Query Generator for CRS - Uses LLM to generate JSON queries from natural language
"""

import json
import os
import re
import httpx
from typing import List, Optional, Union
from openai import OpenAI
from neo4j import GraphDatabase
from dotenv import load_dotenv

from dataclass import (
    QueryConfig,
    FilterCondition,
    FilterGroup,
)

from prompt import build_system_prompt

load_dotenv()


class ValidationError(Exception):
    """Raised when query validation fails"""

    pass


class QueryGenerator:
    def __init__(self):
        self.model = self._get_env("MODEL", "qwen3-coder-next")
        self.base_url = self._get_env(
            "BASE_URL", ""
        )
        self.api_key = self._get_env("API_KEY")

        if not self.api_key:
            raise ValueError("API_KEY not found in environment variables")

        http_client = httpx.Client(timeout=60.0)
        try:
            self.client = OpenAI(
                api_key=self.api_key, base_url=self.base_url, http_client=http_client
            )
        except Exception as e:
            print(f"Warning: Could not initialize with custom http client: {e}")
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        # Load schema from Neo4j graph (single session for all queries)
        self.driver = self._connect_neo4j()
        try:
            modules, joins, same_as = self._load_graph_schema()
            self.system_prompt = self._build_system_prompt(modules, joins, same_as)
        except Exception:
            self.driver.close()
            raise

    def _get_env(self, key: str, default=None) -> Optional[str]:
        """Get env var and strip quotes if present"""
        value = os.getenv(key, default)
        if value and isinstance(value, str):
            value = value.strip().strip('"').strip("'")
        return value

    def _connect_neo4j(self) -> GraphDatabase.driver:
        """Connect to Neo4j"""
        uri = self._get_env("NEO4J_URI", "bolt://localhost:7687")
        user = self._get_env("NEO4J_USER", "neo4j")
        password = self._get_env("NEO4J_PASSWORD", "testpassword")
        self.neo4j_database = self._get_env("NEO4J_DATABASE", "neo4j")
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        print(f"✓ Connected to Neo4j at {uri} (database: {self.neo4j_database})")
        return driver

    def _load_graph_schema(self) -> tuple:
        """Load all schema data from Neo4j in a single session.

        Returns (modules_dict, joins_list, same_as_list).
        Also populates self._field_lookup.
        """
        field_lookup = set()
        field_meta = {}
        required_filters = {}  # {dataSource: [(fieldId, filterType), ...]}
        modules = {}
        joins = []
        same_as = []

        with self.driver.session(database=self.neo4j_database) as session:
            # 1. Fields with metadata
            for r in session.run(
                """
                MATCH (m:Module)-[:HAS_FIELD]->(f:Field)
                RETURN m.moduleId AS moduleId, m.description AS moduleDesc,
                       m.selectType AS selectType,
                       f.dataSourceId AS dsId, f.dataSourceDescription AS dsDesc,
                       f.fieldId AS fieldId, f.description AS fieldDesc,
                       f.type AS fieldType, f.enumOptions AS enumOptions,
                       f.is_freeform AS isFreeform, f.example_data AS exampleData,
                       f.required AS required, f.filterType AS filterType
                ORDER BY moduleId, dsId, fieldId
                """
            ):
                mid, dsid = r["moduleId"], r["dsId"]
                fid = r["fieldId"]
                field_lookup.add((dsid, fid))

                is_freeform = bool(r["isFreeform"])
                enums = r["enumOptions"] or []
                example_data = r["exampleData"] or []

                field_type = (r["fieldType"] or "").lower()

                field_meta[(dsid, fid)] = {
                    "is_freeform": is_freeform,
                    "enum_options": enums,
                    "type": field_type,
                }

                if bool(r["required"]):
                    filter_type = r["filterType"] or ""
                    if dsid not in required_filters:
                        required_filters[dsid] = []
                    required_filters[dsid].append((fid, filter_type))

                if mid not in modules:
                    modules[mid] = {"desc": r["moduleDesc"] or "", "selectType": r["selectType"] or "", "dataSources": {}}
                ds_map = modules[mid]["dataSources"]
                if dsid not in ds_map:
                    ds_map[dsid] = {"desc": r["dsDesc"] or "", "fields": []}

                fdesc = r["fieldDesc"] or ""
                ftype = r["fieldType"] or ""

                parts = []
                if fdesc and fdesc != fid:
                    parts.append(fdesc)
                if ftype:
                    parts.append(ftype)
                if enums:
                    parts.append("enum: " + "|".join(enums))
                if is_freeform:
                    parts.append("freeform")
                    if example_data:
                        parts.append("examples: " + ", ".join(str(e) for e in example_data[:3]))
                label = f"{fid} ({', '.join(parts)})" if parts else fid
                ds_map[dsid]["fields"].append(label)

            # 2. JOINS_WITH relationships
            for r in session.run(
                """
                MATCH (a:Field)-[:JOINS_WITH]-(b:Field)
                WHERE id(a) < id(b)
                RETURN a.dataSourceId AS leftDs, a.fieldId AS leftField,
                       b.dataSourceId AS rightDs, b.fieldId AS rightField
                """
            ):
                joins.append(
                    (r["leftDs"], r["leftField"], r["rightDs"], r["rightField"])
                )

            # 3. SAME_AS relationships
            for r in session.run(
                """
                MATCH (a:Field)-[:SAME_AS]-(b:Field)
                WHERE id(a) < id(b)
                RETURN a.moduleId AS modA, a.dataSourceId AS dsA, a.fieldId AS fieldA,
                       b.moduleId AS modB, b.dataSourceId AS dsB, b.fieldId AS fieldB
                """
            ):
                same_as.append(
                    (
                        r["modA"],
                        r["dsA"],
                        r["fieldA"],
                        r["modB"],
                        r["dsB"],
                        r["fieldB"],
                    )
                )

        self._field_lookup = field_lookup
        self._field_meta = field_meta
        self._required_filters = required_filters
        self._ds_set = {ds for ds, _ in field_lookup}
        self._join_pairs = set()
        for left_ds, left_f, right_ds, right_f in joins:
            self._join_pairs.add((left_ds, left_f, right_ds, right_f))
            self._join_pairs.add((right_ds, right_f, left_ds, left_f))
        # Track module selectType and which module each data source belongs to
        self._module_select_type = {
            mid: mdata["selectType"] for mid, mdata in modules.items()
        }
        self._ds_to_module = {}
        for mid, mdata in modules.items():
            for dsid in mdata["dataSources"]:
                self._ds_to_module[dsid] = mid
        return modules, joins, same_as

    def _build_system_prompt(
        self, modules: dict, joins: list, same_as: list
    ) -> str:
        """Build system prompt from graph data"""
        schema_summary = []
        for mid, mdata in modules.items():
            header = f"\n### {mid}"
            if mdata["desc"]:
                header += f" - {mdata['desc']}"
            header += f" (selectType: {mdata['selectType']})" if mdata["selectType"] else ""
            schema_summary.append(header)
            for dsid, dsdata in mdata["dataSources"].items():
                ds_line = f"  **Data Source: {dsid}"
                ds_line += f"** ({dsdata['desc']})" if dsdata["desc"] else "**"
                schema_summary.append(ds_line)
                if dsdata["fields"]:
                    schema_summary.append(
                        f"    Fields: {', '.join(dsdata['fields'])}"
                    )

        # MultiSelect modules — all data sources are implicitly combinable
        multiselect_modules = []
        for mid, mdata in modules.items():
            if (mdata.get("selectType") or "").lower() == "multiselect":
                ds_list = list(mdata["dataSources"].keys())
                if len(ds_list) > 1:
                    multiselect_modules.append((mid, ds_list))
        multiselect_ds = set()
        if multiselect_modules:
            schema_summary.append("\n## MultiSelect Modules (Implicit Joins)")
            schema_summary.append(
                "All data sources in these modules can be combined in a single query WITHOUT explicit joins — "
                "just use fields from any of their data sources together:"
            )
            for mid, ds_list in multiselect_modules:
                schema_summary.append(f"  - {mid}: {', '.join(ds_list)}")
                multiselect_ds.update(ds_list)

        if joins:
            schema_summary.append("\n## Joinable Fields (JOINS_WITH)")
            schema_summary.append(
                "These field pairs can be used in explicit joins between data sources (including cross-module):"
            )
            for left_ds, left_f, right_ds, right_f in joins:
                schema_summary.append(
                    f"  - {left_ds}.{left_f} <-> {right_ds}.{right_f}"
                )

        all_ds = {
            dsid for mdata in modules.values() for dsid in mdata["dataSources"]
        }
        joinable_ds = set()
        for left_ds, _, right_ds, _ in joins:
            joinable_ds.add(left_ds)
            joinable_ds.add(right_ds)
        unjoinable = all_ds - joinable_ds - multiselect_ds
        if unjoinable:
            schema_summary.append("\n## Non-Joinable Data Sources")
            schema_summary.append(
                "These data sources CANNOT be joined with others:"
            )
            for ds in sorted(unjoinable):
                schema_summary.append(f"  - {ds}")

        if self._required_filters:
            schema_summary.append("\n## Required Filters")
            schema_summary.append(
                "These data sources REQUIRE specific filters when queried (due to large data volume):"
            )
            for ds, fields in sorted(self._required_filters.items()):
                for fid, ftype in fields:
                    hint = f" (use BETWEEN for date range)" if "Date" in ftype else ""
                    schema_summary.append(
                        f"  - {ds} requires filter on: {fid}{hint}"
                    )

        if same_as:
            schema_summary.append(
                "\n## Equivalent Fields Across Modules (SAME_AS)"
            )
            for mod_a, ds_a, f_a, mod_b, ds_b, f_b in same_as:
                schema_summary.append(
                    f"  - {mod_a}/{ds_a}.{f_a} = {mod_b}/{ds_b}.{f_b}"
                )

        return build_system_prompt("\n".join(schema_summary))

    # ---- Validation ----

    def validate_query(self, query: QueryConfig) -> List[str]:
        """Validate all fields in the query exist in the schema"""
        errors = []

        if query.fields:
            for field in query.fields:
                if not self._is_valid_field(field.dataSource, field.field_name):
                    errors.append(
                        f"Invalid field: '{field.field_name}' not found in data source '{field.dataSource}'"
                    )
                elif field.function:
                    errors.extend(self._validate_date_function(
                        field.dataSource, field.field_name, field.function
                    ))

        if query.calculated_fields:
            for calc_field in query.calculated_fields:
                for ds in calc_field.dataSources:
                    if not self._data_source_exists(ds):
                        errors.append(
                            f"Invalid data source for calculated field '{calc_field.alias}': '{ds}'"
                        )

        if query.filters and query.filters.conditions:
            errors.extend(self._validate_filter_conditions(query.filters.conditions))

        if query.joins:
            for join in query.joins:
                if not self._is_valid_field(
                    join.left_data_source, join.left_field
                ):
                    errors.append(
                        f"Invalid join field: '{join.left_field}' not found in '{join.left_data_source}'"
                    )
                if not self._is_valid_field(
                    join.right_data_source, join.right_field
                ):
                    errors.append(
                        f"Invalid join field: '{join.right_field}' not found in '{join.right_data_source}'"
                    )
                if (
                    join.left_data_source,
                    join.left_field,
                    join.right_data_source,
                    join.right_field,
                ) not in self._join_pairs:
                    # Allow implicit joins within the same MultiSelect module
                    left_mod = self._ds_to_module.get(join.left_data_source)
                    right_mod = self._ds_to_module.get(join.right_data_source)
                    in_same_multiselect = (
                        left_mod
                        and left_mod == right_mod
                        and (self._module_select_type.get(left_mod) or "").lower() == "multiselect"
                    )
                    if not in_same_multiselect:
                        errors.append(
                            f"Invalid join: no JOINS_WITH relationship between "
                            f"'{join.left_data_source}.{join.left_field}' and "
                            f"'{join.right_data_source}.{join.right_field}'"
                        )

        if query.aggregation:
            for agg_func in query.aggregation.functions:
                if agg_func.field_name == "*":
                    # COUNT(*) — just validate the data source exists
                    if not self._data_source_exists(agg_func.dataSource):
                        errors.append(
                            f"Invalid data source for COUNT(*): '{agg_func.dataSource}'"
                        )
                elif not self._is_valid_field(
                    agg_func.dataSource, agg_func.field_name
                ):
                    errors.append(
                        f"Invalid aggregation field: '{agg_func.field_name}' not found in '{agg_func.dataSource}'"
                    )
                else:
                    if agg_func.function:
                        errors.extend(self._validate_date_function(
                            agg_func.dataSource, agg_func.field_name, agg_func.function
                        ))
                    if agg_func.operator in ("SUM", "AVG") and agg_func.field_name != "*":
                        errors.extend(self._validate_numeric_field(
                            agg_func.dataSource, agg_func.field_name, agg_func.operator
                        ))
            # Collect all data sources used in the query for ambiguity checks
            query_ds = set()
            if query.fields:
                query_ds.update(f.dataSource for f in query.fields)
            if query.joins:
                for j in query.joins:
                    query_ds.add(j.left_data_source)
                    query_ds.add(j.right_data_source)
            for gb in query.aggregation.group_by:
                if gb.dataSource:
                    if not self._data_source_exists(gb.dataSource):
                        errors.append(
                            f"Invalid group_by data source: '{gb.dataSource}'"
                        )
                    elif not self._is_valid_field(gb.dataSource, gb.field):
                        errors.append(
                            f"Invalid group_by field: '{gb.field}' not found in '{gb.dataSource}'"
                        )
                else:
                    # No dataSource — check for ambiguity
                    matching_ds = [
                        ds for ds in query_ds
                        if (ds, gb.field) in self._field_lookup
                    ]
                    if len(matching_ds) == 0:
                        errors.append(
                            f"Invalid group_by field: '{gb.field}' not found in any data source"
                        )
                    elif len(matching_ds) > 1:
                        errors.append(
                            f"Ambiguous group_by field: '{gb.field}' exists in multiple data sources "
                            f"({', '.join(matching_ds)}). Add 'dataSource' to disambiguate."
                        )
            if query.aggregation.having:
                agg_aliases = {f.alias for f in query.aggregation.functions}
                for having in query.aggregation.having:
                    if having.aggregation_alias not in agg_aliases:
                        errors.append(
                            f"Invalid having clause: alias '{having.aggregation_alias}' "
                            f"does not match any aggregation function"
                        )

        if query.subqueries:
            for subquery in query.subqueries:
                sub_errors = self.validate_query(subquery.query)
                for err in sub_errors:
                    errors.append(f"In subquery '{subquery.alias}': {err}")

        # Check required filters for all data sources used in the query
        used_ds = set()
        if query.fields:
            used_ds.update(f.dataSource for f in query.fields)
        if query.calculated_fields:
            for cf in query.calculated_fields:
                used_ds.update(cf.dataSources)
        if query.joins:
            for j in query.joins:
                used_ds.add(j.left_data_source)
                used_ds.add(j.right_data_source)
        if query.aggregation:
            for af in query.aggregation.functions:
                used_ds.add(af.dataSource)

        # Collect all filtered fields from the query
        filtered_fields = set()
        if query.filters and query.filters.conditions:
            self._collect_filtered_fields(query.filters.conditions, filtered_fields)

        for ds in used_ds:
            if ds in self._required_filters:
                for fid, ftype in self._required_filters[ds]:
                    if (ds, fid) not in filtered_fields:
                        errors.append(
                            f"Data source '{ds}' requires a filter on '{fid}'"
                        )

        # Check that all used data sources are transitively reachable.
        # Two data sources are directly connected if they:
        #   - are in the same MultiSelect module (implicit join), OR
        #   - have an explicit join between them
        # Transitive reachability: if A connects to B and B connects to C,
        # then A, B, C are all combinable — no direct link needed for every pair.
        if len(used_ds) > 1:
            # Union-Find to build connected groups
            parent = {ds: ds for ds in used_ds}

            def find(x):
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            def union(a, b):
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[ra] = rb

            # Connect data sources in the same MultiSelect module
            multiselect_groups = {}
            for ds in used_ds:
                mod = self._ds_to_module.get(ds)
                if mod and (self._module_select_type.get(mod) or "").lower() == "multiselect":
                    if mod not in multiselect_groups:
                        multiselect_groups[mod] = []
                    multiselect_groups[mod].append(ds)
            for ds_group in multiselect_groups.values():
                for ds in ds_group[1:]:
                    union(ds_group[0], ds)

            # Connect data sources with explicit joins
            if query.joins:
                for j in query.joins:
                    if j.left_data_source in used_ds and j.right_data_source in used_ds:
                        union(j.left_data_source, j.right_data_source)

            # All used data sources must be in one connected group
            roots = {find(ds) for ds in used_ds}
            if len(roots) > 1:
                # Build the disconnected groups for a clear error message
                groups = {}
                for ds in sorted(used_ds):
                    r = find(ds)
                    if r not in groups:
                        groups[r] = []
                    groups[r].append(ds)
                group_strs = [", ".join(g) for g in groups.values()]
                errors.append(
                    f"Data sources are not all connected. "
                    f"Disconnected groups: [{'] / ['.join(group_strs)}]. "
                    f"Add explicit joins between groups or use data sources from the same MultiSelect module."
                )

        return errors

    @staticmethod
    def _collect_filtered_fields(
        conditions: List[Union[FilterCondition, FilterGroup]], result: set
    ):
        """Recursively collect all (dataSource, field_name) pairs from filter conditions."""
        for condition in conditions:
            if isinstance(condition, FilterCondition):
                result.add((condition.dataSource, condition.field_name))
            elif isinstance(condition, FilterGroup):
                QueryGenerator._collect_filtered_fields(condition.conditions, result)

    def _is_valid_field(self, data_source: str, field_name: str) -> bool:
        return (data_source, field_name) in self._field_lookup

    def _data_source_exists(self, data_source: str) -> bool:
        return data_source in self._ds_set

    def _validate_date_function(
        self, data_source: str, field_name: str, function: str
    ) -> List[str]:
        """Check that a date function (YEAR/MONTH/DAY) is applied to a date field."""
        key = (data_source, field_name)
        if key in self._field_meta:
            ftype = self._field_meta[key]["type"]
            if ftype and ftype != "date":
                return [
                    f"Cannot apply {function} to '{field_name}' in '{data_source}' — "
                    f"field type is '{ftype}', expected 'date'"
                ]
        return []

    def _validate_numeric_field(
        self, data_source: str, field_name: str, operator: str
    ) -> List[str]:
        """Check that SUM/AVG is applied to a numeric field."""
        key = (data_source, field_name)
        if key in self._field_meta:
            ftype = self._field_meta[key]["type"]
            if ftype and ftype not in ("decimal", "int", "integer", "number", "float"):
                return [
                    f"Cannot apply {operator} to '{field_name}' in '{data_source}' — "
                    f"field type is '{ftype}', expected numeric"
                ]
        return []

    def _validate_filter_conditions(
        self, conditions: List[Union[FilterCondition, FilterGroup]]
    ) -> List[str]:
        errors = []
        for condition in conditions:
            if isinstance(condition, FilterCondition):
                key = (condition.dataSource, condition.field_name)
                if not self._is_valid_field(*key):
                    errors.append(
                        f"Invalid filter field: '{condition.field_name}' not found in '{condition.dataSource}'"
                    )
                elif key in self._field_meta:
                    meta = self._field_meta[key]
                    op = condition.operator
                    val = condition.value

                    if condition.function:
                        errors.extend(self._validate_date_function(
                            condition.dataSource, condition.field_name, condition.function
                        ))

                    if not meta["is_freeform"]:
                        # Non-freeform: no fuzzy matching allowed
                        if op in ("LIKE", "NOT LIKE"):
                            errors.append(
                                f"Field '{condition.field_name}' in '{condition.dataSource}' is not freeform — "
                                f"use exact match (=, IN) instead of {op}"
                            )
                        # Non-freeform with enums: value must be from enum set
                        enum_opts = meta["enum_options"]
                        if enum_opts and val is not None:
                            allowed = set(enum_opts)
                            if op == "=" and str(val) not in allowed:
                                errors.append(
                                    f"Invalid value '{val}' for '{condition.field_name}' — "
                                    f"allowed values: {', '.join(enum_opts)}"
                                )
                            elif op in ("IN", "NOT IN") and isinstance(val, list):
                                bad = [str(v) for v in val if str(v) not in allowed]
                                if bad:
                                    errors.append(
                                        f"Invalid values {bad} for '{condition.field_name}' — "
                                        f"allowed values: {', '.join(enum_opts)}"
                                    )
                    else:
                        # Freeform: warn if using exact match (= is valid but LIKE is preferred)
                        if op == "=" and val is not None and isinstance(val, str):
                            errors.append(
                                f"Field '{condition.field_name}' is freeform — "
                                f"consider using LIKE with '%{val}%' for keyword matching instead of exact ="
                            )
            elif isinstance(condition, FilterGroup):
                errors.extend(
                    self._validate_filter_conditions(condition.conditions)
                )
        return errors

    # ---- Generation ----

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON from LLM response, handling think tags and markdown."""
        # Strip Qwen3 <think> blocks
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        # Strip markdown code fences
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
        return text

    def generate_query(
        self, user_question: str, validate: bool = True
    ) -> QueryConfig:
        """Generate a query from natural language.

        On validation failure, automatically retries once with error feedback
        so the LLM can self-correct.
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": f"Question: {user_question}\n\nRespond with JSON only.",
            },
        ]

        for attempt in range(2):  # at most 1 retry
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0,
                    max_tokens=4096,
                )
                raw = response.choices[0].message.content
                content = self._extract_json(raw)
                json_data = json.loads(content)
                query_config = QueryConfig(**json_data)

                if validate:
                    errors = self.validate_query(query_config)
                    if errors and attempt == 0:
                        # Feed errors back for self-correction
                        messages.append({"role": "assistant", "content": raw})
                        feedback = "Validation errors:\n" + "\n".join(
                            f"- {e}" for e in errors
                        )
                        feedback += "\n\nFix these errors using ONLY fields from the schema. Respond with corrected JSON only."
                        messages.append({"role": "user", "content": feedback})
                        continue
                    elif errors:
                        raise ValidationError(
                            "Query validation failed:\n"
                            + "\n".join(f"  - {e}" for e in errors)
                        )

                return query_config

            except json.JSONDecodeError as e:
                if attempt == 0:
                    # Retry: ask for clean JSON
                    messages.append({"role": "assistant", "content": raw})
                    messages.append(
                        {
                            "role": "user",
                            "content": "Invalid JSON. Respond with valid JSON only, no markdown or explanation.",
                        }
                    )
                    continue
                raise ValueError(
                    f"Failed to parse LLM response as JSON: {e}\nResponse: {raw[:200]}"
                )
            except (ValidationError, ValueError):
                raise
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt == 0:
                    continue
                raise RuntimeError(f"Network error after retry: {e}")
            except Exception as e:
                raise RuntimeError(
                    f"Error generating query: {type(e).__name__}: {e}"
                )

        raise RuntimeError("Query generation failed after all retry attempts")

    def close(self):
        """Close the Neo4j driver"""
        self.driver.close()

    def print_query(self, query: QueryConfig):
        """Pretty print the query configuration"""
        print("\n" + "=" * 60)
        print("GENERATED QUERY CONFIGURATION")
        print("=" * 60)
        print(json.dumps(query.model_dump(), indent=2))
        print("=" * 60 + "\n")


def main():
    """Main interactive loop"""
    print("\n" + "=" * 60)
    print("CRS Query Generator")
    print("=" * 60)
    print("Ask questions about employee data (or type 'quit' to exit)")
    print("=" * 60 + "\n")

    try:
        generator = QueryGenerator()
        print(
            f"✓ Loaded schema from Neo4j ({len(generator._field_lookup)} valid fields)"
        )
        print(f"✓ Using model: {generator.model}")
        print(f"✓ API endpoint: {generator.base_url}\n")
    except Exception as e:
        print(f"✗ Failed to initialize: {e}")
        import traceback

        traceback.print_exc()
        return

    try:
        while True:
            try:
                user_input = input("Enter your question: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ("quit", "exit", "q"):
                    print("\nGoodbye!")
                    break

                print("\nGenerating query...")
                query = generator.generate_query(user_input)
                generator.print_query(query)

            except KeyboardInterrupt:
                print("\n\nGoodbye!")
                break
            except Exception as e:
                print(f"\n✗ Error: {e}\n")
    finally:
        generator.close()


if __name__ == "__main__":
    main()
