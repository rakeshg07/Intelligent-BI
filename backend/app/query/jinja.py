"""Sandboxed Jinja SQL Templating Engine."""

from typing import Any

from jinja2.sandbox import SandboxedEnvironment


def render_template_sql(raw_sql: str, parameters: dict[str, Any]) -> str:
    """Render Jinja parameters into SQL inside a secure sandbox."""
    if "{{" not in raw_sql and "{%" not in raw_sql:
        return raw_sql

    env = SandboxedEnvironment(autoescape=False)
    template = env.from_string(raw_sql)
    return template.render(**parameters)
