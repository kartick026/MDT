"""Bounded literal Aspire AppHost discovery; C# is read, never compiled or run.

Only top-level fluent declarations are interpreted. Helpers, loops, conditionals,
interpolation and generated resources remain unresolved. This is topology evidence,
not API-contract coverage or a claim about the selected runtime environment.
"""
import json
import posixpath
import re

MAX_BYTES = 256 * 1024
TOKEN = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|@"(?:""|[^"])*"|"(?:\\.|[^"\\])*"|[^/"@]+|.', re.S)
IDENT = r"[A-Za-z_][A-Za-z_0-9]*"


def _statements(source):
    # Strings stay indivisible, so braces/semicolons/comment markers inside them
    # cannot escape their expression into a fake declaration.
    text = "".join("\n" * token.count("\n") if token.startswith(("//", "/*")) else token
                   for token in TOKEN.findall(source))
    pieces, current, parens, block = [], [], 0, 0
    for token in re.findall(r'@"(?:""|[^"])*"|"(?:\\.|[^"\\])*"|.', text, re.S):
        if len(token) > 1:
            if not block:
                current.append(token)
            continue
        if block:
            if token == "{": block += 1
            if token == "}": block -= 1
            continue
        if token == "{" and parens == 0:
            block = 1
            current = []
            continue
        if token == "(": parens += 1
        if token == ")": parens = max(0, parens - 1)
        if token == ";" and parens == 0:
            pieces.append("".join(current).strip())
            current = []
        else:
            current.append(token)
    return pieces


def _arguments(text, start):
    depth, current, result = 1, [], []
    for match in re.finditer(r'@"(?:""|[^"])*"|"(?:\\.|[^"\\])*"|.', text[start:], re.S):
        token = match.group()
        if token in {"(", "[", "{"}: depth += 1
        elif token in {")", "]", "}"}:
            depth -= 1
            if depth == 0:
                result.append("".join(current).strip())
                return result, start + match.end()
        if token == "," and depth == 1:
            result.append("".join(current).strip())
            current = []
        else:
            current.append(token)
    return [], len(text)


def _calls(text):
    result, offset = [], 0
    while match := re.search(r'\.(' + IDENT + r')(?:<([^<>]+)>)?\s*\(', text[offset:]):
        args, end = _arguments(text, offset + match.end())
        result.append((match[1], match[2], args))
        offset = end
    return result


def _literal(value):
    if not isinstance(value, str) or not re.fullmatch(r'"(?:\\.|[^"\\])*"', value):
        return None
    try:
        return json.loads(value)
    except ValueError:
        return None


async def discover_aspire(tree, get_content):
    candidates = sorted(path for path in tree if posixpath.basename(path) in {"AppHost.cs", "Program.cs"}
                        and any(part.lower().endswith("apphost") for part in path.split("/")[:-1])
                        and not set(path.lower().split("/")) & {"test", "tests", "examples", "samples", "obj", "bin"})
    meta = {"sources": [], "warnings": [], "selected_manifest_files": candidates[:1]}
    if not candidates:
        return [], [], {}, meta
    if len(candidates) != 1:
        meta["warnings"].append("aspire_multiple_apphosts_require_selection")
        return [], [], {}, meta
    path = candidates[0]
    source = await get_content(path)
    if len(source.encode()) > MAX_BYTES:
        meta["warnings"].append("aspire_source_size_limit")
        return [], [], {}, meta
    statements = _statements(source)
    builders = {match[1] for statement in statements if (match := re.fullmatch(
        r'var\s+(' + IDENT + r')\s*=\s*DistributedApplication\.CreateBuilder\([^;]*\)', statement))}
    if len(builders) != 1:
        meta["warnings"].append("aspire_builder_unresolved")
        return [], [], {}, meta
    builder = next(iter(builders))
    services, edges, mappings, variables, endpoint_aliases, chains = [], [], {}, {}, {}, []
    node_types = {"AddRedis": "database", "AddPostgres": "database", "AddSqlServer": "database",
                  "AddMySql": "database", "AddMongoDB": "database", "AddRabbitMQ": "broker",
                  "AddKafka": "broker", "AddDatabase": "database", "AddYarp": "service",
                  "AddProject": "service", "AddDotnetProject": "service"}
    for statement in statements:
        match = re.match(r'(?:(?:var|' + IDENT + r')\s+(' + IDENT + r')\s*=\s*)?(' + IDENT + r')(\..*)$', statement, re.S)
        if not match:
            continue
        variable, receiver, tail = match.groups()
        calls = _calls(tail)
        if not calls:
            continue
        method, generic, args = calls[0]
        if method == "GetEndpoint" and receiver in variables and variable:
            endpoint_aliases[variable] = variables[receiver]
            continue
        if method not in node_types or (receiver != builder and method != "AddDatabase"):
            if receiver in variables:
                chains.append((variables[receiver], calls))
            continue
        if method == "AddDatabase" and receiver not in variables:
            continue
        name = _literal(args[0]) if args else None
        if not name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
            meta["warnings"].append("aspire_resource_name_unresolved")
            continue
        if any(node["name"] == name for node in services):
            meta["warnings"].append("aspire_duplicate_resource:" + name)
            continue
        prefix = None
        if method in {"AddDotnetProject", "AddProject"}:
            relative = _literal(args[1]) if len(args) > 1 else None
            if relative:
                normalized = posixpath.normpath(posixpath.join(posixpath.dirname(path), relative.replace("\\", "/")))
                if not normalized.startswith(("../", "/")) and ":" not in normalized:
                    if normalized.endswith(".csproj"):
                        normalized = posixpath.dirname(normalized)
                    if any(file.startswith(normalized + "/") and file.endswith(".csproj") for file in tree):
                        prefix = normalized
            elif generic and generic.startswith("Projects."):
                matches = [posixpath.dirname(file) for file in tree if file.endswith(".csproj")
                           and re.sub(r'[^A-Za-z0-9_]', '_', posixpath.basename(file)[:-7]) == generic[9:]]
                if len(matches) == 1:
                    prefix = matches[0]
            if prefix is None:
                meta["warnings"].append("aspire_project_source_unresolved:" + name)
        if prefix:
            mappings[prefix] = name
        services.append({"name": name, "display_name": name, "node_type": node_types[method],
                         "language": "csharp" if method in {"AddProject", "AddDotnetProject"} else "unknown",
                         "source_expected": bool(prefix), "discovery_kind": "aspire", "source_file": path,
                         "port": None, "description": "Literal Aspire resource declaration"})
        if variable:
            variables[variable] = name
        chains.append((name, calls[1:]))
    seen = set()
    for name, calls in chains:
        for method, _, args in calls:
            if method in {"WithReference", "WaitFor", "WaitForCompletion"} and args:
                target = variables.get(args[0])
                kind = "aspire_reference" if method == "WithReference" else "aspire_wait_for"
                edge_type = "declared" if method == "WithReference" else "startup"
                env = None
            elif method == "WithEnvironment" and len(args) == 2:
                target = endpoint_aliases.get(args[1])
                endpoint = re.fullmatch(r'(' + IDENT + r')\.GetEndpoint\([^;]*\)', args[1])
                if endpoint:
                    target = variables.get(endpoint[1])
                kind, edge_type, env = "aspire_endpoint_reference", "declared", _literal(args[0])
            else:
                continue
            if not target or target == name or (name, target, kind, env) in seen:
                continue
            seen.add((name, target, kind, env))
            edge = {"from": name, "to": target, "type": edge_type, "endpoint": "",
                    "evidence_kind": kind, "source_file": path}
            if env:
                edge["environment_variable"] = env
            edges.append(edge)
    meta["sources"] = ["aspire"] if services else []
    meta["warnings"].extend(["aspire_literal_topology_only_helpers_and_conditionals_unresolved",
                             "aspire_references_are_configuration_not_runtime_calls", "csharp_contracts_unresolved"])
    return services, edges, mappings, meta
