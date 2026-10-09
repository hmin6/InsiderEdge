from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_session, get_universe, known_company
from app.api.schemas import CompanyResponse, InsidersResponse, PricesResponse, RadarResponse
from app.services import core_reads
from app.services.universe import CompanyMetadata, Universe

router = APIRouter(prefix='/api')


@router.get('/radar', response_model=RadarResponse)
def radar(universe: Universe = Depends(get_universe), session: Session = Depends(get_session)):
    return core_reads.radar(session, universe)


@router.get('/companies/{ticker}', response_model=CompanyResponse)
def company(company: CompanyMetadata = Depends(known_company), session: Session = Depends(get_session)):
    return core_reads.company(session, company)


@router.get('/companies/{ticker}/prices', response_model=PricesResponse)
def prices(company: CompanyMetadata = Depends(known_company), session: Session = Depends(get_session)):
    return core_reads.prices(session, company)


@router.get('/companies/{ticker}/insiders', response_model=InsidersResponse)
def insiders(company: CompanyMetadata = Depends(known_company), session: Session = Depends(get_session)):
    return core_reads.insiders(session, company)
