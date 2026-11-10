"""Pure repository-validation rules (no internal imports)."""


def is_valid_repository(repository: str) -> bool:
    """Return True for a repository reference in ``owner/name`` form.

    Rules: exactly one separator, both parts non-empty and free of
    surrounding/inner whitespace.
    """
    parts = repository.split("/")
    if len(parts) != 2:
        return False
    return all(p and p == p.strip() and not any(ch.isspace() for ch in p) for p in parts)
