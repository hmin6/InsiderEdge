"""Additive optional research endpoint; core endpoints remain independent."""
from fastapi import APIRouter, Depends
from app.api.dependencies import get_session, known_company
from app.services import snowflake_research

router = APIRouter(prefix='/api/companies')


def get_provider():
    return snowflake_research.SnowflakeProvider()


def get_context(company=Depends(known_company), session=Depends(get_session)):
    return snowflake_research.assemble(session, company)


@router.post('/{ticker}/snowflake-research', response_model=snowflake_research.ResearchResponse)
def research(context=Depends(get_context), provider=Depends(get_provider)):
    return snowflake_research.research(context, provider)
