"""
Neo4j graph service for CodeVault.
Manages nodes and relationships for a specific project namespace.
"""
import logging
from django.conf import settings

logger = logging.getLogger(__name__)


class GraphService:
    """Manages Neo4j graph operations scoped to a project namespace."""

    def __init__(self, project_namespace: str):
        self.namespace = project_namespace
        self._driver = None
        self._indexes_ensured = False

    def _get_driver(self):
        if self._driver is None:
            from neo4j import GraphDatabase
            self._driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            )
        return self._driver

    def close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def ensure_indexes(self):
        """Create Neo4j indexes for efficient lookups."""
        indexes = [
            "CREATE INDEX IF NOT EXISTS FOR (f:File) ON (f.namespace, f.path)",
            "CREATE INDEX IF NOT EXISTS FOR (fn:Function) ON (fn.namespace, fn.name)",
            "CREATE INDEX IF NOT EXISTS FOR (fn:Function) ON (fn.namespace, fn.file_path)",
            "CREATE INDEX IF NOT EXISTS FOR (c:Class) ON (c.namespace, c.name)",
            "CREATE INDEX IF NOT EXISTS FOR (ep:APIEndpoint) ON (ep.namespace, ep.pattern)",
            "CREATE INDEX IF NOT EXISTS FOR (s:Signal) ON (s.namespace, s.handler)",
            "CREATE INDEX IF NOT EXISTS FOR (cj:CronJob) ON (cj.namespace, cj.task_name)",
            "CREATE INDEX IF NOT EXISTS FOR (n:DjangoModel) ON (n.namespace, n.name)",
        ]
        with self._get_driver().session() as session:
            for idx in indexes:
                try:
                    session.run(idx)
                except Exception as e:
                    logger.warning(f"[GraphService] Index creation issue: {e}")
        logger.info(f"[GraphService] Indexes ensured for {self.namespace}")

    def _ensure_indexes_once(self):
        if not self._indexes_ensured:
            self.ensure_indexes()
            self._indexes_ensured = True

    # ------------------------------------------------------------------ #
    #  Mutations                                                           #
    # ------------------------------------------------------------------ #

    def clear_project(self):
        """Remove ALL nodes for this project namespace."""
        with self._get_driver().session() as session:
            session.run(
                "MATCH (n {namespace: $ns}) DETACH DELETE n",
                ns=self.namespace,
            )
        logger.info(f"[GraphService] Cleared all nodes for namespace {self.namespace}")
        self.ensure_indexes()

    def delete_file(self, file_path: str):
        """Remove a file node and all entities it defines."""
        with self._get_driver().session() as session:
            session.run("""
                MATCH (f:File {path: $path, namespace: $ns})
                OPTIONAL MATCH (f)-[:DEFINES]->(child)
                DETACH DELETE f, child
            """, path=file_path, ns=self.namespace)

    def ingest_file(self, file_path: str, parsed_data):
        """Upsert all extracted entities for a file into Neo4j."""
        self._ensure_indexes_once()
        with self._get_driver().session() as session:
            session.execute_write(self._ingest_tx, file_path, parsed_data)
        logger.info(f"[GraphService] Ingested {file_path} → {self.namespace}")

    def _ingest_tx(self, tx, file_path: str, parsed_data):
        ns = self.namespace

        # 1. Upsert File node
        tx.run("""
            MERGE (f:File {path: $path, namespace: $ns})
            SET f.last_updated = timestamp()
        """, path=file_path, ns=ns)

        # 2. Functions
        for func in parsed_data.functions:
            tx.run("""
                MATCH (f:File {path: $path, namespace: $ns})
                MERGE (fn:Function {name: $name, file_path: $path, namespace: $ns})
                SET fn.start_line    = $start,
                    fn.end_line      = $end,
                    fn.is_method     = $is_method,
                    fn.parent_class  = $parent_class,
                    fn.is_async      = $is_async,
                    fn.code          = $code,
                    fn.docstring     = $docstring,
                    fn.description   = $description,
                    fn.decorators    = $decorators
                MERGE (f)-[:DEFINES]->(fn)
            """,
                path=file_path, ns=ns,
                name=func.name,
                start=func.start_line,
                end=func.end_line,
                is_method=func.is_method,
                parent_class=func.parent_class or '',
                is_async=func.is_async,
                code=func.code[:2000],
                docstring=func.docstring or '',
                description=func.description or '',
                decorators=func.decorators,
            )

        # 3. Classes
        for cls in parsed_data.classes:
            tx.run("""
                MATCH (f:File {path: $path, namespace: $ns})
                MERGE (c:Class {name: $name, file_path: $path, namespace: $ns})
                SET c.start_line     = $start,
                    c.end_line       = $end,
                    c.bases          = $bases,
                    c.is_django_model= $is_model,
                    c.docstring      = $docstring,
                    c.description    = $description,
                    c.fields         = $fields
                MERGE (f)-[:DEFINES]->(c)
            """,
                path=file_path, ns=ns,
                name=cls.name,
                start=cls.start_line,
                end=cls.end_line,
                bases=cls.bases,
                is_model=cls.is_django_model,
                docstring=cls.docstring or '',
                description=cls.description or '',
                fields=[f"{f['name']}: {f['type']}" for f in cls.fields],
            )
            if cls.is_django_model:
                tx.run("""
                    MATCH (c:Class {name: $name, namespace: $ns, file_path: $path})
                    SET c:DjangoModel
                """, name=cls.name, ns=ns, path=file_path)

        # 4. API Endpoints
        for ep in parsed_data.endpoints:
            tx.run("""
                MATCH (f:File {path: $path, namespace: $ns})
                MERGE (ep:APIEndpoint {pattern: $pattern, namespace: $ns})
                SET ep.view_name    = $view,
                    ep.file_path    = $path,
                    ep.http_methods = $methods,
                    ep.description  = $description
                MERGE (f)-[:DEFINES]->(ep)
            """,
                path=file_path, ns=ns,
                pattern=ep.url_pattern,
                view=ep.view_name,
                methods=ep.http_methods,
                description=ep.description or '',
            )
            # Try to link endpoint → handler function
            tx.run("""
                MATCH (ep:APIEndpoint {pattern: $pattern, namespace: $ns})
                MATCH (fn:Function {namespace: $ns})
                WHERE fn.name = split($view, '.')[-1]
                   OR fn.name = $view
                MERGE (ep)-[:TRIGGERS]->(fn)
            """, pattern=ep.url_pattern, ns=ns, view=ep.view_name)

        # 5. Signals
        for sig in parsed_data.signals:
            tx.run("""
                MATCH (f:File {path: $path, namespace: $ns})
                MERGE (s:Signal {signal_type: $sig_type, handler: $handler, namespace: $ns})
                SET s.sender    = $sender,
                    s.file_path = $path
                MERGE (f)-[:DEFINES]->(s)
            """,
                path=file_path, ns=ns,
                sig_type=sig.signal_type,
                handler=sig.handler_function,
                sender=sig.sender or '',
            )
            tx.run("""
                MATCH (s:Signal {handler: $handler, namespace: $ns})
                MATCH (fn:Function {name: $handler, namespace: $ns})
                MERGE (s)-[:HANDLED_BY]->(fn)
            """, handler=sig.handler_function, ns=ns)

        # 6. Cron Jobs
        for cron in parsed_data.cron_jobs:
            tx.run("""
                MATCH (f:File {path: $path, namespace: $ns})
                MERGE (cj:CronJob {task_name: $name, namespace: $ns})
                SET cj.schedule  = $schedule,
                    cj.file_path = $path
                MERGE (f)-[:DEFINES]->(cj)
            """,
                path=file_path, ns=ns,
                name=cron.task_name,
                schedule=cron.schedule,
            )

    # ------------------------------------------------------------------ #
    #  Queries                                                             #
    # ------------------------------------------------------------------ #

    def query_graph(self, cypher: str, params: dict = None) -> list:
        """Execute a read-only Cypher query and return list of dicts."""
        with self._get_driver().session() as session:
            result = session.run(cypher, **(params or {}))
            return [record.data() for record in result]

    def get_file_summary(self, file_path: str) -> dict:
        results = self.query_graph("""
            MATCH (f:File {path: $path, namespace: $ns})
            OPTIONAL MATCH (f)-[:DEFINES]->(fn:Function)
            OPTIONAL MATCH (f)-[:DEFINES]->(c:Class)
            OPTIONAL MATCH (f)-[:DEFINES]->(ep:APIEndpoint)
            OPTIONAL MATCH (f)-[:DEFINES]->(s:Signal)
            OPTIONAL MATCH (f)-[:DEFINES]->(cj:CronJob)
            RETURN f.path AS file,
                   collect(DISTINCT fn.name) AS functions,
                   collect(DISTINCT c.name)  AS classes,
                   collect(DISTINCT ep.pattern) AS endpoints,
                   collect(DISTINCT s.signal_type) AS signals,
                   collect(DISTINCT cj.task_name) AS cron_jobs
        """, {'path': file_path, 'ns': self.namespace})
        return results[0] if results else {}

    def get_all_endpoints(self) -> list:
        return self.query_graph("""
            MATCH (ep:APIEndpoint {namespace: $ns})
            OPTIONAL MATCH (ep)-[:TRIGGERS]->(fn:Function)
            RETURN ep.pattern      AS pattern,
                   ep.view_name    AS view,
                   ep.http_methods AS methods,
                   ep.file_path    AS file,
                   ep.description  AS description,
                   fn.name         AS handler_function,
                   fn.start_line   AS handler_line,
                   fn.description  AS handler_description
            ORDER BY ep.pattern
        """, {'ns': self.namespace})

    def get_all_models(self) -> list:
        return self.query_graph("""
            MATCH (c:DjangoModel {namespace: $ns})
            RETURN c.name          AS name,
                   c.file_path     AS file,
                   c.start_line    AS start_line,
                   c.end_line      AS end_line,
                   c.bases         AS bases,
                   c.fields        AS fields,
                   c.docstring     AS docstring,
                   c.description   AS description
            ORDER BY c.name
        """, {'ns': self.namespace})

    def get_all_files(self) -> list:
        return self.query_graph("""
            MATCH (f:File {namespace: $ns})
            OPTIONAL MATCH (f)-[:DEFINES]->(fn:Function)
            OPTIONAL MATCH (f)-[:DEFINES]->(c:Class)
            OPTIONAL MATCH (f)-[:DEFINES]->(ep:APIEndpoint)
            RETURN f.path AS path,
                   count(DISTINCT fn) AS function_count,
                   count(DISTINCT c) AS class_count,
                   count(DISTINCT ep) AS endpoint_count
            ORDER BY f.path
        """, {'ns': self.namespace})

    def search_functions(self, query: str, limit: int = 20) -> list:
        return self.query_graph("""
            MATCH (fn:Function {namespace: $ns})
            WHERE toLower(fn.name) CONTAINS toLower($term)
               OR toLower(coalesce(fn.docstring, '')) CONTAINS toLower($term)
               OR toLower(coalesce(fn.parent_class, '')) CONTAINS toLower($term)
            RETURN fn.name         AS name,
                   fn.file_path    AS file,
                   fn.start_line   AS start_line,
                   fn.end_line     AS end_line,
                   fn.is_method    AS is_method,
                   fn.parent_class AS parent_class,
                   fn.is_async     AS is_async,
                   fn.decorators   AS decorators,
                   fn.docstring    AS docstring,
                   fn.code         AS code
            ORDER BY fn.name
            LIMIT $limit
        """, {'ns': self.namespace, 'term': query, 'limit': limit})

    def search_classes(self, query: str, limit: int = 20) -> list:
        return self.query_graph("""
            MATCH (c:Class {namespace: $ns})
            WHERE toLower(c.name) CONTAINS toLower($term)
               OR toLower(coalesce(c.description, '')) CONTAINS toLower($term)
               OR toLower(coalesce(c.docstring, '')) CONTAINS toLower($term)
               OR ANY(b IN c.bases WHERE toLower(b) CONTAINS toLower($term))
            RETURN c.name          AS name,
                   c.file_path     AS file,
                   c.start_line    AS start_line,
                   c.end_line      AS end_line,
                   c.bases         AS bases,
                   c.is_django_model AS is_django_model,
                   c.fields        AS fields,
                   c.docstring     AS docstring,
                   c.description   AS description
            ORDER BY c.name
            LIMIT $limit
        """, {'ns': self.namespace, 'term': query, 'limit': limit})

    def get_class_context(self, class_name: str) -> dict:
        """Full class context including its methods and whether it's a Django model."""
        results = self.query_graph("""
            MATCH (c:Class {name: $name, namespace: $ns})
            OPTIONAL MATCH (f:File {path: c.file_path, namespace: $ns})-[:DEFINES]->(fn:Function)
            WHERE fn.parent_class = $name
            RETURN c.name          AS name,
                   c.file_path     AS file,
                   c.start_line    AS start_line,
                   c.end_line      AS end_line,
                   c.bases         AS bases,
                   c.is_django_model AS is_django_model,
                   c.fields        AS fields,
                   c.docstring     AS docstring,
                   c.description   AS description,
                   collect(DISTINCT {
                       name: fn.name,
                       start_line: fn.start_line,
                       is_async: fn.is_async,
                       description: fn.description,
                       docstring: fn.docstring
                   }) AS methods
        """, {'name': class_name, 'ns': self.namespace})
        return results[0] if results else {}

    def get_function_context(self, function_name: str) -> dict:
        """Full context: function details + which endpoints trigger it + signals it handles."""
        results = self.query_graph("""
            MATCH (fn:Function {name: $name, namespace: $ns})
            OPTIONAL MATCH (ep:APIEndpoint)-[:TRIGGERS]->(fn)
            OPTIONAL MATCH (s:Signal)-[:HANDLED_BY]->(fn)
            RETURN fn.name         AS name,
                   fn.file_path    AS file,
                   fn.start_line   AS start_line,
                   fn.end_line     AS end_line,
                   fn.is_method    AS is_method,
                   fn.parent_class AS parent_class,
                   fn.is_async     AS is_async,
                   fn.decorators   AS decorators,
                   fn.docstring    AS docstring,
                   fn.code         AS code,
                   collect(DISTINCT ep.pattern)    AS triggered_by_endpoints,
                   collect(DISTINCT s.signal_type) AS handles_signals
        """, {'name': function_name, 'ns': self.namespace})
        return results[0] if results else {}

    def get_project_stats(self) -> dict:
        result = self.query_graph("""
            MATCH (n {namespace: $ns})
            RETURN
                count(CASE WHEN 'File'        IN labels(n) THEN 1 END) AS files,
                count(CASE WHEN 'Function'    IN labels(n) THEN 1 END) AS functions,
                count(CASE WHEN 'Class'       IN labels(n) THEN 1 END) AS classes,
                count(CASE WHEN 'DjangoModel' IN labels(n) THEN 1 END) AS models,
                count(CASE WHEN 'APIEndpoint' IN labels(n) THEN 1 END) AS endpoints,
                count(CASE WHEN 'Signal'      IN labels(n) THEN 1 END) AS signals,
                count(CASE WHEN 'CronJob'     IN labels(n) THEN 1 END) AS cron_jobs
        """, {'ns': self.namespace})
        return result[0] if result else {
            'files': 0, 'functions': 0, 'classes': 0, 'models': 0,
            'endpoints': 0, 'signals': 0, 'cron_jobs': 0,
        }

    def run_custom_cypher(self, cypher: str, params: dict = None) -> list:
        """Execute arbitrary Cypher query (admin use)."""
        return self.query_graph(cypher, params)
