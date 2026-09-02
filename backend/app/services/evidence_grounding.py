from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Evidence, Case
from app.schemas.investigation import Finding, InvestigationResult


class EvidenceGroundingValidator:
    """Validates that all evidence references in findings are valid."""

    def __init__(self, db: Session):
        self.db = db

    def validate_findings(self, findings: list[Finding]) -> tuple[bool, list[str]]:
        """
        Validate that all evidence_ids in findings refer to existing evidence.
        
        Returns:
            tuple: (is_valid, list_of_errors)
        """
        errors = []
        
        # Collect all evidence IDs from findings
        all_evidence_ids = set()
        for finding in findings:
            for ev_id in finding.evidence_ids:
                all_evidence_ids.add(ev_id)
        
        if not all_evidence_ids:
            return True, []
        
        # Query database for all evidence IDs at once
        stmt = select(Evidence.id).where(Evidence.id.in_(all_evidence_ids))
        existing_ids = set(self.db.execute(stmt).scalars().all())
        
        # Check for missing evidence IDs
        missing_ids = all_evidence_ids - existing_ids
        if missing_ids:
            for missing_id in missing_ids:
                errors.append(
                    f"Finding references non-existent evidence ID: {missing_id}"
                )
        
        return len(errors) == 0, errors

    def validate_investigation_result(
        self, 
        investigation_result: InvestigationResult,
        case_id: UUID,
        findings: list[Finding],
    ) -> tuple[bool, list[str]]:
        """
        Validate an entire investigation result.
        
        Returns:
            tuple: (is_valid, list_of_errors)
        """
        from sqlalchemy import select
        
        errors = []
        
        # Validate findings
        is_valid, finding_errors = self.validate_findings(findings)
        errors.extend(finding_errors)
        
        # Validate evidence_references point to evidence in the same case
        if investigation_result.evidence_references:
            case = self.db.execute(
                select(Case).where(Case.id == case_id)
            ).scalar_one_or_none()
            
            if case:
                case_evidence_ids = set()
                for ev in case.evidence:
                    case_evidence_ids.add(ev.id)
                
                for ev_ref in investigation_result.evidence_references:
                    if ev_ref not in case_evidence_ids:
                        errors.append(
                            f"Investigation references evidence {ev_ref} not belonging to case {case_id}"
                        )
        
        return len(errors) == 0, errors