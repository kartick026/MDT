"""Bounded JS/TS syntax extraction, without executing repository code.

This identifies declarations and literal Express-style method/path calls. It does
not resolve middleware, router mount prefixes, generated routes or OpenAPI schemas.
"""
import ast
import hashlib
import json
import re
import posixpath
import io
import tokenize
from functools import lru_cache

from tree_sitter import Language, Parser
import tree_sitter_javascript
import tree_sitter_typescript


MAX_SYNTAX_NODES = 50000
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def parse_python(content):
    """Bounded AST with a narrow PEP 758 bridge for older Python runtimes.

    Only simple comma-separated exception names without an ``as`` clause are
    normalized. Source is never executed or changed in the stored snapshot.
    Other new syntax and malformed headers remain errors. Restore AST columns
    after inserting the equivalent tuple parentheses; line numbers never move.
    """
    if len(content.encode('utf-8')) > 256 * 1024:
        raise ValueError('source_exceeds_parser_limit')
    compatibility = []
    try:
        tree = ast.parse(content)
    except SyntaxError as original:
        try:
            tokens = list(tokenize.generate_tokens(io.StringIO(content).readline))
        except (tokenize.TokenError, IndentationError):
            raise original
        if len(tokens) > MAX_SYNTAX_NODES:
            raise ValueError('syntax_node_limit_reached')
        lines = content.splitlines(keepends=True)
        edits = {}
        for i, token in enumerate(tokens):
            if token.type != tokenize.NAME or token.string != 'except':
                continue
            header = []
            for part in tokens[i + 1:]:
                if part.start[0] != token.start[0] or part.type in {tokenize.NEWLINE, tokenize.COMMENT}:
                    break
                if part.string == ':':
                    break
                header.append(part)
            else:
                continue
            if part.string != ':' or not header:
                continue
            if header[0].string == '*':
                header = header[1:]
            expression = ''.join(t.string for t in header)
            # Do not accept Python 2's ``except Error, error as value`` or
            # expressions whose precedence needs the newer grammar to resolve.
            name = r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*'
            if not re.fullmatch(rf'{name}(?:,{name})+', expression):
                continue
            if any(t.type == tokenize.NAME and t.string in {'as', 'lambda', 'if', 'else'} for t in header):
                continue
            row = token.start[0] - 1
            edits.setdefault(row, []).extend([(header[0].start[1], '('), (part.start[1], ')')])
        if not edits:
            raise original
        normalized = list(lines)
        positions = {}
        for row, inserts in edits.items():
            positions[row + 1] = [len(lines[row][:col].encode('utf-8')) + n
                                  for n, (col, _) in enumerate(sorted(inserts))]
            for col, value in sorted(inserts, reverse=True):
                normalized[row] = normalized[row][:col] + value + normalized[row][col:]
        tree = ast.parse(''.join(normalized))  # Still reject every unrelated syntax error.
        for node in ast.walk(tree):
            for line_attr, col_attr in [('lineno', 'col_offset'), ('end_lineno', 'end_col_offset')]:
                row, col = getattr(node, line_attr, None), getattr(node, col_attr, None)
                if row in positions and col is not None:
                    setattr(node, col_attr, col - sum(p < col for p in positions[row]))
        compatibility = ['python_unparenthesized_except']
    if sum(1 for _ in ast.walk(tree)) > MAX_SYNTAX_NODES:
        raise ValueError('syntax_node_limit_reached')
    tree.mdt_compatibility = compatibility
    return tree


def semantic_comparison(before, after, language, *, complete=True, structural_change=False):
    """Prove syntax equivalence; missing/invalid/unsupported evidence never means safe.

    This compares static semantics, not runtime behavior or deployment safety.
    Python comments/positions and JS trivia are excluded; strings remain intact.
    """
    result = {"semantic_change": None, "semantic_status": "unknown", "semantic_evidence": "unavailable"}
    if not complete or max(len(before.encode()), len(after.encode())) > 256 * 1024:
        return result
    try:
        if language == "python":
            def fingerprint(source):
                tree = parse_python(source)
                if sum(1 for _ in ast.walk(tree)) > MAX_SYNTAX_NODES:
                    raise ValueError("syntax_node_limit")
                return ast.dump(tree, include_attributes=False)
            evidence = "python_ast"
        elif language in {"javascript", "typescript"}:
            def fingerprint(source):
                encoded = source.encode()
                tree, _, _, syntax_supported = _parse_js_ts_tree(encoded, language)
                if not syntax_supported:
                    raise ValueError("invalid_syntax")
                pending, parts, count = [tree.root_node], [], 0
                while pending:
                    node = pending.pop()
                    count += 1
                    if count > MAX_SYNTAX_NODES:
                        raise ValueError("syntax_node_limit")
                    if node.type == "comment":
                        continue
                    parts.append(node.type)
                    if node.children:
                        pending.extend(reversed(node.children))
                    else:
                        parts.append(encoded[node.start_byte:node.end_byte])
                return parts
            evidence = "tree_sitter"
        elif language == "json":
            def fingerprint(source):
                def unique_pairs(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            raise ValueError("duplicate_json_key")
                        result[key] = value
                    return result
                parsed = json.loads(source, object_pairs_hook=unique_pairs)
                return json.dumps(parsed, sort_keys=True, allow_nan=False)
            evidence = "json_values"
        elif language == "yaml":
            import yaml
            # Compare representation trees, without constructing aliases/objects.
            # Anchor/alias/config-expression changes remain conservatively changed.
            def fingerprint(source):
                events = list(yaml.parse(source, Loader=yaml.SafeLoader))
                if len(events) > MAX_SYNTAX_NODES:
                    raise ValueError("syntax_node_limit")
                return [(type(e).__name__, getattr(e, "value", None), getattr(e, "tag", None),
                         getattr(e, "anchor", None), getattr(e, "implicit", None)) for e in events]
            evidence = "yaml_syntax"
        elif language == "toml":
            import tomllib
            def fingerprint(source):
                def typed(value):
                    if isinstance(value, dict):
                        return [(key, typed(value[key])) for key in sorted(value)]
                    if isinstance(value, list):
                        return [typed(v) for v in value]
                    return type(value).__name__, repr(value)
                return typed(tomllib.loads(source))
            evidence = "toml_values"
        else:
            if before == after and not structural_change:
                return {"semantic_change": False, "semantic_status": "equivalent", "semantic_evidence": "identical_source"}
            return result
        changed = fingerprint(before) != fingerprint(after) or structural_change
        return {"semantic_change": changed, "semantic_status": "changed" if changed else "equivalent", "semantic_evidence": evidence}
    except (ValueError, SyntaxError, RecursionError, TypeError):
        return result
    except Exception:
        # Parser-specific exceptions (e.g. YAML) are unavailable evidence.
        return result


class PythonModelContext:
    """Resolve bounded supplied Python snapshots only; never import repository code."""

    def __init__(self, sources):
        self.trees, self.classes, self.imports, self.modules, self.cache = {}, {}, {}, {}, {}
        total = 0
        for path, source in sorted(sources.items())[:100]:
            if not path.endswith(".py") or len(source.encode()) > 256 * 1024:
                continue
            total += len(source.encode())
            if total > 2 * 1024 * 1024:
                break
            try:
                tree = parse_python(source)
                if sum(1 for _ in ast.walk(tree)) > MAX_SYNTAX_NODES:
                    continue
            except (SyntaxError, ValueError, RecursionError):
                continue
            self.trees[path] = tree
            self.modules[path] = path.removesuffix(".py").removesuffix("/__init__").replace("/", ".")
            self.classes[path] = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
            imports = {}
            for node in tree.body:
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if node.level:
                        package = posixpath.dirname(path).split("/")
                        package = package[:len(package) - node.level + 1]
                        module = ".".join(package + ([module] if module else []))
                    imports.update({a.asname or a.name: (module, a.name) for a in node.names if a.name != "*"})
                elif isinstance(node, ast.Import):
                    imports.update({a.asname or a.name: (a.name, None) for a in node.names})
            self.imports[path] = imports

    def target(self, path, name):
        if name in self.classes.get(path, {}):
            return path, name
        root, _, tail = name.partition(".")
        imported = self.imports.get(path, {}).get(root)
        if not imported:
            return None
        module, member = imported
        if member is None:
            if not tail:
                return None
            module, _, member = (module + "." + tail).rpartition(".")
        elif tail:
            module, member = module + "." + member, tail
        candidates = [p for p, m in self.modules.items() if (m == module or m.endswith("." + module))
                      and member in self.classes[p]]
        return (candidates[0], member) if len(candidates) == 1 else None

    def model(self, path, name, stack=()):
        target = self.target(path, name)
        if not target or target in stack or len(stack) >= 12:
            return None
        if target in self.cache:
            return self.cache[target]
        model_path, model_name = target
        node = self.classes[model_path][model_name]
        fields, unresolved, recognized = {}, [], False
        for base in node.bases:
            base_name = _annotation(base)
            imported = self.imports.get(model_path, {}).get(base_name)
            canonical = ".".join(p for p in imported if p) if imported else base_name
            if canonical in {"BaseModel", "SQLModel", "pydantic.BaseModel", "sqlmodel.SQLModel"}:
                recognized = True
                continue
            parent = self.model(model_path, base_name, stack + (target,))
            if parent:
                fields.update({f["name"]: f for f in parent["fields"]})
                recognized |= parent["recognized_model"]
                unresolved.extend(parent["unresolved_bases"])
            elif base_name not in {"object"}:
                unresolved.append(base_name)
        for child in node.body:
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                fields[child.target.id] = {"name": child.target.id, "annotation": _annotation(child.annotation),
                    "source_path": model_path, **_default_contract(child.value)}
        result = {"fields": list(fields.values()), "bases": [_annotation(b) for b in node.bases],
                  "source_path": model_path, "recognized_model": recognized,
                  "unresolved_bases": sorted(set(unresolved))}
        self.cache[target] = result
        return result

    def schemas(self, path):
        return {name: model for name in self.classes.get(path, {})
                if (model := self.model(path, name)) and model["recognized_model"]}

    def referenced(self, path, annotations):
        names = set()
        for annotation in annotations:
            if annotation:
                names.update(_annotation(n) for n in ast.walk(annotation) if isinstance(n, (ast.Name, ast.Attribute)))
        selected = {}
        for _ in range(12):
            pending = names - selected.keys()
            added = False
            for name in sorted(pending):
                model = self.model(path, name)
                if model:
                    selected[name] = model
                    added = True
                    for field in model["fields"]:
                        names.update(re.findall(r"\b[A-Za-z_]\w*\b", field["annotation"] or ""))
            if not added:
                break
        unresolved = sorted(name for name in names - selected.keys() if name.split(".")[0] in self.imports.get(path, {})
            and not self.imports[path][name.split(".")[0]][0].startswith(("typing", "builtins", "fastapi")))
        return selected, unresolved


def compare_schema_models(before, after, *, direction="request"):
    """Conservative static compatibility evidence, not a full OpenAPI validator."""
    result = {"added": [], "removed": [], "modified": [], "breaking_changes": [],
              "additive_changes": [], "uncertain_changes": [], "coverage": "bounded_python_model_annotations"}
    for name in sorted(before.keys() | after.keys()):
        if name not in after:
            result["removed"].append({"model": name, "before": before[name]})
            result["breaking_changes"].append({"model": name, "reason": "model_removed"})
            continue
        if name not in before:
            result["added"].append({"model": name, "after": after[name]})
            result["additive_changes"].append({"model": name, "reason": "model_added"})
            continue
        old, new = before[name], after[name]
        if old == new:
            continue
        result["modified"].append({"model": name, "before": old, "after": new})
        old_fields = {f["name"]: f for f in old["fields"]}
        new_fields = {f["name"]: f for f in new["fields"]}
        found = False
        for field in sorted(old_fields.keys() | new_fields.keys()):
            a, b = old_fields.get(field), new_fields.get(field)
            if a == b:
                continue
            found = True
            if b is None:
                kind, reason = "breaking", "field_removed"
            elif a is None:
                kind, reason = ("breaking", "required_field_added") if b["required"] else ("additive", "optional_field_added")
            elif a["annotation"] != b["annotation"]:
                kind, reason = "breaking", "field_type_changed"
            elif not a["required"] and b["required"]:
                kind, reason = "breaking", "field_became_required"
            elif a["required"] and not b["required"]:
                kind, reason = "additive", "field_became_optional"
            else:
                kind, reason = "uncertain", "field_default_or_constraints_changed"
            if direction == "response":
                # Request relaxation is not response compatibility: a consumer
                # may rely on fields being present in every returned object.
                if reason == "field_became_optional":
                    kind = "breaking"
                elif reason == "field_became_required":
                    kind = "additive"
                elif reason in {"optional_field_added", "required_field_added"}:
                    kind = "uncertain"
            result[kind + "_changes"].append({"model": name, "field": field, "reason": reason})
        if not found or old.get("unresolved_bases") or new.get("unresolved_bases"):
            result["uncertain_changes"].append({"model": name, "reason": "model_context_or_inheritance_changed"})
    result["compatibility"] = next((kind for kind in ("breaking", "uncertain", "additive") if result[kind + "_changes"]), "unchanged")
    return result


def compare_route_contracts(before, after, language):
    old = {(r["method"], r["path"]): r for r in before}
    new = {(r["method"], r["path"]): r for r in after}
    fields = ("parameters", "request_schema", "response_schema", "status_code")
    result = {"removed": [old[k] for k in sorted(old.keys() - new.keys())],
              "added": [new[k] for k in sorted(new.keys() - old.keys())],
              "modified": [], "breaking_changes": [], "additive_changes": [], "uncertain_changes": [],
              "coverage": "bounded_python_annotations" if language == "python" else "literal_method_path_only"}
    result["breaking_changes"] = [{"method": r["method"], "path": r["path"], "reason": "route_removed"} for r in result["removed"]]
    result["additive_changes"] = [{"method": r["method"], "path": r["path"], "reason": "route_added"} for r in result["added"]]
    for key in sorted(old.keys() & new.keys()):
        a, b = old[key], new[key]
        if not any(a.get(f) != b.get(f) for f in fields):
            continue
        result["modified"].append({"method": key[0], "path": key[1], "before": a, "after": b})
        comparisons = [compare_schema_models(a.get("request_schema", {}), b.get("request_schema", {})),
            compare_schema_models(a.get("response_schema", {}).get("models", {}), b.get("response_schema", {}).get("models", {}), direction="response"),
            compare_schema_models({"parameters": {"fields": a.get("parameters", [])}},
                                  {"parameters": {"fields": b.get("parameters", [])}})]
        evidence_found = False
        for compared in comparisons:
            for kind in ("breaking", "additive", "uncertain"):
                for evidence in compared[kind + "_changes"]:
                    evidence_found = True
                    result[kind + "_changes"].append({"method": key[0], "path": key[1], **evidence})
        if a.get("response_schema", {}).get("annotation") != b.get("response_schema", {}).get("annotation"):
            evidence_found = True
            result["breaking_changes"].append({"method": key[0], "path": key[1], "reason": "response_type_changed"})
        if a.get("status_code") != b.get("status_code") or not evidence_found:
            result["uncertain_changes"].append({"method": key[0], "path": key[1], "reason": "route_contract_changed"})
    result["compatibility"] = next((kind for kind in ("breaking", "uncertain", "additive") if result[kind + "_changes"]), "unchanged")
    result["unresolved_models"] = sorted({m for route in before + after for m in route.get("unresolved_models", [])})
    return result


def _annotation(node):
    return ast.unparse(node) if node else None


def _default_contract(value):
    """Compare default changes without putting source default values in exports."""
    required = value is None or isinstance(value, ast.Constant) and value.value is Ellipsis
    if isinstance(value, ast.Call):
        call_name = _annotation(value.func).split(".")[-1]
        if call_name in {"Query", "Path", "Body", "Header", "Cookie", "Form", "File", "Field"}:
            default = value.args[0] if value.args else next((k.value for k in value.keywords if k.arg == "default"), None)
            required = default is None or isinstance(default, ast.Constant) and default.value is Ellipsis
            if any(k.arg == "default_factory" for k in value.keywords):
                required = False
    result = {"required": required}
    if value is not None:
        result["default_fingerprint"] = hashlib.sha256(ast.dump(value, include_attributes=False).encode()).hexdigest()
    return result


def extract_python_routes(content, *, file_path="source.py", context=None):
    """Literal Python routes and local annotated handler/model contracts.

    This deliberately avoids runtime imports, evaluating validators or claiming
    fully resolved OpenAPI schemas, inherited fields or mounted router prefixes.
    """
    try:
        tree = parse_python(content)
    except (SyntaxError, ValueError, RecursionError):
        return []
    context = context or PythonModelContext({file_path: content})

    def schema_for(annotations):
        return context.referenced(file_path, annotations)[0]

    declarations = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            declarations.extend((decorator, node) for decorator in node.decorator_list)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_api_route":
            declarations.append((node, None))
    signatures = []
    for node, handler in declarations:
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        verb = node.func.attr.lower()
        if verb not in HTTP_METHODS | {"route", "api_route", "add_api_route"}:
            continue
        path_node = node.args[0] if node.args else next((kw.value for kw in node.keywords if kw.arg == "path"), None)
        if not isinstance(path_node, ast.Constant) or not isinstance(path_node.value, str):
            continue
        methods = [verb.upper()] if verb in HTTP_METHODS else ["GET"]
        method_node = next((kw.value for kw in node.keywords if kw.arg == "methods"), None)
        if isinstance(method_node, (ast.List, ast.Tuple, ast.Set)):
            methods = [entry.value.upper() for entry in method_node.elts if isinstance(entry, ast.Constant)
                       and isinstance(entry.value, str) and entry.value.lower() in HTTP_METHODS]
        details = {"parameters": [], "request_schema": {}, "response_schema": {}}
        if handler:
            positional = handler.args.posonlyargs + handler.args.args
            defaults = [None] * (len(positional) - len(handler.args.defaults)) + list(handler.args.defaults)
            arguments = list(zip(positional, defaults)) + list(zip(handler.args.kwonlyargs, handler.args.kw_defaults))
            details["parameters"] = [{"name": argument.arg, "annotation": _annotation(argument.annotation),
                                      **_default_contract(default)} for argument, default in arguments]
            details["request_schema"] = schema_for([argument.annotation for argument, _ in arguments])
            response_model = next((kw.value for kw in node.keywords if kw.arg == "response_model"), handler.returns)
            details["response_schema"] = {"annotation": _annotation(response_model), "models": schema_for([response_model])}
            referenced, unresolved = context.referenced(file_path,
                [argument.annotation for argument, _ in arguments] + [response_model])
            details["unresolved_models"] = sorted(set(unresolved) | {
                base for model in referenced.values() for base in model.get("unresolved_bases", [])})
        status_code = next((kw.value for kw in node.keywords if kw.arg == "status_code"), None)
        if status_code is not None:
            details["status_code"] = _annotation(status_code)
        for method in methods:
            signatures.append({"method": method, "path": path_node.value, "line": node.lineno,
                               "coverage": "literal_route_and_local_annotations", **details})
    return signatures


@lru_cache(maxsize=3)
def _language(name):
    if name == "javascript":
        return Language(tree_sitter_javascript.language())
    factory = tree_sitter_typescript.language_tsx if name == "tsx" else tree_sitter_typescript.language_typescript
    return Language(factory())


def _generic_template_recovery(node):
    """Recognize one upstream TS grammar gap, never arbitrary missing syntax.

    TypeScript permits tag<Type>`template` (since 2.9), but the pinned grammar
    sometimes recovers it as tag<Type>!`template` with a zero-width missing !.
    See tree-sitter/tree-sitter-typescript#341. Keep the original source/tree:
    inserting or stripping text would lose byte positions and change evidence.
    """
    if not (node.is_missing and node.type == "!" and node.start_byte == node.end_byte):
        return False
    function = node.parent
    if not function or function.type != "non_null_expression":
        return False
    expressions = [child for child in function.named_children if child.type != "comment"]
    if len(expressions) != 1 or expressions[0].type != "instantiation_expression":
        return False
    instantiation = expressions[0]
    type_arguments = instantiation.child_by_field_name("type_arguments")
    if (not type_arguments or type_arguments.has_error
            or instantiation.end_byte > node.start_byte
            or function.end_byte != node.start_byte
            or any(child != instantiation and child != node and child.type != "comment"
                   for child in function.children)):
        return False
    call = function.parent
    if not call or call.type != "call_expression" or call.child_by_field_name("function") != function:
        return False
    template = call.child_by_field_name("arguments")
    if not template or template.type != "template_string" or template.start_byte < node.end_byte:
        return False
    # An unparenthesized optional chain cannot be a tagged-template receiver.
    # Restrict this accommodation to the observed identifier/member tags, with
    # structurally valid type arguments; leave other recovered forms unknown.
    tag = instantiation.named_children[0]
    while tag.type == "member_expression":
        if tag.child_by_field_name("optional_chain") or any(c.type == "optional_chain" for c in tag.children):
            return False
        tag = tag.child_by_field_name("object")
        if tag is None:
            return False
    return tag.type == "identifier" and not instantiation.has_error


def _jsx_attribute_literal(node, encoded):
    if node.type != 'string' or not node.parent or node.parent.type != 'jsx_attribute':
        return False
    raw = encoded[node.start_byte:node.end_byte]
    return len(raw) >= 2 and raw[:1] in {b'"', b"'"} and raw[-1:] == raw[:1] and raw[:1] not in raw[1:-1]


def _supported_js_ts_tree(tree, grammar, encoded):
    """Validate every error-bearing node, within the existing traversal bound."""
    if not tree.root_node.has_error:
        return True, []
    pending, count, recovered = [tree.root_node], 0, set()
    while pending:
        node = pending.pop()
        count += 1
        if count > MAX_SYNTAX_NODES:
            return False, []
        if node.has_error and _jsx_attribute_literal(node, encoded):
            # JSX quoted attributes are literal text, not JS expressions. The
            # pinned grammar incorrectly recovers bare ampersands as code.
            if b'&' not in encoded[node.start_byte:node.end_byte]:
                return False, []
            recovered.add('jsx_quoted_attribute_ampersand')
            continue
        if node.type == "ERROR":
            return False, []
        if node.is_missing:
            if grammar not in {"typescript", "tsx"} or not _generic_template_recovery(node):
                return False, []
            recovered.add('typescript_generic_tagged_template')
        pending.extend(reversed(node.children))
    return bool(recovered), sorted(recovered)


def _parse_js_ts_tree(encoded, language):
    """Share strict parsing and the bounded TS compatibility path with comparison."""
    grammars = ("typescript", "tsx") if language == "typescript" else (language,)
    for grammar in grammars:
        tree = Parser(_language(grammar)).parse(encoded)
        supported, compatibility = _supported_js_ts_tree(tree, grammar, encoded)
        if supported:
            return tree, grammar, compatibility, True
    return tree, grammar, [], False


def parse_js_ts(content, language):
    """Return deterministic metadata plus explicit syntax/coverage limitations."""
    encoded = content.encode("utf-8")
    result = {"language": language, "functions": [], "classes": [], "imports": [],
              "exports": [], "routes": [], "parser_coverage": "tree_sitter",
              "parser_warnings": [], "parser_compatibility": [],
              "contract_coverage": "literal_method_path_only"}
    if len(encoded) > 256 * 1024:
        result.update(parser_coverage="failed", parser_warnings=["source_exceeds_parser_limit"])
        return result
    tree, grammar, compatibility, syntax_supported = _parse_js_ts_tree(encoded, language)
    result["parser_grammar"] = grammar
    result["parser_compatibility"] = compatibility
    if not syntax_supported:
        result["parser_coverage"] = "failed"
        result["parser_warnings"].append("source_parse_failed")

    def text(node):
        return encoded[node.start_byte:node.end_byte].decode("utf-8") if node else ""

    def literal(node):
        if not node or node.type not in {"string", "template_string"}:
            return None
        if node.type == "template_string":
            return text(node)[1:-1] if not any(c.type == "template_substitution" for c in node.named_children) else None
        try:
            value = ast.literal_eval(text(node))
            return value if isinstance(value, str) else None
        except (ValueError, SyntaxError):
            return None

    nodes, pending = [], [tree.root_node]
    while pending and len(nodes) < MAX_SYNTAX_NODES:
        node = pending.pop()
        nodes.append(node)
        if _jsx_attribute_literal(node, encoded):
            continue  # Never extract fake calls from a literal attribute value.
        pending.extend(reversed(node.named_children))
    if pending:
        result["parser_coverage"] = "partial"
        result["parser_warnings"].append("syntax_node_limit_reached")

    # Conventional receivers and locally declared Express/Fastify router aliases.
    receivers = {"app", "router", "server"}
    for node in nodes:
        if node.type != "variable_declarator":
            continue
        value = node.child_by_field_name("value")
        name = node.child_by_field_name("name")
        if value and value.type == "call_expression" and name and name.type == "identifier":
            factory = text(value.child_by_field_name("function"))
            if factory in {"express", "Router", "express.Router", "fastify", "Fastify"}:
                receivers.add(text(name))

    def chained_path(node):
        """Resolve only a local router.route('/literal').get(...).post(...) chain."""
        for _ in range(12):
            if not node or node.type != "call_expression":
                return None
            function = node.child_by_field_name("function")
            if not function or function.type != "member_expression":
                return None
            receiver = function.child_by_field_name("object")
            method = text(function.child_by_field_name("property"))
            if method == "route" and text(receiver) in receivers:
                arguments = node.child_by_field_name("arguments")
                return literal(arguments.named_children[0]) if arguments and arguments.named_children else None
            if method not in HTTP_METHODS:
                return None
            node = receiver
        return None

    for node in nodes:
        if node.type in {"function_declaration", "generator_function_declaration"}:
            result["functions"].append(text(node.child_by_field_name("name")))
        elif node.type == "variable_declarator":
            value = node.child_by_field_name("value")
            if value and value.type in {"arrow_function", "function_expression", "generator_function"}:
                result["functions"].append(text(node.child_by_field_name("name")))
        elif node.type in {"class_declaration", "abstract_class_declaration"}:
            result["classes"].append(text(node.child_by_field_name("name")))
        elif node.type == "import_statement":
            source = literal(node.child_by_field_name("source"))
            if source:
                result["imports"].append(source)
        elif node.type == "export_statement":
            declaration = node.child_by_field_name("declaration")
            source = literal(node.child_by_field_name("source"))
            if source:
                result["imports"].append(source)
            if declaration:
                name = declaration.child_by_field_name("name")
                if name:
                    result["exports"].append(text(name))
                for child in declaration.named_children:
                    if child.type == "variable_declarator":
                        result["exports"].append(text(child.child_by_field_name("name")))
            for child in node.named_children:
                if child.type == "export_clause":
                    for specifier in child.named_children:
                        result["exports"].append(text(specifier.child_by_field_name("alias") or specifier.child_by_field_name("name")))
                elif child.type == "identifier":
                    result["exports"].append(text(child))
        elif node.type == "call_expression":
            function = node.child_by_field_name("function")
            arguments = node.child_by_field_name("arguments")
            args = arguments.named_children if arguments else []
            if text(function) in {"require", "import"} and args:
                source = literal(args[0])
                if source:
                    result["imports"].append(source)
            if not function or function.type != "member_expression":
                continue
            receiver = function.child_by_field_name("object")
            method = text(function.child_by_field_name("property"))
            if method == "use" and text(receiver) in receivers and args and literal(args[0]):
                result["parser_warnings"].append("router_mount_prefixes_not_resolved")
            if method not in HTTP_METHODS:
                continue
            path = literal(args[0]) if text(receiver) in receivers and args else chained_path(receiver)
            if path is not None and path.startswith("/"):
                result["routes"].append({"method": method.upper(), "path": path,
                    "line": node.start_point.row + 1, "coverage": "syntax_literal_method_path"})
            elif text(receiver) in receivers:
                result["parser_warnings"].append("dynamic_route_path_not_resolved")

    for key in ("functions", "classes", "imports", "exports", "parser_warnings"):
        result[key] = list(dict.fromkeys(value for value in result[key] if value))
    result["routes"] = list({(r["method"], r["path"], r["line"]): r for r in result["routes"]}.values())
    return result
