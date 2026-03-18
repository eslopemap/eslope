import json


def jspprint(obj, indent=2, wrap_length=120, decimals=3) -> str:
    """Pretty-print JSON, but collapse any subtree that fits on one line.

    Starting from leaves, each node is first rendered as a single-line JSON string.
    If ``current_indent + len(single_line)`` ≤ *wrap_length* the compact form is kept;
    otherwise the node is expanded with *indent* extra spaces per nesting level.
    """
    def _round(node):
        if isinstance(node, float):
            return round(node, decimals)
        if isinstance(node, dict):
            return {k: _round(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_round(v) for v in node]
        return node

    obj = _round(obj)

    def _fmt(node, level):
        prefix = " " * (indent * level)
        compact = json.dumps(node, ensure_ascii=False, separators=(", ", ": "))
        if len(prefix) + len(compact) <= wrap_length:
            return compact

        if isinstance(node, dict):
            if not node:
                return "{}"
            items = []
            child_prefix = " " * (indent * (level + 1))
            for k, v in node.items():
                val = _fmt(v, level + 1)
                items.append(f"{child_prefix}{json.dumps(k)}: {val}")
            inner = ",\n".join(items)
            return "{\n" + inner + "\n" + prefix + "}"

        if isinstance(node, list):
            if not node:
                return "[]"
            items = []
            child_prefix = " " * (indent * (level + 1))
            for item in node:
                items.append(child_prefix + _fmt(item, level + 1))
            inner = ",\n".join(items)
            return "[\n" + inner + "\n" + prefix + "]"

        # Scalars always fit on one line
        return compact

    return _fmt(obj, 0)
