"""yfinance 기반 현물·일별 시세·옵션 체인 수집.

yfinance는 Yahoo의 공식 지원 서비스가 아니며 개인 연구 목적으로 사용한다.
수집 값은 지연·누락·수정될 수 있다.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .base import ProviderError

SOURCE = "Yahoo Finance (yfinance)"


def _yf():
    try:
        import yfinance as yf
        return yf
    except Exception as e:  # pragma: no cover
        raise ProviderError(f"yfinance를 불러올 수 없음: {e}")


def fetch_ticker(ticker: str, period: str = "2y") -> dict:
    yf = _yf()
    try:
        df = yf.Ticker(ticker).history(period=period, auto_adjust=False)
    except Exception as e:
        raise ProviderError(f"{ticker} 시세 수집 실패: {e}")
    if df is None or df.empty or "Close" not in df:
        raise ProviderError(f"{ticker} 시세가 비어 있음")
    df = df.dropna(subset=["Close"])
    adj = df["Adj Close"] if "Adj Close" in df else df["Close"]
    hist = [{"date": idx.date().isoformat(), "close": float(c), "adj_close": float(a)}
            for idx, c, a in zip(df.index, df["Close"], adj)]
    last = df.index[-1]
    cutoff = last - __import__("pandas").Timedelta(days=365)
    div_ttm = float(df["Dividends"][df.index > cutoff].sum()) if "Dividends" in df else None
    flags = []
    if "Adj Close" not in df:
        flags.append("조정종가 없음: 종가로 대체")
    return {"ticker": ticker, "history": hist, "last_bar_date": last.date().isoformat(), "dividends_ttm": div_ttm,
            "source": SOURCE, "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "currency": "USD", "quality_flags": flags}


def fetch_expiries(ticker: str) -> list:
    yf = _yf()
    try:
        return list(yf.Ticker(ticker).options)
    except Exception as e:
        raise ProviderError(f"{ticker} 옵션 만기 목록 수집 실패: {e}")


def fetch_option_chain(ticker: str, expiry: str) -> dict:
    yf = _yf()
    try:
        ch = yf.Ticker(ticker).option_chain(expiry)
    except Exception as e:
        raise ProviderError(f"{ticker} {expiry} 옵션 체인 수집 실패: {e}")
    rows = []
    for cp, df in (("CALL", ch.calls), ("PUT", ch.puts)):
        for _, r in df.iterrows():
            def num(k):
                v = r.get(k)
                try:
                    v = float(v)
                    return None if v != v else v
                except Exception:
                    return None
            bid, ask = num("bid"), num("ask")
            flags = []
            if bid is None or ask is None or not (ask >= bid >= 0) or ask == 0:
                flags.append("호가 무효")
            mid = (bid + ask) / 2 if not flags else None
            iv = num("impliedVolatility")
            if iv is None or iv <= 0 or iv > 5:
                flags.append("공급자 IV 비정상")
            ltd = r.get("lastTradeDate")
            rows.append({"ticker": ticker, "expiry": expiry, "strike": num("strike"), "option_type": cp, "bid": bid, "ask": ask,
                         "mid": mid, "last": num("lastPrice"), "last_trade_date": str(ltd) if ltd is not None else None,
                         "volume": num("volume"), "open_interest": num("openInterest"), "provider_iv": iv,
                         "contract_symbol": r.get("contractSymbol"), "currency": "USD", "quality_flags": flags})
    return {"ticker": ticker, "expiry": expiry, "rows": rows, "source": SOURCE, "exercise_style": "American (상장 ETF 옵션)",
            "snapshot_time": datetime.now(timezone.utc).isoformat(timespec="seconds")}
