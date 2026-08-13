import logging

from fastapi import APIRouter, HTTPException

from app.services.company_intelligence import CompanyClassification, get_company_classification


router = APIRouter(prefix="/api/v1/company-intelligence", tags=["company-intelligence"])
logger = logging.getLogger(__name__)


@router.get("/{ticker}", response_model=CompanyClassification, response_model_by_alias=True)
def get_classification(ticker: str) -> CompanyClassification:
    try:
        return get_company_classification(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("company_classification_unavailable", extra={"ticker": ticker.upper()})
        raise HTTPException(
            status_code=502,
            detail={
                "code": "company_classification_unavailable",
                "message": "Company classification is temporarily unavailable.",
            },
        ) from exc
