from datetime import date
import time

from app.services.universe import normalize_ticker


def provider_symbol(ticker: str) -> str:
    ticker = normalize_ticker(ticker)
    return 'BRK-B' if ticker == 'BRK.B' else ticker


class ProviderError(RuntimeError):
    def __init__(self, reason: str, attempts: int):
        self.reason, self.attempts = reason, attempts
        super().__init__(f'Market provider {reason} after {attempts} attempt(s)')


class YFinanceProvider:
    """One symbol at a time, with bounded attempts and explicit adjustment flags."""
    def __init__(self, downloader=None, attempts=3, interval=0.5,
                 sleeper=time.sleep, clock=time.monotonic):
        if not 1 <= attempts <= 3 or interval < 0.5:
            raise ValueError('Require 1–3 attempts and interval >= 0.5 seconds')
        self.downloader, self.attempts, self.interval = downloader, attempts, interval
        self.sleep, self.clock, self.last_request = sleeper, clock, None

    def fetch(self, ticker: str, start: date, end: date):
        if end <= start:
            raise ValueError('End date must follow start date')
        downloader = self.downloader
        if downloader is None:
            import yfinance as yf
            downloader = yf.download
        reason = 'failure'
        for attempt in range(self.attempts):
            if self.last_request is not None:
                self.sleep(max(0, self.interval - (self.clock() - self.last_request)))
            self.last_request = self.clock()
            try:
                frame = downloader(
                    tickers=provider_symbol(ticker), start=start.isoformat(), end=end.isoformat(),
                    interval='1d', auto_adjust=False, back_adjust=False, repair=False,
                    actions=False, keepna=True, prepost=False, rounding=False,
                    threads=False, progress=False, ignore_tz=False,
                    multi_level_index=False, timeout=30,
                )
                if frame is not None and not frame.empty:
                    return frame
                reason = 'empty_data'
            except Exception:
                reason = 'failure'
            if attempt < self.attempts - 1:
                self.sleep(2 ** attempt)
        raise ProviderError(reason, self.attempts) from None
