"""Thin, server-side AI routes. Database reads finish before provider calls."""
from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_session, get_universe, known_company
from app.api.schemas import BriefResponse, ExplainResponse
from app.services import ai_evidence, ai_research
from app.services.ai_providers import ElevenLabsProvider, GeminiProvider, ProviderFailure

router = APIRouter(prefix='/api/companies')


def get_gemini():
    return GeminiProvider()


def get_elevenlabs():
    return ElevenLabsProvider()


def get_evidence(company=Depends(known_company), session=Depends(get_session), universe=Depends(get_universe)):
    return ai_evidence.assemble(session, company, universe)


@router.post('/{ticker}/explain', response_model=ExplainResponse)
def explain(evidence=Depends(get_evidence), provider=Depends(get_gemini)):
    try:
        return ai_research.explain(evidence, provider)
    except ProviderFailure:
        raise HTTPException(status_code=503, detail='Explanation unavailable') from None


@router.post('/{ticker}/brief', response_model=BriefResponse)
def brief(evidence=Depends(get_evidence), provider=Depends(get_elevenlabs)):
    return ai_research.brief(evidence, provider)
