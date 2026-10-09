"""Schema only. No ingestion, event aggregation, or research calculations."""
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Column, Date, DateTime, ForeignKey,
    Index, Integer, JSON, MetaData, Numeric, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention={
        'ix': 'ix_%(table_name)s_%(column_0_name)s',
        'uq': 'uq_%(table_name)s_%(column_0_name)s',
        'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
        'pk': 'pk_%(table_name)s',
    })


class Company(Base):
    __tablename__ = 'companies'
    ticker = Column(Text, primary_key=True)
    cik = Column(Text, index=True)
    company_name = Column(Text, nullable=False)
    sector = Column(Text, index=True)
    industry = Column(Text)


class InsiderTransaction(Base):
    __tablename__ = 'insider_transactions'
    transaction_id = Column(Text, primary_key=True)
    canonical_transaction_key = Column(Text, nullable=False, unique=True)
    accession_number = Column(Text, nullable=False, index=True)
    source_type = Column(Text, nullable=False)
    document_type = Column(Text)
    ticker = Column(Text, ForeignKey('companies.ticker'))
    cik = Column(Text, index=True)
    company_name = Column(Text)
    insider_name = Column(Text)
    insider_role = Column(Text)
    transaction_date = Column(Date, nullable=False)
    filing_date = Column(Date, nullable=False)
    accepted_at = Column(DateTime(timezone=True))
    public_event_day = Column(Date, index=True)
    transaction_code = Column(Text, nullable=False)
    acquired_or_disposed = Column(Text, nullable=False)
    derivative_flag = Column(Boolean, nullable=False)
    source_table = Column(Text)
    security_title = Column(Text)
    shares = Column(Numeric)
    price = Column(Numeric)
    transaction_value = Column(Numeric)
    shares_owned_after = Column(Numeric)
    direct_or_indirect = Column(Text)
    aff10b5one = Column(Boolean)
    is_amendment = Column(Boolean, nullable=False)
    is_p0_qualifying = Column(Boolean, nullable=False, index=True)
    __table_args__ = (
        Index('ix_insider_ticker_filing', 'ticker', 'filing_date'),
        Index('ix_insider_ticker_transaction', 'ticker', 'transaction_date'),
        CheckConstraint("source_type IN ('bulk', 'edgar')", name='ck_insider_source'),
    )


class ResearchEvent(Base):
    __tablename__ = 'research_events'
    research_event_id = Column(Text, primary_key=True)
    ticker = Column(Text, ForeignKey('companies.ticker'), nullable=False)
    public_event_day = Column(Date, nullable=False, index=True)
    information_date = Column(Date, nullable=False)
    source_transaction_count = Column(Integer, nullable=False)
    source_filing_count = Column(Integer, nullable=False)
    aggregate_purchase_value = Column(Numeric)
    unique_buyer_count = Column(Integer, nullable=False)
    role_bucket = Column(Text, nullable=False, index=True)
    has_executive = Column(Boolean, nullable=False)
    has_director = Column(Boolean, nullable=False)
    has_other = Column(Boolean, nullable=False)
    has_cfo = Column(Boolean)
    max_valid_ownership_change_pct = Column(Numeric)
    any_new_position_flag = Column(Boolean)
    feature_metadata = Column(JSON)
    __table_args__ = (
        UniqueConstraint('ticker', 'public_event_day'),
        CheckConstraint("role_bucket IN ('Executive', 'Director', 'Other')", name='ck_event_role'),
    )


class Price(Base):
    __tablename__ = 'prices'
    # No company FK: SPY and sector ETFs are outside the company universe.
    ticker = Column(Text, primary_key=True)
    date = Column(Date, primary_key=True, index=True)
    open = Column(Numeric)
    high = Column(Numeric)
    low = Column(Numeric)
    close = Column(Numeric)
    adjusted_close = Column(Numeric)
    analysis_price = Column(Numeric)
    volume = Column(BigInteger)


class Fundamental(Base):
    __tablename__ = 'fundamentals'
    fundamental_id = Column(Text, primary_key=True)
    ticker = Column(Text, ForeignKey('companies.ticker'), nullable=False)
    cik = Column(Text)
    report_period = Column(Date, nullable=False)
    filed_date = Column(Date, nullable=False)
    fiscal_year = Column(Integer)
    fiscal_period = Column(Text)
    cash = Column(Numeric)
    total_debt = Column(Numeric)
    equity = Column(Numeric)
    revenue = Column(Numeric)
    current_assets = Column(Numeric)
    current_liabilities = Column(Numeric)
    operating_income = Column(Numeric)
    unit_metadata = Column(JSON)
    currency = Column(Text)
    __table_args__ = (UniqueConstraint('ticker', 'report_period', 'filed_date', 'fiscal_period'),)


class Signal(Base):
    __tablename__ = 'signals'
    signal_id = Column(Text, primary_key=True)
    research_event_id = Column(Text, ForeignKey('research_events.research_event_id'), nullable=False, unique=True)
    ticker = Column(Text, ForeignKey('companies.ticker'), nullable=False)
    public_event_day = Column(Date, nullable=False)
    anomaly_score = Column(Numeric)
    activity_score = Column(Numeric)
    statistical_score = Column(Numeric)
    dislocation_score = Column(Numeric)
    model_probability = Column(Numeric)
    insider_edge_score = Column(Numeric, index=True)
    score_status = Column(Text, nullable=False, index=True)
    unavailable_components = Column(JSON, nullable=False)
    car5 = Column(Numeric)
    car30 = Column(Numeric)
    car90 = Column(Numeric)
    comparable_event_count = Column(Integer)
    comparable_cohort = Column(Text)
    mean_car30 = Column(Numeric)
    bootstrap_ci_lower = Column(Numeric)
    bootstrap_ci_upper = Column(Numeric)
    randomization_p_value = Column(Numeric)
    model_name = Column(Text)
    model_version = Column(Text)
    score_version = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        Index('ix_signals_ticker_day', 'ticker', 'public_event_day'),
        CheckConstraint("score_status IN ('complete', 'partial', 'insufficient_data')", name='ck_signal_status'),
        *[CheckConstraint(f'{name} BETWEEN 0 AND {limit}', name=f'ck_signals_{name}')
          for name, limit in [('anomaly_score', 100), ('activity_score', 100),
                              ('statistical_score', 100), ('dislocation_score', 100),
                              ('insider_edge_score', 100), ('model_probability', 1),
                              ('randomization_p_value', 1)]],
    )
