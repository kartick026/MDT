"""Contract extraction and immutable-source caching against real syntax/HTTP."""
from unittest.mock import AsyncMock

import httpx
import pytest

from services.git_analyzer import GitAnalyzer, GitHubAPIClient, GitHubRateLimitError, extract_route_signatures
from services.source_parser import parse_js_ts, semantic_comparison
from services.impact_engine import ImpactEngine
from services.repo_onboarding import RepoOnboarder


def test_typescript_syntax_ignores_comments_strings_and_reads_real_declarations():
    source = '''
import express from "express";
import type { Request } from "express";
import "./instrumentation";
// function fake() {} app.get('/comment', handler)
const example = "router.post('/quoted', handler)";
export const handler = async (req: Request): Promise<void> => {};
export function* items<T>(values: T[]) { yield* values; }
const api = express.Router();
api.route("/users").get(handler).post(handler);
api.delete(`/users/:id`, handler);
const lazy = import("./lazy");
export { handler as getHandler };
'''
    result = parse_js_ts(source, "typescript")
    assert result["parser_coverage"] == "tree_sitter"
    assert result["functions"] == ["handler", "items"]
    assert result["imports"] == ["express", "./instrumentation", "./lazy"]
    assert result["exports"] == ["handler", "items", "getHandler"]
    assert {(r["method"], r["path"]) for r in result["routes"]} == {
        ("GET", "/users"), ("POST", "/users"), ("DELETE", "/users/:id")}


@pytest.mark.parametrize('language', ['javascript', 'typescript'])
def test_jsx_ampersand_attributes_are_literal_not_call_evidence(language):
    source = '''export const Page = () => <a href="/search?a=1&b=2" data-example="app.get(unknown, handler)">Link</a>;
app.get('/real', handler);'''
    parsed = parse_js_ts(source, language)
    assert parsed['parser_coverage'] == 'tree_sitter'
    assert [r['path'] for r in parsed['routes']] == ['/real']
    assert semantic_comparison(source, '// comment\n' + source, language)['semantic_status'] == 'equivalent'
    assert semantic_comparison(source, source.replace('a=1', 'a=2'), language)['semantic_status'] == 'changed'


@pytest.mark.parametrize('source', [
    'const p = <a href="/x?a=1&b=2"/>; const invalid = ( => {};',
    'const p = <a href="/x?a=1&b=2 />;',
    'const p = <a href={a & }/>;',
    # This grammar loses the entire attribute boundary; do not broaden recovery.
    '''const p = <a href="/x?a=1&app.get('/fake', handler)"/>;''',
])
def test_jsx_attribute_recovery_rejects_unrelated_and_unterminated_errors(source):
    assert parse_js_ts(source, 'typescript')['parser_coverage'] == 'failed'


@pytest.mark.parametrize('header', ['except ValueError, TypeError:', 'except* errors.ValueError, TypeError:'])
def test_python_new_exception_syntax_preserves_semantics_routes_and_source_positions(header):
    from services.source_parser import parse_python
    import ast
    source = '@app.get("/items")\ndef items():\n    try:\n        run()\n    ' + header + '\n        pass\n'
    tree = parse_python(source)
    handler = next(n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler))
    assert ast.get_source_segment(source, handler.type.elts[0]) in {'ValueError', 'errors.ValueError'}
    assert semantic_comparison(source, '# comment\n' + source, 'python')['semantic_status'] == 'equivalent'
    change = GitAnalyzer()._build_change('app.py', 'modified', source, source.replace('/items', '/orders'))
    assert change.parser_coverage == 'ast'
    assert change.ast_metadata['contract_changes']['added'][0]['path'] == '/orders'


@pytest.mark.parametrize('header', ['except ValueError, TypeError as exc:', 'except ValueError,:', 'except ValueError,, TypeError:'])
def test_python_exception_compatibility_rejects_invalid_headers(header):
    import sys
    if sys.version_info >= (3, 14) and header == 'except ValueError,:':
        pytest.skip("Python 3.14+ natively accepts trailing comma in except clause (PEP 758)")
    from services.source_parser import parse_python
    with pytest.raises(SyntaxError):
        parse_python('try:\n    pass\n' + header + '\n    pass\n')


def test_tsx_and_single_argument_arrow_are_parsed():
    result = parse_js_ts('export const Page = (props: Props) => <main>{props.name}</main>; const id = x => x;', "typescript")
    assert result["parser_coverage"] == "tree_sitter"
    assert result["functions"] == ["Page", "id"]


@pytest.mark.parametrize("source", [
    "const Button = styled.button<{ $type?: 'primary' | 'link' }>`color: ${({ $type }) => $type};`;",
    "export const Item = styled.div<{ $fullWidth?: boolean }>`width: ${({ $fullWidth }) => $fullWidth ? '100%' : 'auto'};`;",
    "const view = tag<{ value: string }, number>`value: ${value}`;",
    "const view = tag<{ value: string }> /* a comment */ `value: ${value}`;",
    "const Button = styled.button<{ $type?: string }>`color: red`; export const Page = () => <Button />;",
])
def test_typescript_generic_tagged_templates_keep_supported_syntax_and_diagnostics(source):
    result = parse_js_ts(source, "typescript")
    assert result["parser_coverage"] == "tree_sitter"
    assert result["parser_compatibility"] == ["typescript_generic_tagged_template"]
    assert not result["parser_warnings"]
    assert result["contract_coverage"] == "literal_method_path_only"
    comparison = semantic_comparison(source, "// comment only\n" + source, "typescript")
    assert comparison["semantic_status"] == "equivalent"


def test_tagged_template_compatibility_preserves_route_lines_and_ignores_template_contents():
    source = '''import styled from "styled-components";
// Non-ASCII bytes before the supported grammar gap: café.
export const Button = styled.button<{ $active?: boolean }>`
  app.get('/not-a-route', handler);
  ${({ $active }) => $active ? 'block' : 'none'}
`;
app.get('/actual-route', handler);
'''
    result = parse_js_ts(source, "typescript")
    assert result["parser_coverage"] == "tree_sitter"
    assert result["imports"] == ["styled-components"]
    assert result["exports"] == ["Button"]
    assert result["routes"] == [{"method": "GET", "path": "/actual-route", "line": 7,
                                  "coverage": "syntax_literal_method_path"}]


def test_unrecognized_nested_tagged_template_grammar_error_remains_unknown():
    # The grammar emits an ERROR subtree for this valid, more complex form.
    # The narrow compatibility path must not reinterpret arbitrary ERROR nodes.
    source = "const view = tag<{ value: string }>`outer ${other<{ ready: boolean }>`inner`}`;"
    assert parse_js_ts(source, "typescript")["parser_coverage"] == "failed"
    assert semantic_comparison(source, source, "typescript")["semantic_status"] == "unknown"


@pytest.mark.parametrize("suffix", [
    "const invalid = ( => {};",  # A separate malformed declaration.
    "const invalid = styled.div<{ x?: }>`value`;",  # Missing type.
    "const invalid = styled.div<{ x?: boolean }>`value ${}`;",  # Missing expression.
    "const invalid = styled.div<{ x?: boolean }>`unterminated;",  # Missing closing template.
    "const invalid = styled?.div<{ x?: boolean }>`value`;",  # Invalid optional-chain tag.
    "const invalid = styled.div<{ x?: boolean }>(;",  # Missing ordinary call arguments.
])
def test_tagged_template_compatibility_does_not_accept_other_missing_or_invalid_syntax(suffix):
    source = "const valid = styled.div<{ x?: boolean }>`value`;\n" + suffix
    result = parse_js_ts(source, "typescript")
    assert result["parser_coverage"] == "failed"
    assert result["parser_warnings"] == ["source_parse_failed"]
    assert result["parser_compatibility"] == []
    assert semantic_comparison(source, source, "typescript")["semantic_status"] == "unknown"


@pytest.mark.parametrize("after", [
    "const value = tag<{ active?: string }>`color: red ${color}`;",
    "const value = tag<{ active?: boolean }>`color: blue ${color}`;",
    "const value = tag<{ active?: boolean }>`color: red ${other}`;",
    "const value = other<{ active?: boolean }>`color: red ${color}`;",
])
def test_tagged_template_changes_retain_conservative_semantic_comparison(after):
    before = "const value = tag<{ active?: boolean }>`color: red ${color}`;"
    assert semantic_comparison(before, after, "typescript")["semantic_status"] == "changed"


def test_tagged_template_compatibility_remains_bounded(monkeypatch):
    source = "const value = tag<{ active?: boolean }>`value`;"
    monkeypatch.setattr("services.source_parser.MAX_SYNTAX_NODES", 10)
    result = parse_js_ts(source, "typescript")
    assert result["parser_coverage"] != "tree_sitter"
    assert "syntax_node_limit_reached" in result["parser_warnings"]
    assert result["parser_compatibility"] == []
    assert semantic_comparison(source, source, "typescript")["semantic_status"] == "unknown"
    oversized = source + " " * (256 * 1024)
    assert parse_js_ts(oversized, "typescript")["parser_warnings"] == ["source_exceeds_parser_limit"]


def test_invalid_javascript_and_dynamic_routes_are_explicitly_partial():
    change = GitAnalyzer()._build_change("app.ts", "modified", "", 'const broken = ( => {')
    assert change.parser_coverage == "failed"
    assert "new_source_parse_failed" in change.extraction_warnings
    dynamic = GitAnalyzer()._build_change("app.mjs", "modified", "", 'app.get(`/users/${id}`, handler); app.use("/api", router);')
    assert dynamic.ast_metadata["routes"] == []
    assert dynamic.extraction_status == "partial"
    assert "new_dynamic_route_path_not_resolved" in dynamic.extraction_warnings
    assert "new_router_mount_prefixes_not_resolved" in dynamic.extraction_warnings


def test_python_same_path_contract_changes_include_model_fields_and_requiredness():
    before = '''
class Order(BaseModel):
    amount: int
    note: str = "private default"
@app.post("/orders", response_model=Order, status_code=201)
def create(order: Order, limit: int = 10):
    return order
'''
    after = before.replace('amount: int', 'amount: float').replace('limit: int = 10', 'limit: int')
    change = GitAnalyzer()._build_change("main.py", "modified", before, after)
    contracts = change.ast_metadata["contract_changes"]
    assert not contracts["added"] and not contracts["removed"]
    assert len(contracts["modified"]) == 1
    assert contracts["modified"][0]["after"]["parameters"][1]["required"]
    assert contracts["modified"][0]["after"]["request_schema"]["Order"]["fields"][0]["annotation"] == "float"
    assert "private default" not in str(contracts)
    assert ImpactEngine()._has_api_changes([change])


def test_contracts_ignore_line_comments_and_implementation_only_changes():
    before = '@app.get("/orders")\ndef orders(limit: int = 10) -> list[str]:\n    return []\n'
    after = '# comment\n' + before.replace('return []', 'return ["done"]')
    contracts = GitAnalyzer()._build_change("main.py", "modified", before, after).ast_metadata["contract_changes"]
    assert not contracts["modified"]
    changed_default = before.replace('= 10', '= 20')
    assert GitAnalyzer()._build_change("main.py", "modified", before, changed_default).ast_metadata["contract_changes"]["modified"]


def test_fastapi_field_and_query_required_flags_and_multiple_methods():
    routes = extract_route_signatures('''
class Payload(BaseModel):
    required: str = Field(...)
    optional: str = Field(default="hidden")
@app.api_route("/items", methods=["GET", "POST"])
def handler(payload: Payload, query: str = Query(...), limit: int = Query(10)):
    pass
''')
    assert {r["method"] for r in routes} == {"GET", "POST"}
    assert [p["required"] for p in routes[0]["parameters"]] == [True, True, False]
    assert [p["required"] for p in routes[0]["request_schema"]["Payload"]["fields"]] == [True, False]


@pytest.mark.asyncio
async def test_cache_reuses_only_exact_full_shas_not_moving_refs(httpx_mock):
    client = GitHubAPIClient(token="test-token")
    for body in ("first", "second", "branch old", "branch new"):
        httpx_mock.add_response(text=body)
    assert await client.get_file_content("Owner", "Repo", "app.py", "a" * 40) == "first"
    assert await client.get_file_content("owner", "repo", "app.py", "A" * 40) == "first"
    assert await client.get_file_content("owner", "repo", "app.py", "b" * 40) == "second"
    assert await client.get_file_content("owner", "repo", "app.py", "main") == "branch old"
    assert await client.get_file_content("owner", "repo", "app.py", "main") == "branch new"
    assert len(httpx_mock.get_requests()) == 4


@pytest.mark.asyncio
async def test_cache_is_isolated_per_client_credentials_repo_and_path(httpx_mock):
    first = GitHubAPIClient(token="first")
    second = GitHubAPIClient(token="second")
    for body in ("private-one", "private-two", "other-path", "other-repo", "rotated"):
        httpx_mock.add_response(text=body)
    args = ("owner", "repo", "app.py", "a" * 40)
    assert await first.get_file_content(*args) == "private-one"
    assert await second.get_file_content(*args) == "private-two"
    assert await first.get_file_content("owner", "repo", "other.py", "a" * 40) == "other-path"
    assert await first.get_file_content("owner", "other", "app.py", "a" * 40) == "other-repo"
    first._headers["Authorization"] = "Bearer rotated"
    assert await first.get_file_content(*args) == "rotated"
    assert len(first._source_cache) == 1


@pytest.mark.asyncio
async def test_cache_byte_bound_evicts_least_recently_used(httpx_mock, monkeypatch):
    monkeypatch.setattr("services.git_analyzer.MAX_CACHE_BYTES", 8)
    client = GitHubAPIClient(token="test")
    for body in ("aaaa", "bbbb", "cccc", "bbbb"):
        httpx_mock.add_response(text=body)
    await client.get_file_content("o", "r", "a.py", "a" * 40)
    await client.get_file_content("o", "r", "b.py", "a" * 40)
    await client.get_file_content("o", "r", "a.py", "a" * 40)
    await client.get_file_content("o", "r", "c.py", "a" * 40)
    assert client._cache_bytes == 8
    assert await client.get_file_content("o", "r", "b.py", "a" * 40) == "bbbb"
    assert len(httpx_mock.get_requests()) == 4


@pytest.mark.asyncio
async def test_rate_limit_stops_network_retries_and_retains_safe_evidence(httpx_mock, monkeypatch):
    monkeypatch.setattr("services.git_analyzer.time.time", lambda: 1000)
    client = GitHubAPIClient(token="secret")
    httpx_mock.add_response(text="cached")
    httpx_mock.add_response(status_code=403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1120"})
    await client.get_file_content("o", "r", "cached.py", "a" * 40)
    for path in ("one.py", "two.py"):
        with pytest.raises(GitHubRateLimitError) as error:
            await client.get_file_content("o", "r", path, "a" * 40)
        assert error.value.retry_after_seconds == 120
        assert error.value.evidence == "github_rate_limit:retry_after_seconds=120"
    assert await client.get_file_content("o", "r", "cached.py", "a" * 40) == "cached"
    assert len(httpx_mock.get_requests()) == 2


@pytest.mark.asyncio
async def test_forbidden_is_not_confused_with_rate_limit_or_cached(httpx_mock):
    client = GitHubAPIClient(token="test")
    httpx_mock.add_response(status_code=403)
    httpx_mock.add_response(text="available")
    with pytest.raises(ValueError, match="HTTP 403") as error:
        await client.get_file_content("o", "r", "a.py", "a" * 40)
    assert not isinstance(error.value, GitHubRateLimitError)
    assert await client.get_file_content("o", "r", "a.py", "a" * 40) == "available"


@pytest.mark.asyncio
async def test_onboarding_retains_parser_and_rate_limit_coverage():
    content = AsyncMock(side_effect=['export const Item = (p: Props) => <div/>;', GitHubRateLimitError(60)])
    result, coverage = await RepoOnboarder()._collect_service_sources([{"name": "api"}], {"src": "api"},
        ["src/a.tsx", "src/b.ts"], content)
    assert list(result["api"]) == ["src/a.tsx"]
    assert coverage["parsers"] == {"tree_sitter": 1}
    assert coverage["warnings"] == ["github_rate_limit:retry_after_seconds=60:src/b.ts"]
