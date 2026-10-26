from financial_assistant.contracts.models import Evidence, Scope


class AccessDenied(PermissionError):
    pass


def require_entity(scope: Scope, entity: str) -> None:
    if entity not in scope.entities:
        raise AccessDenied("Entity is not authorized.")


def check_evidence(scope: Scope, evidence: tuple[Evidence, ...]) -> None:
    for item in evidence:
        if item.tenant_id != scope.tenant_id or item.entity not in scope.entities:
            raise AccessDenied("Evidence is outside the authorized scope.")
