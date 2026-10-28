"""Literal deployment configuration only. No shell/environment interpolation or execution."""
import re
import posixpath
from urllib.parse import urlsplit
import yaml


def dotenv_literals(source, defaults=None):
    """Read repository defaults, never local process environment or shell commands."""
    values = {}
    if not isinstance(source, str) or len(source.encode()) > 65536:
        return values
    for line in source.splitlines():
        match = re.fullmatch(r'\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*?)\s*', line)
        if not match:
            continue
        key, value = match.groups()
        quoted_literal = value.startswith("'")
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                continue
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].rstrip()
        if not quoted_literal:
            value = compose_literal_default(value, {**(defaults or {}), **values})
        if not any(char in value for char in "$`\\"):
            values[key] = value
    return values


def compose_literal_default(value, defaults):
    """Resolve only simple recorded defaults; unresolved expressions stay unknown."""
    if not isinstance(value, str) or "$$" in value:
        return value
    pattern = r'\$\{([A-Za-z_][A-Za-z_0-9]*)(?:(:-|-|:\?|\?)([^{}]*))?\}|\$([A-Za-z_][A-Za-z_0-9]*)'
    def replace(match):
        key, op, fallback, bare = match.groups()
        key = key or bare
        present = key in defaults and (bool(defaults[key]) or op not in {":-", ":?"})
        if present:
            return defaults[key]
        if op in {"-", ":-"} and "$" not in fallback:
            return fallback
        return match[0]
    return re.sub(pattern, replace, value)


def literal_endpoint(value, variable=""):
    """Extract a host without retaining credentials, query parameters or secret values."""
    if not isinstance(value, str) or not value or any(char in value for char in "$ {}\n\r\t"):
        return None
    try:
        parsed = urlsplit(value if "://" in value else "//" + value)
        host, port = parsed.hostname, parsed.port
        scheme = parsed.scheme.lower()
        if not host or not re.fullmatch(r"[a-zA-Z0-9_.-]+", host):
            return None
        if not scheme and port is None and not re.search(r"HOST|ADDR|SERVER|ENDPOINT|URL|URI", variable, re.I):
            return None
        # A literal matching an internal alias is configuration evidence, not a call.
        if scheme and scheme not in {"http", "https", "grpc", "redis", "rediss", "postgres", "postgresql", "mysql", "mongodb", "amqp", "amqps"}:
            return None
        return host, scheme or "declared", parsed.path
    except ValueError:
        return None


def compose_ports(config):
    """Container target and published port, including host-IP and long syntax."""
    def number(value):
        text = str(value).split("/", 1)[0]
        return int(text) if text.isdigit() and 0 < int(text) <= 65535 else None
    for item in config.get("ports") or []:
        if isinstance(item, dict):
            target, published = number(item.get("target")), number(item.get("published"))
        else:
            parts = str(item).split(":")
            target = number(parts[-1])
            published = number(parts[-2]) if len(parts) > 1 else None
        if target:
            return target, published
    for item in config.get("expose") or []:
        if target := number(item):
            return target, None
    return None, None


def compose_default_config(config, defaults, file_environment=None):
    result = dict(config)
    for key in ("image", "hostname", "container_name"):
        if key in result:
            result[key] = compose_literal_default(result[key], defaults)
    for key in ("ports", "expose"):
        value = result.get(key)
        if isinstance(value, list):
            result[key] = [{k: compose_literal_default(v, defaults) for k, v in item.items()} if isinstance(item, dict)
                           else compose_literal_default(item, defaults) for item in value]
        elif isinstance(value, dict):
            result[key] = {k: compose_literal_default(v, defaults) for k, v in value.items()}
    environment = dict(file_environment or {})
    inline = config.get("environment") or {}
    if isinstance(inline, list):
        inline = dict(item.split("=", 1) if "=" in item else (item, None)
                      for item in inline if isinstance(item, str))
    if isinstance(inline, dict):
        for key, value in inline.items():
            environment[key] = defaults.get(key) if value is None else compose_literal_default(value, defaults)
    result["environment"] = environment
    return result


async def compose_env_files(content, source_file, tree, getter, defaults):
    """Bounded tracked env_file reads. Values never leave the discovery process."""
    try:
        document = yaml.safe_load(content)
    except yaml.YAMLError:
        return {}, ["compose_yaml_unavailable"]
    configs = document.get("services", {}) if isinstance(document, dict) else {}
    if not isinstance(configs, dict):
        return {}, []
    environments, cache, warnings = {}, {}, []
    for name, config in configs.items():
        if not isinstance(config, dict):
            continue
        files = config.get("env_file") or []
        if isinstance(files, str):
            files = [files]
        if not isinstance(files, list):
            continue
        combined = {}
        for entry in files:
            relative = entry.get("path") if isinstance(entry, dict) else entry
            if not isinstance(relative, str):
                continue
            relative = compose_literal_default(relative, defaults)
            path = posixpath.normpath(posixpath.join(posixpath.dirname(source_file), relative))
            if path.startswith(("/", "../")) or any(char in path for char in "$:\\") or path not in tree:
                warnings.append("compose_env_file_unavailable:" + name)
                continue
            if path not in cache:
                if len(cache) >= 32:
                    warnings.append("compose_env_file_limit_reached")
                    break
                cache[path] = {}
                try:
                    source = await getter(path)
                    if len(source.encode()) > 65536:
                        raise ValueError("size limit")
                    cache[path] = dotenv_literals(source, defaults)
                except Exception:
                    warnings.append("compose_env_file_unavailable:" + name)
            combined.update(cache[path])
        environments[name] = combined
    return environments, sorted(set(warnings))


def compose_references(configs, source_file):
    aliases = {name: name for name in configs}
    for name, config in configs.items():
        if not isinstance(config, dict):
            continue
        for key in ("hostname", "container_name"):
            alias = config.get(key)
            if isinstance(alias, str) and "$" not in alias:
                aliases[alias] = name if alias not in aliases else (name if aliases[alias] == name else None)
    edges = []
    for name, config in configs.items():
        if not isinstance(config, dict):
            continue
        env = config.get("environment") or {}
        if isinstance(env, list):
            env = dict(item.split("=", 1) for item in env if isinstance(item, str) and "=" in item)
        if not isinstance(env, dict):
            continue
        for key, value in env.items():
            endpoint = literal_endpoint(value, str(key))
            if not endpoint:
                continue
            host, protocol, path = endpoint
            target = aliases.get(host)
            if target and target != name:
                edges.append({"from": name, "to": target, "type": protocol, "endpoint": path,
                              "evidence_kind": "compose_env_reference", "source_file": source_file,
                              "environment_variable": str(key)})
    return edges


def merge_source_calls(services, service_files, dependencies, validator):
    """Keep startup/configuration evidence and each distinct observed static path."""
    targets = {service["name"]: service for service in services}
    seen = {(edge["from"], edge["to"], edge.get("type"), edge.get("endpoint"), edge.get("method"))
            for edge in dependencies if edge.get("evidence_kind") == "source_inferred"}
    for source, files in service_files.items():
        if source not in targets:
            continue
        for path, code in files.items():
            for call in validator.extract_outbound_calls(code, file_path=path):
                target = validator._resolve_host_to_service(call["host"], call["port"], targets)
                if not target or target == source:
                    continue
                endpoint = call.get("path") or "/"
                method = call.get("method")
                key = (source, target, "http", endpoint, method)
                if key in seen:
                    continue
                seen.add(key)
                edge = {"from": source, "to": target, "type": "http", "endpoint": endpoint,
                        "evidence_kind": "source_inferred", "source_file": path,
                        "source_line": call.get("line", call.get("line_number"))}
                if method:
                    edge["method"] = method
                dependencies.append(edge)
    return dependencies
