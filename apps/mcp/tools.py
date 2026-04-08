"""
MCP tool definitions for CodeVault.
Rich tool descriptions optimized for Claude Desktop / Cursor / AI agent context.
"""

TOOLS = [
    {
        "name": "search_codebase",
        "description": (
            "Semantically search the codebase using natural language. "
            "Returns ranked code snippets (functions, classes) with file paths, "
            "line numbers, and similarity scores. Use this to find relevant code "
            "when you know what functionality you're looking for but not where it lives. "
            "Examples: 'user authentication logic', 'database connection pooling', "
            "'error handling middleware'."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_slug": {
                    "type": "string",
                    "description": "Project identifier (URL slug). Use list_projects to find available slugs.",
                },
                "query": {
                    "type": "string",
                    "description": "Natural language description of what you're looking for",
                },
                "type_filter": {
                    "type": "string",
                    "enum": ["function", "class", "any"],
                    "default": "any",
                    "description": "Filter results: 'function' for functions/methods only, 'class' for classes/structs, 'any' for all",
                },
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                    "description": "Maximum results to return (1-50)",
                },
            },
            "required": ["project_slug", "query"],
        },
    },
    {
        "name": "get_function",
        "description": (
            "Look up functions or methods in the project. Two modes:\n"
            "1. Exact lookup (provide function_name): returns full source code, "
            "file location, line numbers, docstring, which API endpoints trigger it, "
            "and which signals it handles.\n"
            "2. Search (provide search term or leave both empty): returns a list of "
            "matching functions filtered by name or docstring.\n"
            "Use exact lookup after search_codebase to dive deep into a specific function."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_slug": {
                    "type": "string",
                    "description": "Project identifier (slug)",
                },
                "function_name": {
                    "type": "string",
                    "description": "Exact function/method name for full context lookup (e.g., 'create_user'). Omit to use search mode.",
                },
                "search": {
                    "type": "string",
                    "description": "Search term to filter functions by name or docstring. Used when function_name is not provided.",
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Max results in search mode (1-100)",
                },
            },
            "required": ["project_slug"],
        },
    },
    {
        "name": "get_class",
        "description": (
            "Look up classes, structs, or models in the project. Two modes:\n"
            "1. Exact lookup (provide class_name): returns full source code, "
            "base classes/interfaces, fields, methods, and file location. "
            "Especially useful for understanding data models and their relationships.\n"
            "2. Search (provide search term or leave both empty): returns a list of "
            "matching classes filtered by name, description, docstring, or base class."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_slug": {
                    "type": "string",
                    "description": "Project identifier (slug)",
                },
                "class_name": {
                    "type": "string",
                    "description": "Exact class/struct name for full context lookup (e.g., 'User', 'PaymentService'). Omit to use search mode.",
                },
                "search": {
                    "type": "string",
                    "description": "Search term to filter classes by name, docstring, or base class. Used when class_name is not provided.",
                },
                "limit": {
                    "type": "integer",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                    "description": "Max results in search mode (1-100)",
                },
            },
            "required": ["project_slug"],
        },
    },
    {
        "name": "list_api_endpoints",
        "description": (
            "List ALL REST API endpoints discovered in the project. "
            "Shows URL patterns, HTTP methods, handler functions, and file locations. "
            "Works across frameworks: Django urls.py, Express routes, Spring controllers, "
            "Go HTTP handlers, Actix/Axum routes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_slug": {
                    "type": "string",
                    "description": "Project identifier (slug)",
                },
            },
            "required": ["project_slug"],
        },
    },
    {
        "name": "list_models",
        "description": (
            "List all data models/entities in the project: Django ORM models, "
            "SQLAlchemy models, JPA entities, Go structs with DB tags, "
            "Rust Diesel models. Shows name, base classes, file location, and fields."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_slug": {
                    "type": "string",
                    "description": "Project identifier (slug)",
                },
            },
            "required": ["project_slug"],
        },
    },
    {
        "name": "ask_codebase",
        "description": (
            "Ask a natural language question about the codebase and get an "
            "LLM-synthesized answer with references to specific files and functions. "
            "The answer combines semantic code search with structural graph context "
            "for accurate, grounded responses. Great for understanding architecture, "
            "data flow, business logic, or debugging.\n\n"
            "Effort levels control depth vs speed:\n"
            "- 'low': Fast semantic search only (~2s). Best for simple lookups.\n"
            "- 'medium': Semantic + 1-hop graph expansion (~5s). Best for most questions.\n"
            "- 'high': Full multi-hop traversal with models/endpoints context (~10s). "
            "Best for complex architectural questions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_slug": {
                    "type": "string",
                    "description": "Project identifier (slug)",
                },
                "question": {
                    "type": "string",
                    "description": "Your question about the codebase in natural language",
                },
                "effort": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "default": "medium",
                    "description": "Query depth: low=fast, medium=balanced, high=thorough",
                },
            },
            "required": ["project_slug", "question"],
        },
    },
    {
        "name": "get_project_stats",
        "description": (
            "Get a high-level overview of an indexed project: total files, "
            "functions, classes, API endpoints, signals, cron jobs, and "
            "vector embeddings count. Use this first to understand project scope."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_slug": {
                    "type": "string",
                    "description": "Project identifier (slug)",
                },
            },
            "required": ["project_slug"],
        },
    },
    {
        "name": "list_files",
        "description": (
            "List all indexed source files in the project with entity counts "
            "(functions, classes, endpoints per file) and AI-generated file summaries "
            "where available. Optionally filter by filename. "
            "Use this to understand project structure and find specific files."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_slug": {
                    "type": "string",
                    "description": "Project identifier (slug)",
                },
                "search": {
                    "type": "string",
                    "description": "Filter files by path substring (e.g., 'auth', 'models', 'api/')",
                },
            },
            "required": ["project_slug"],
        },
    },
    {
        "name": "get_file_summary",
        "description": (
            "Get a detailed summary of a specific file: all functions, classes, "
            "endpoints, signals, and cron jobs defined in it. Use this to understand "
            "what a particular file does before diving into specific functions."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_slug": {
                    "type": "string",
                    "description": "Project identifier (slug)",
                },
                "file_path": {
                    "type": "string",
                    "description": "Relative file path within the project (e.g., 'apps/auth/views.py')",
                },
            },
            "required": ["project_slug", "file_path"],
        },
    },
    {
        "name": "get_dependency_graph",
        "description": (
            "Trace the dependency chain for a function or class: "
            "what calls it, what it calls, which endpoints trigger it, "
            "and which signals it handles. Essential for impact analysis "
            "before making code changes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_slug": {
                    "type": "string",
                    "description": "Project identifier (slug)",
                },
                "entity_name": {
                    "type": "string",
                    "description": "Function or class name to trace dependencies for",
                },
                "depth": {
                    "type": "integer",
                    "default": 2,
                    "minimum": 1,
                    "maximum": 5,
                    "description": "How many hops to trace (1-5)",
                },
            },
            "required": ["project_slug", "entity_name"],
        },
    },
    {
        "name": "list_projects",
        "description": (
            "List all projects you have access to, with their slugs, "
            "descriptions, languages, and last indexed timestamps. "
            "Use this first if you don't know the project slug."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]
