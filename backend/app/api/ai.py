"""Thin, server-side AI routes. Database reads finish before provider calls."""
from fastapi import APIRouter, Body, Depends, HTTPException

from app.api.dependencies import get_session, get_universe, known_company
from app.api.schemas import BriefResponse, ExplainResponse
from app.services import ai_evidence, ai_research, research_document
from app.api.snowflake import get_context
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
        result = ai_research.explain(evidence, provider)
        research_document.validated_research.remember('gemini', evidence.model_dump(mode='json'), result.model_dump())
        return result
    except ProviderFailure:
        raise HTTPException(status_code=503, detail='Explanation unavailable') from None


@router.post('/{ticker}/brief', response_model=BriefResponse)
def brief(evidence=Depends(get_evidence), provider=Depends(get_elevenlabs)):
    return ai_research.brief(evidence, provider)


@router.post('/{ticker}/research-audio', response_model=BriefResponse)
def research_audio(request: research_document.ResearchAudioRequest = Body(),
                   evidence=Depends(get_evidence), provider=Depends(get_elevenlabs),
                   snowflake_evidence=Depends(get_context)):
    if (evidence.event is None or request.research_event_id != evidence.event.research_event_id
            or (snowflake_evidence.get('event') or {}).get('research_event_id') != request.research_event_id):
        raise HTTPException(status_code=409, detail='Research event changed; regenerate AI research')
    if len(research_document.script(evidence.ticker, request.document)) > research_document.MAX_SCRIPT_CHARACTERS:
        raise HTTPException(status_code=413, detail='Research exceeds audio size limit')
    if not research_document.verify(request, evidence, snowflake_evidence):
        raise HTTPException(status_code=403, detail='Research verification unavailable; regenerate AI research')
    return research_document.synthesize(evidence.ticker, request.document, provider)
