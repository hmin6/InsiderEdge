"""Read-only contract mapping. No ingestion, event rebuilds or score calculation."""
from sqlalchemy import func, select

from app.api.schemas import (
    CompanyResponse, InsiderTransaction, InsidersResponse, PricePoint, PricesResponse,
    RadarItem, RadarResponse, ResearchEventSummary,
)
from app.db.models import Company, InsiderTransaction as Transaction, ResearchEvent, Signal
from app.services.market.repository import read_prices


def latest_events(tickers):
    ranked = select(
        ResearchEvent.research_event_id.label('event_id'),
        func.row_number().over(partition_by=ResearchEvent.ticker,
                               order_by=ResearchEvent.public_event_day.desc()).label('position'),
    ).where(ResearchEvent.ticker.in_(tickers)).subquery()
    return (select(ResearchEvent, Signal, Company)
            .join(ranked, ranked.c.event_id == ResearchEvent.research_event_id)
            .outerjoin(Signal, (Signal.research_event_id == ResearchEvent.research_event_id)
                       & (Signal.ticker == ResearchEvent.ticker)
                       & (Signal.public_event_day == ResearchEvent.public_event_day))
            .outerjoin(Company, Company.ticker == ResearchEvent.ticker)
            .where(ranked.c.position == 1))


def radar_item(event, signal, company, frozen):
    # No stored textual summary exists; NULL is the honest contract value.
    return RadarItem(
        ticker=frozen.ticker, company_name=company.company_name if company else frozen.company_name,
        sector=company.sector if company else frozen.sector, public_event_day=event.public_event_day,
        insider_signal_summary=None,
        insider_edge_score=signal.insider_edge_score if signal else None,
        anomaly_score=signal.anomaly_score if signal else None,
        activity_score=signal.activity_score if signal else None,
        statistical_score=signal.statistical_score if signal else None,
        dislocation_score=signal.dislocation_score if signal else None,
        ml_outperformance_probability=signal.model_probability if signal else None,
        score_status=signal.score_status if signal else 'insufficient_data',
        unavailable_components=signal.unavailable_components if signal else ['A', 'C', 'M', 'S', 'D'],
    )


def radar(session, universe):
    rows = session.execute(latest_events([company.ticker for company in universe.companies])).all()
    items = [radar_item(event, signal, company, universe.ticker_to_company(event.ticker))
             for event, signal, company in rows]
    items.sort(key=lambda item: (item.insider_edge_score is None,
                                 -(item.insider_edge_score if item.insider_edge_score is not None else 0),
                                 item.ticker))
    return RadarResponse(items=items)


def company(session, frozen):
    stored = session.get(Company, frozen.ticker)
    latest = session.execute(latest_events([frozen.ticker])).first()
    event, signal, metadata = latest if latest else (None, None, None)
    return CompanyResponse(
        ticker=frozen.ticker, cik=stored.cik if stored else frozen.cik,
        company_name=stored.company_name if stored else frozen.company_name,
        sector=stored.sector if stored else frozen.sector, industry=stored.industry if stored else None,
        latest_public_event_day=event.public_event_day if event else None,
        latest_signal=radar_item(event, signal, metadata, frozen) if signal else None,
    )


def prices(session, frozen):
    return PricesResponse(ticker=frozen.ticker,
                          prices=[PricePoint.model_validate(row) for row in read_prices(session, frozen.ticker)])


def insiders(session, frozen):
    transactions = session.scalars(select(Transaction).where(Transaction.ticker == frozen.ticker)
                                  .order_by(Transaction.filing_date, Transaction.transaction_date, Transaction.transaction_id))
    events = session.scalars(select(ResearchEvent).where(ResearchEvent.ticker == frozen.ticker)
                            .order_by(ResearchEvent.public_event_day))
    # Amendments remain raw provenance; only existing Issue #5 events are exposed.
    return InsidersResponse(ticker=frozen.ticker,
                            transactions=[InsiderTransaction.model_validate(row) for row in transactions],
                            research_events=[ResearchEventSummary.model_validate(row) for row in events])
