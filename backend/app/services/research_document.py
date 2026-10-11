"""Deterministic research document and verification for speech, with no model calls."""
import base64
from collections import OrderedDict
import hashlib
import json
from threading import Lock
from time import monotonic
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.api.schemas import BriefResponse
from app.services.ai_research import ExplanationSections, Text
from app.services.ai_providers import ProviderFailure
from app.services.snowflake_research import Context

DISCLAIMER = ('AI tools interpret existing evidence. They do not calculate or modify '
              'InsiderEdge scores or predictions. Research only; not investment advice.')
SOURCES = {'snowflake': 'Snowflake Cortex - event and filing context',
           'gemini': 'Gemini - quantitative signal interpretation'}
MAX_SCRIPT_CHARACTERS = 10000
DocumentText = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=700)]


class VerifiedExplanation(ExplanationSections):
    ticker: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=20)]
    # /explain appends persisted limitations after validating its eight-item sections.
    limitations: Annotated[list[Text], Field(max_length=32)]


class DocumentSection(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    title: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=80)]
    items: Annotated[list[DocumentText], Field(min_length=1, max_length=40)]


class ResearchDocument(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    title: Literal['Research Summary']
    sections: Annotated[list[DocumentSection], Field(min_length=1, max_length=6)]
    sources: Annotated[list[Annotated[str, StringConstraints(strict=True, max_length=80)]], Field(min_length=1, max_length=2)]
    unavailable: Annotated[list[DocumentText], Field(max_length=2)]
    disclaimer: Literal[DISCLAIMER]


class ResearchAudioRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    research_event_id: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=64)]
    snowflake_context: Context | None = None
    gemini_explanation: VerifiedExplanation | None = None
    document: ResearchDocument


class ValidatedResearch:
    """Bounded per-worker proof cache; stores hashes only, never evidence or prose."""
    def __init__(self, capacity=512, ttl=1200):
        self.capacity, self.ttl = capacity, ttl
        self.entries = OrderedDict()
        self.lock = Lock()

    @staticmethod
    def key(provider, evidence, output):
        def digest(value):
            return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False,
                                             separators=(',', ':')).encode()).digest()
        return provider, digest(evidence), digest(output)

    def remember(self, provider, evidence, output):
        key = self.key(provider, evidence, output)
        with self.lock:
            self.entries[key] = monotonic()
            self.entries.move_to_end(key)
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)

    def contains(self, provider, evidence, output):
        key = self.key(provider, evidence, output)
        with self.lock:
            timestamp = self.entries.get(key)
            return timestamp is not None and monotonic() - timestamp <= self.ttl


validated_research = ValidatedResearch()



def combine(snowflake, gemini):
    """Same ordered sections as frontend researchDocument.ts; preserve every source string."""
    sections = []
    def add(title, items):
        if items:
            sections.append({'title': title, 'items': items})
    if snowflake:
        add('Event & Filing Context', snowflake.event_context + snowflake.filing_context)
    if gemini:
        add('Signal Interpretation', gemini.why_flagged)
        add('Supporting Evidence', gemini.supportive_evidence)
        add('Risks / Counter-Evidence', gemini.risk_evidence)
        add('Uncertainty & Limitations', gemini.uncertainty + gemini.limitations)
    if snowflake:
        add('Research Considerations', snowflake.research_considerations)
    return ResearchDocument(title='Research Summary', sections=sections,
        sources=([SOURCES['snowflake']] if snowflake else []) + ([SOURCES['gemini']] if gemini else []),
        unavailable=([] if snowflake else ['Qualitative research context was unavailable.'])
                    + ([] if gemini else ['Quantitative AI interpretation was unavailable.']),
        disclaimer=DISCLAIMER)


def script(ticker, document):
    parts = [f'InsiderEdge research for {ticker}.', document.title]
    for section in document.sections:
        parts.extend([section.title, *section.items])
    parts.extend([*document.unavailable, 'Research generated from:', *document.sources, document.disclaimer])
    return '\n'.join(parts)


def verify(request, evidence, snowflake_evidence):
    """Fail closed: every supplied output and the complete displayed document must match."""
    snowflake, gemini = request.snowflake_context, request.gemini_explanation
    if snowflake is None and gemini is None:
        return False
    if snowflake is not None and not validated_research.contains(
            'snowflake', snowflake_evidence, snowflake.model_dump()):
        return False
    if gemini is not None and (gemini.ticker != evidence.ticker or not validated_research.contains(
            'gemini', evidence.model_dump(mode='json'), gemini.model_dump())):
        return False
    return request.document == combine(snowflake, gemini)


def synthesize(ticker, document, provider):
    text = script(ticker, document)
    try:
        audio = provider.synthesize(text)
        if not isinstance(audio, bytes) or not audio or len(audio) > 5 * 1024 * 1024:
            raise ProviderFailure('Audio unavailable')
        return BriefResponse(ticker=ticker, transcript=text, audio_base64=base64.b64encode(audio).decode(),
                             audio_mime_type='audio/mpeg', status='ok')
    except ProviderFailure:
        return BriefResponse(ticker=ticker, transcript=text, audio_base64=None,
                             audio_mime_type=None, status='audio_unavailable')
