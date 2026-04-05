"""
Tests for MCP server and tool definitions.
"""
import json
import pytest
from apps.mcp.tools import TOOLS


class TestMCPTools:
    """Test MCP tool definitions are well-formed."""

    def test_all_tools_have_required_fields(self):
        for tool in TOOLS:
            assert 'name' in tool, f"Tool missing 'name'"
            assert 'description' in tool, f"Tool {tool.get('name')} missing 'description'"
            assert 'inputSchema' in tool, f"Tool {tool.get('name')} missing 'inputSchema'"

    def test_all_schemas_are_valid(self):
        for tool in TOOLS:
            schema = tool['inputSchema']
            assert schema.get('type') == 'object'
            assert 'properties' in schema

    def test_required_fields_exist_in_properties(self):
        for tool in TOOLS:
            schema = tool['inputSchema']
            required = schema.get('required', [])
            properties = schema.get('properties', {})
            for field in required:
                assert field in properties, (
                    f"Tool {tool['name']}: required field '{field}' not in properties"
                )

    def test_tool_names_are_unique(self):
        names = [t['name'] for t in TOOLS]
        assert len(names) == len(set(names))

    def test_expected_tools_exist(self):
        names = {t['name'] for t in TOOLS}
        expected = {
            'search_codebase', 'get_function', 'list_api_endpoints',
            'ask_codebase', 'get_project_stats', 'list_files',
        }
        assert expected.issubset(names)

    def test_tool_count_minimum(self):
        assert len(TOOLS) >= 7

    def test_search_codebase_tool(self):
        search_tool = next(t for t in TOOLS if t['name'] == 'search_codebase')
        assert 'project_slug' in search_tool['inputSchema']['required']
        assert 'query' in search_tool['inputSchema']['required']
        assert 'type_filter' in search_tool['inputSchema']['properties']
        assert search_tool['inputSchema']['properties']['limit']['maximum'] == 50

    def test_ask_codebase_tool(self):
        ask_tool = next(t for t in TOOLS if t['name'] == 'ask_codebase')
        assert 'project_slug' in ask_tool['inputSchema']['required']
        assert 'question' in ask_tool['inputSchema']['required']
        effort_prop = ask_tool['inputSchema']['properties']['effort']
        assert 'low' in effort_prop['enum']
        assert 'medium' in effort_prop['enum']
        assert 'high' in effort_prop['enum']

    def test_get_function_tool(self):
        fn_tool = next(t for t in TOOLS if t['name'] == 'get_function')
        assert 'project_slug' in fn_tool['inputSchema']['required']
        assert 'function_name' in fn_tool['inputSchema']['required']

    def test_get_class_tool(self):
        cls_tool = next(t for t in TOOLS if t['name'] == 'get_class')
        assert 'project_slug' in cls_tool['inputSchema']['required']
        assert 'class_name' in cls_tool['inputSchema']['required']

    def test_list_api_endpoints_tool(self):
        ep_tool = next(t for t in TOOLS if t['name'] == 'list_api_endpoints')
        assert 'project_slug' in ep_tool['inputSchema']['required']

    def test_get_project_stats_tool(self):
        stats_tool = next(t for t in TOOLS if t['name'] == 'get_project_stats')
        assert 'project_slug' in stats_tool['inputSchema']['required']

    def test_list_files_tool(self):
        files_tool = next(t for t in TOOLS if t['name'] == 'list_files')
        assert 'project_slug' in files_tool['inputSchema']['required']
        assert 'search' in files_tool['inputSchema']['properties']

    def test_all_descriptions_not_empty(self):
        for tool in TOOLS:
            assert len(tool['description']) > 10

    def test_all_tools_json_serializable(self):
        try:
            json.dumps(TOOLS)
        except TypeError as e:
            pytest.fail(f"Tools not JSON serializable: {e}")


class TestMCPToolValidation:
    """Validate tool schemas match JSON Schema standards."""

    def test_type_filter_enum_values(self):
        search_tool = next(t for t in TOOLS if t['name'] == 'search_codebase')
        type_filter = search_tool['inputSchema']['properties']['type_filter']
        assert type_filter['type'] == 'string'
        assert set(type_filter['enum']) >= {'function', 'class', 'any'}

    def test_effort_enum_values(self):
        ask_tool = next(t for t in TOOLS if t['name'] == 'ask_codebase')
        effort = ask_tool['inputSchema']['properties']['effort']
        assert effort['type'] == 'string'
        assert set(effort['enum']) == {'low', 'medium', 'high'}

    def test_limit_integer_bounds(self):
        search_tool = next(t for t in TOOLS if t['name'] == 'search_codebase')
        limit = search_tool['inputSchema']['properties']['limit']
        assert limit['type'] == 'integer'
        assert limit['minimum'] == 1
        assert limit['maximum'] == 50

    def test_depth_integer_bounds(self):
        dep_tool = next(t for t in TOOLS if t['name'] == 'get_dependency_graph')
        depth = dep_tool['inputSchema']['properties']['depth']
        assert depth['type'] == 'integer'
        assert depth['minimum'] == 1
        assert depth['maximum'] == 5

    def test_get_file_summary_tool(self):
        file_tool = next(
            (t for t in TOOLS if t['name'] == 'get_file_summary'),
            None
        )
        if file_tool:
            assert 'project_slug' in file_tool['inputSchema']['required']
            assert 'file_path' in file_tool['inputSchema']['required']

    def test_get_dependency_graph_tool(self):
        dep_tool = next(
            (t for t in TOOLS if t['name'] == 'get_dependency_graph'),
            None
        )
        if dep_tool:
            assert 'project_slug' in dep_tool['inputSchema']['required']
            assert 'entity_name' in dep_tool['inputSchema']['required']


class TestMCPToolDescriptions:
    """Verify tool descriptions are helpful and accurate."""

    def test_descriptions_mention_frameworks(self):
        ep_tool = next(t for t in TOOLS if t['name'] == 'list_api_endpoints')
        desc = ep_tool['description'].lower()
        assert 'django' in desc or 'framework' in desc

    def test_ask_codebase_mentions_effort_levels(self):
        ask_tool = next(t for t in TOOLS if t['name'] == 'ask_codebase')
        desc = ask_tool['description'].lower()
        assert 'low' in desc
        assert 'medium' in desc
        assert 'high' in desc

    def test_search_codebase_examples(self):
        search_tool = next(t for t in TOOLS if t['name'] == 'search_codebase')
        desc = search_tool['description'].lower()
        assert 'example' in desc or 'auth' in desc

    def test_list_projects_description(self):
        proj_tool = next(
            (t for t in TOOLS if t['name'] == 'list_projects'),
            None
        )
        if proj_tool:
            desc = proj_tool['description'].lower()
            assert 'project' in desc.lower()


class TestMCPPropertyConsistency:
    """Check consistency across tool properties."""

    def test_all_project_tools_have_slug_parameter(self):
        project_tools = [
            'search_codebase', 'get_function', 'get_class',
            'list_api_endpoints', 'list_models', 'ask_codebase',
            'get_project_stats', 'list_files',
        ]
        for tool_name in project_tools:
            tool = next((t for t in TOOLS if t['name'] == tool_name), None)
            if tool:
                props = tool['inputSchema']['properties']
                assert 'project_slug' in props

    def test_all_required_fields_documented(self):
        for tool in TOOLS:
            schema = tool['inputSchema']
            for req_field in schema.get('required', []):
                prop = schema['properties'].get(req_field)
                assert prop is not None
                if prop:
                    assert 'description' in prop or 'type' in prop

    def test_tool_input_schemas_well_formed(self):
        for tool in TOOLS:
            schema = tool['inputSchema']
            assert schema['type'] == 'object'
            assert isinstance(schema['properties'], dict)
            assert isinstance(schema.get('required', []), list)
            for key, value in schema['properties'].items():
                assert isinstance(value, dict)
                assert 'type' in value or 'enum' in value


class TestMCPServerProtocol:
    """Test MCP JSON-RPC protocol handling if server available."""

    def test_tools_list_completeness(self):
        """Verify we have all critical MCP tools."""
        required_tools = {
            'search_codebase',
            'get_function',
            'list_api_endpoints',
            'ask_codebase',
            'get_project_stats',
            'list_files',
        }
        available = {t['name'] for t in TOOLS}
        assert required_tools.issubset(available), (
            f"Missing tools: {required_tools - available}"
        )

    def test_tool_descriptions_length(self):
        """Tool descriptions should be substantial."""
        for tool in TOOLS:
            desc = tool['description']
            assert len(desc) > 50, f"Description too short for {tool['name']}"
