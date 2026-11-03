import hmac
import json
import math
import os
import time
import urllib.error
import urllib.request

import eth_account
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

load_dotenv()

PRIVATE_KEY = os.getenv("HL_AGENT_PRIVATE_KEY", "").strip()
ACCOUNT_ADDRESS = os.getenv("HL_ACCOUNT_ADDRESS", "").strip()
SIGNER_TOKEN = os.getenv("HL_SIGNER_TOKEN", "").strip()

if not PRIVATE_KEY:
    raise RuntimeError("HL_AGENT_PRIVATE_KEY is missing")
if not ACCOUNT_ADDRESS:
    raise RuntimeError("HL_ACCOUNT_ADDRESS is missing")
if not SIGNER_TOKEN:
    raise RuntimeError("HL_SIGNER_TOKEN is missing")

# ---------------------------------------------------------------------------
# HARD SERVER-SIDE RISK GATE
# This service is intentionally pinned to Hyperliquid TESTNET.
# Cancellation is always allowed so orders can still be made safer even when
# the kill switch blocks new orders.
# ---------------------------------------------------------------------------

RISK_GATE_VERSION = "server-v1"

# Trading/account/execution stay pinned to Hyperliquid TESTNET.
NETWORK = "testnet"
EXECUTION_API_URL = constants.TESTNET_API_URL

# Market data is intentionally sourced from Hyperliquid MAINNET so the
# strategy sees the real, liquid market while all orders remain simulated
# on Testnet.
MARKET_DATA_NETWORK = "mainnet"
MARKET_DATA_API_URL = constants.MAINNET_API_URL

ALLOWED_COINS = {"HYPE", "BTC", "ETH"}
MAX_SIZE = {
    "HYPE": 1.0,
    "BTC": 0.001,
    "ETH": 0.02,
}
MAX_NOTIONAL_USD = 100.0
MIN_LIMIT_PRICE = 0.000001
MAX_LIMIT_PRICE = 1_000_000.0
MAX_TESTNET_REFERENCE_GAP_PCT = 0.20
MAX_TESTNET_REFERENCE_GAP_STOP_UNITS = 0.75

INTERVAL_MS = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
}

# Set HL_KILL_SWITCH=true in Railway to immediately block all NEW orders.
KILL_SWITCH = os.getenv("HL_KILL_SWITCH", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Explicit server-side arming switch for real Testnet order execution.
# Validation endpoints remain available while this is false.
EXECUTION_ENABLED = os.getenv("HL_EXECUTION_ENABLED", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

agent = eth_account.Account.from_key(PRIVATE_KEY)

# Testnet client: account state, open orders, cancellations and execution.
execution_info = Info(EXECUTION_API_URL, skip_ws=True)

# Mainnet client: read-only market data only.
market_info = Info(MARKET_DATA_API_URL, skip_ws=True)

exchange = Exchange(
    agent,
    EXECUTION_API_URL,
    account_address=ACCOUNT_ADDRESS,
)

app = FastAPI(title="Hyperliquid Testnet Signer", version="2.11")


def require_token(x_signer_token: str = Header(default="")):
    if not hmac.compare_digest(x_signer_token, SIGNER_TOKEN):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


class OrderRequest(BaseModel):
    coin: str = Field(min_length=1, max_length=20)
    is_buy: bool
    size: float = Field(gt=0)
    limit_price: float = Field(gt=0)


class BracketOrderRequest(BaseModel):
    coin: str = Field(min_length=1, max_length=20)
    is_buy: bool
    size: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    stop_loss: float = Field(gt=0)
    take_profit: float = Field(gt=0)


class CancelRequest(BaseModel):
    coin: str = Field(min_length=1, max_length=20)
    oid: int = Field(gt=0)


class TestCloseRequest(BaseModel):
    coin: str = Field(min_length=1, max_length=20)


class TestnetSmokeBracketRequest(BaseModel):
    coin: str = Field(default="BTC", min_length=1, max_length=20)
    notional_usd: float = Field(default=12.0, ge=10.5, le=15.0)
    is_buy: bool = True


class TestnetTransportBracketRequest(BaseModel):
    coin: str = Field(default="BTC", min_length=1, max_length=20)
    is_buy: bool
    size: float = Field(gt=0)
    strategy_entry_price: float = Field(gt=0)
    stop_loss_pct: float = Field(gt=0.1, le=4.0)
    take_profit_pct: float = Field(gt=0.1, le=10.0)




def risk_payload() -> dict:
    return {
        "enabled": True,
        "version": RISK_GATE_VERSION,
        "kill_switch": KILL_SWITCH,
        "execution_enabled": EXECUTION_ENABLED,
        "allowed_coins": sorted(ALLOWED_COINS),
        "max_size": MAX_SIZE,
        "max_notional_usd": MAX_NOTIONAL_USD,
        "min_limit_price": MIN_LIMIT_PRICE,
        "max_limit_price": MAX_LIMIT_PRICE,
        "max_testnet_reference_gap_pct": MAX_TESTNET_REFERENCE_GAP_PCT,
        "max_testnet_reference_gap_stop_units": MAX_TESTNET_REFERENCE_GAP_STOP_UNITS,
    }


def validate_order(req: OrderRequest) -> dict:
    if KILL_SWITCH:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "RISK_GATE_BLOCKED",
                "reason": "Kill switch is ON",
                "risk_gate_version": RISK_GATE_VERSION,
            },
        )

    coin = req.coin.strip().upper()
    size = float(req.size)
    limit_price = float(req.limit_price)

    if coin not in ALLOWED_COINS:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "RISK_GATE_BLOCKED",
                "reason": f"Coin {coin} is not allowed",
                "risk_gate_version": RISK_GATE_VERSION,
            },
        )

    if not math.isfinite(size) or size <= 0:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "RISK_GATE_BLOCKED",
                "reason": "Invalid size",
                "risk_gate_version": RISK_GATE_VERSION,
            },
        )

    max_size = MAX_SIZE[coin]
    if size > max_size:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "RISK_GATE_BLOCKED",
                "reason": f"{coin} size {size} exceeds maximum {max_size}",
                "risk_gate_version": RISK_GATE_VERSION,
            },
        )

    if (
        not math.isfinite(limit_price)
        or limit_price < MIN_LIMIT_PRICE
        or limit_price > MAX_LIMIT_PRICE
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "RISK_GATE_BLOCKED",
                "reason": "Limit price is outside the allowed sanity range",
                "risk_gate_version": RISK_GATE_VERSION,
            },
        )

    notional = size * limit_price
    if not math.isfinite(notional) or notional > MAX_NOTIONAL_USD:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "RISK_GATE_BLOCKED",
                "reason": (
                    f"Notional USD {notional:.2f} exceeds "
                    f"USD {MAX_NOTIONAL_USD:.2f}"
                ),
                "risk_gate_version": RISK_GATE_VERSION,
            },
        )

    return {
        "coin": coin,
        "is_buy": req.is_buy,
        "size": size,
        "limit_price": limit_price,
        "notional_usd": round(notional, 2),
    }


def _asset_sz_decimals(coin: str) -> int:
    """
    Hyperliquid perp prices are constrained by both:
    - max 5 significant figures
    - max decimals = 6 - szDecimals

    Read szDecimals from TESTNET metadata because execution happens on Testnet.
    """
    normalized_coin = coin.strip().upper()
    meta = execution_info.meta()

    for asset in meta.get("universe", []):
        if str(asset.get("name", "")).strip().upper() == normalized_coin:
            return int(asset.get("szDecimals", 0))

    raise HTTPException(
        status_code=400,
        detail={
            "error": "PRICE_RULE_LOOKUP_FAILED",
            "reason": f"Could not find Testnet metadata for {normalized_coin}",
        },
    )


def _price_tick(coin: str, price: float) -> float:
    if not math.isfinite(price) or price <= 0:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_PRICE",
                "reason": f"Invalid price {price}",
            },
        )

    sz_decimals = _asset_sz_decimals(coin)
    max_decimals = max(0, 6 - sz_decimals)

    magnitude = math.floor(math.log10(abs(price)))
    decimals_for_5_sig_figs = 4 - magnitude
    allowed_decimals = min(max_decimals, decimals_for_5_sig_figs)

    return 10.0 ** (-allowed_decimals)


def _quantize_hl_price(coin: str, price: float, direction: str = "nearest") -> float:
    """
    Quantize a price to a valid Hyperliquid price increment.

    direction:
      nearest -> nearest legal price
      up      -> legal price >= input
      down    -> legal price <= input
    """
    tick = _price_tick(coin, price)
    scaled = price / tick

    if direction == "up":
        units = math.ceil(scaled - 1e-12)
    elif direction == "down":
        units = math.floor(scaled + 1e-12)
    else:
        units = round(scaled)

    return float(units * tick)


def _testnet_mid(coin: str) -> float:
    normalized_coin = coin.strip().upper()
    mids = execution_info.all_mids()
    raw_mid = mids.get(normalized_coin)

    if raw_mid is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "TESTNET_MID_UNAVAILABLE",
                "reason": f"No Testnet mid available for {normalized_coin}",
            },
        )

    mid = float(raw_mid)

    if not math.isfinite(mid) or mid <= 0:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "TESTNET_MID_INVALID",
                "reason": f"Invalid Testnet mid for {normalized_coin}",
            },
        )

    return mid


def validate_bracket_order(req: BracketOrderRequest) -> dict:
    """
    Validate the strategy bracket using MAINNET-derived prices.

    These absolute prices are NOT sent directly to Testnet because Mainnet and
    Testnet can trade at different levels. The execution endpoint preserves the
    stop/target percentages and rebases them onto the live Testnet midpoint.
    """
    approved = validate_order(
        OrderRequest(
            coin=req.coin,
            is_buy=req.is_buy,
            size=req.size,
            limit_price=req.entry_price,
        )
    )

    stop_loss = float(req.stop_loss)
    take_profit = float(req.take_profit)
    entry_price = float(req.entry_price)

    if not math.isfinite(stop_loss) or not math.isfinite(take_profit):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "RISK_GATE_BLOCKED",
                "reason": "Invalid stop loss or take profit",
                "risk_gate_version": RISK_GATE_VERSION,
            },
        )

    if req.is_buy:
        valid_geometry = stop_loss < entry_price < take_profit
        stop_distance = entry_price - stop_loss
        take_profit_distance = take_profit - entry_price
    else:
        valid_geometry = take_profit < entry_price < stop_loss
        stop_distance = stop_loss - entry_price
        take_profit_distance = entry_price - take_profit

    if not valid_geometry:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "RISK_GATE_BLOCKED",
                "reason": "Invalid bracket geometry",
                "risk_gate_version": RISK_GATE_VERSION,
            },
        )

    stop_fraction = stop_distance / entry_price
    take_profit_fraction = take_profit_distance / entry_price

    if (
        not math.isfinite(stop_fraction)
        or not math.isfinite(take_profit_fraction)
        or stop_fraction <= 0
        or take_profit_fraction <= 0
    ):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "RISK_GATE_BLOCKED",
                "reason": "Invalid bracket distances",
                "risk_gate_version": RISK_GATE_VERSION,
            },
        )

    return {
        **approved,
        "strategy_entry_price": entry_price,
        "strategy_stop_loss": stop_loss,
        "strategy_take_profit": take_profit,
        "stop_fraction": stop_fraction,
        "take_profit_fraction": take_profit_fraction,
    }

def ensure_flat_and_no_open_orders() -> None:
    perp_state = execution_info.user_state(ACCOUNT_ADDRESS)

    for wrapped in perp_state.get("assetPositions", []):
        position = wrapped.get("position", {})
        try:
            size = float(position.get("szi", "0") or 0)
        except (TypeError, ValueError):
            size = 0.0

        if size != 0:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "EXPOSURE_BLOCKED",
                    "reason": "An open position already exists",
                },
            )

    if execution_info.open_orders(ACCOUNT_ADDRESS):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "EXPOSURE_BLOCKED",
                "reason": "An open order already exists",
            },
        )


@app.get("/ping")
def ping():
    return {"ok": True, "service": "hl-n8n-signer"}


@app.get("/health")
def health(_: bool = Depends(require_token)):
    return {
        "ok": True,
        "network": NETWORK,
        "market_data_network": MARKET_DATA_NETWORK,
        "account_address": ACCOUNT_ADDRESS,
        "agent_address": agent.address,
        "private_key_exposed": False,
        "auth": "required",
        "risk_gate": risk_payload(),
    }


@app.get("/risk")
def risk(_: bool = Depends(require_token)):
    return {
        "ok": True,
        "network": NETWORK,
        "risk_gate": risk_payload(),
    }


@app.get("/agent_snapshot")
def agent_snapshot(_: bool = Depends(require_token)):
    try:
        perp_state = execution_info.user_state(ACCOUNT_ADDRESS)
        spot_state = execution_info.spot_user_state(ACCOUNT_ADDRESS)
        open_orders = execution_info.open_orders(ACCOUNT_ADDRESS)
        mids = market_info.all_mids()

        positions = []
        for wrapped in perp_state.get("assetPositions", []):
            position = wrapped.get("position", {})
            try:
                size = float(position.get("szi", "0") or 0)
            except (TypeError, ValueError):
                size = 0.0
            if size != 0:
                positions.append(position)

        allowed_mids = {
            coin: mids.get(coin)
            for coin in sorted(ALLOWED_COINS)
            if mids.get(coin) is not None
        }

        # Hyperliquid Unified accounts expose collateral balances in the
        # spot clearinghouse state. In that mode the individual perp
        # clearinghouse state's marginSummary can legitimately be zero.
        usdc_balance = None
        for balance in spot_state.get("balances", []):
            if balance.get("coin") == "USDC":
                usdc_balance = balance
                break

        def _as_float(value):
            try:
                return float(value or 0)
            except (TypeError, ValueError):
                return 0.0

        perp_margin_summary = perp_state.get("marginSummary") or {}
        perp_account_value = _as_float(perp_margin_summary.get("accountValue"))

        spot_usdc_total = _as_float(
            usdc_balance.get("total") if usdc_balance else 0
        )
        spot_usdc_hold = _as_float(
            usdc_balance.get("hold") if usdc_balance else 0
        )
        spot_usdc_available = max(spot_usdc_total - spot_usdc_hold, 0.0)

        if spot_usdc_total > 0 and perp_account_value == 0:
            collateral_source = "spot_unified"
            normalized_account_value = spot_usdc_total
            normalized_available = spot_usdc_available
        else:
            collateral_source = "perp"
            normalized_account_value = perp_account_value
            normalized_available = _as_float(perp_state.get("withdrawable"))

        return {
            "ok": True,
            "network": NETWORK,
            "server_time_ms": int(time.time() * 1000),
            "market": {
                "source_network": MARKET_DATA_NETWORK,
                "mids": allowed_mids,
            },
            "account": {
                "withdrawable": perp_state.get("withdrawable"),
                "marginSummary": perp_margin_summary,
                "positions": positions,
                "spot": {
                    "usdc": usdc_balance,
                },
                "normalized": {
                    "collateral_source": collateral_source,
                    "account_value_usd": normalized_account_value,
                    "available_usd": normalized_available,
                },
            },
            "open_orders": open_orders,
            "risk_gate": risk_payload(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/candles/{coin}")
def candles(
    coin: str,
    interval: str = "5m",
    limit: int = 200,
    _: bool = Depends(require_token),
):
    normalized_coin = coin.strip().upper()

    if normalized_coin not in ALLOWED_COINS:
        raise HTTPException(status_code=400, detail="Coin is not allowed")

    if interval not in INTERVAL_MS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported interval. Allowed: {sorted(INTERVAL_MS)}",
        )

    if limit < 20 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 20 and 500")

    end_time = int(time.time() * 1000)
    start_time = end_time - (INTERVAL_MS[interval] * limit)

    # Use a short-lived direct HTTP request for candles instead of the shared
    # global SDK client. Snapshot and candle requests are triggered in parallel
    # by n8n; isolating this request avoids shared-client contention and, more
    # importantly, gives us a hard upstream timeout so Railway never hangs long
    # enough to surface an nginx 502.
    payload = {
        "type": "candleSnapshot",
        "req": {
            "coin": normalized_coin,
            "interval": interval,
            "startTime": start_time,
            "endTime": end_time,
        },
    }

    last_error = None
    attempts = 3

    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                f"{MARKET_DATA_API_URL}/info",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "hl-n8n-signer/2.8",
                },
                method="POST",
            )

            with urllib.request.urlopen(request, timeout=5.0) as response:
                raw = response.read().decode("utf-8")
                data = json.loads(raw)

            if not isinstance(data, list):
                raise RuntimeError(
                    f"Unexpected candle response type: {type(data).__name__}"
                )

            if len(data) < 20:
                raise RuntimeError(
                    f"Insufficient candle data: received {len(data)} rows"
                )

            return {
                "ok": True,
                "network": NETWORK,
                "market_data_network": MARKET_DATA_NETWORK,
                "coin": normalized_coin,
                "interval": interval,
                "count": len(data),
                "candles": data,
                "upstream_attempt": attempt,
            }

        except urllib.error.HTTPError as exc:
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            last_error = f"HTTP {exc.code}: {body[:300]}"

        except urllib.error.URLError as exc:
            last_error = f"URL error: {exc.reason}"

        except TimeoutError:
            last_error = "upstream timeout"

        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        if attempt < attempts:
            time.sleep(0.25 * attempt)

    raise HTTPException(
        status_code=503,
        detail=(
            "Mainnet candle data unavailable after "
            f"{attempts} attempts: {last_error}"
        ),
    )


@app.get("/account")
def account(_: bool = Depends(require_token)):
    try:
        perp_state = execution_info.user_state(ACCOUNT_ADDRESS)
        spot_state = execution_info.spot_user_state(ACCOUNT_ADDRESS)
        return {
            "ok": True,
            "perp": {
                "withdrawable": perp_state.get("withdrawable"),
                "marginSummary": perp_state.get("marginSummary"),
                "positions": [
                    p.get("position", {})
                    for p in perp_state.get("assetPositions", [])
                ],
            },
            "spot": spot_state,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/fills")
def fills(
    coin: str = "BTC",
    limit: int = 100,
    _: bool = Depends(require_token),
):
    """
    Read-only recent fill history from Hyperliquid TESTNET.

    This endpoint never places, cancels, or modifies orders.
    It is intended for Forward Test outcome reconciliation in n8n.
    """
    normalized_coin = coin.strip().upper()

    if normalized_coin not in ALLOWED_COINS:
        raise HTTPException(status_code=400, detail="Coin is not allowed")

    if limit < 1 or limit > 500:
        raise HTTPException(
            status_code=400,
            detail="limit must be between 1 and 500",
        )

    def _optional_float(value):
        if value is None or value == "":
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    def _optional_int(value):
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    try:
        raw_fills = execution_info.user_fills(ACCOUNT_ADDRESS)

        coin_fills = [
            fill
            for fill in raw_fills
            if str(fill.get("coin", "")).strip().upper() == normalized_coin
        ]

        coin_fills.sort(
            key=lambda fill: _optional_int(fill.get("time")) or 0,
            reverse=True,
        )

        selected = coin_fills[:limit]

        normalized_fills = []
        for fill in selected:
            normalized_fills.append(
                {
                    "coin": normalized_coin,
                    "direction": fill.get("dir"),
                    "side": fill.get("side"),
                    "price": _optional_float(fill.get("px")),
                    "size": _optional_float(fill.get("sz")),
                    "closed_pnl": _optional_float(fill.get("closedPnl")),
                    "start_position": _optional_float(fill.get("startPosition")),
                    "time_ms": _optional_int(fill.get("time")),
                    "oid": _optional_int(fill.get("oid")),
                    "tid": _optional_int(fill.get("tid")),
                    "hash": fill.get("hash"),
                    "crossed": fill.get("crossed"),
                    "fee": _optional_float(fill.get("fee")),
                    "fee_token": fill.get("feeToken"),
                }
            )

        return {
            "ok": True,
            "network": NETWORK,
            "source": "hyperliquid_user_fills",
            "coin": normalized_coin,
            "count": len(normalized_fills),
            "server_time_ms": int(time.time() * 1000),
            "fills": normalized_fills,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/validate_order")
def validate_order_only(req: OrderRequest, _: bool = Depends(require_token)):
    """
    Validate a proposed order against the hard server-side risk gate
    without placing any order on Hyperliquid.
    """
    approved = validate_order(req)

    return {
        "ok": True,
        "network": NETWORK,
        "mode": "validation_only",
        "order": approved,
        "risk_gate": {
            **risk_payload(),
            "approved": True,
        },
        "execution": {
            "performed": False,
            "reason": "VALIDATION_ONLY",
        },
    }


@app.post("/place_order")
def place_order(req: OrderRequest, _: bool = Depends(require_token)):
    if not EXECUTION_ENABLED:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "EXECUTION_DISABLED",
                "reason": "Server-side Testnet execution is not armed",
                "risk_gate_version": RISK_GATE_VERSION,
            },
        )

    approved = validate_order(req)

    try:
        result = exchange.order(
            approved["coin"],
            approved["is_buy"],
            approved["size"],
            approved["limit_price"],
            {"limit": {"tif": "Gtc"}},
        )
        if isinstance(result, dict):
            result = dict(result)
            result["risk_gate"] = {
                "approved": True,
                "version": RISK_GATE_VERSION,
                "notional_usd": approved["notional_usd"],
            }
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/place_bracket_order")
def place_bracket_order(
    req: BracketOrderRequest,
    _: bool = Depends(require_token),
):
    """
    Execute a protected BTC/ETH/HYPE Testnet bracket using live TESTNET prices.

    The strategy signal is generated from MAINNET data, so its absolute
    entry/SL/TP prices are treated as a geometry template. We preserve the
    stop/target percentages, rebase them to the live Testnet midpoint, then
    quantize every Testnet price to Hyperliquid's legal price precision.

    The entry is an aggressive IOC limit so the Testnet simulation represents
    an immediate signal entry instead of leaving a stale Mainnet-priced order.
    """
    if not EXECUTION_ENABLED:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "EXECUTION_DISABLED",
                "reason": "Server-side Testnet execution is not armed",
                "risk_gate_version": RISK_GATE_VERSION,
            },
        )

    strategy = validate_bracket_order(req)
    ensure_flat_and_no_open_orders()

    coin = strategy["coin"]
    is_buy = strategy["is_buy"]
    size = strategy["size"]

    testnet_mid = _testnet_mid(coin)

    # -----------------------------------------------------------------------
    # MAINNET -> TESTNET PARITY GATE
    #
    # Strategy signals are generated from Mainnet, while execution happens on
    # Testnet. If the two venues are too far apart, a Testnet fill no longer
    # represents the strategy entry we are trying to evaluate. In that case,
    # fail closed: keep the signal/candidate logs, but do NOT place an order.
    # -----------------------------------------------------------------------
    strategy_entry = float(strategy["strategy_entry_price"])
    strategy_stop_distance = (
        strategy_entry * float(strategy["stop_fraction"])
    )
    reference_gap = abs(testnet_mid - strategy_entry)
    reference_gap_pct = (reference_gap / strategy_entry) * 100.0
    reference_gap_stop_units = (
        reference_gap / strategy_stop_distance
        if strategy_stop_distance > 0
        else math.inf
    )

    if (
        reference_gap_pct > MAX_TESTNET_REFERENCE_GAP_PCT
        or reference_gap_stop_units > MAX_TESTNET_REFERENCE_GAP_STOP_UNITS
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "error": "TESTNET_REFERENCE_PARITY_BLOCKED",
                "reason": (
                    "Testnet market is too far from the Mainnet strategy "
                    "reference to produce a representative forward-test fill"
                ),
                "coin": coin,
                "strategy_entry_price": strategy_entry,
                "testnet_mid": testnet_mid,
                "reference_gap": reference_gap,
                "reference_gap_pct": round(reference_gap_pct, 4),
                "reference_gap_stop_units": round(
                    reference_gap_stop_units, 4
                ),
                "max_reference_gap_pct": (
                    MAX_TESTNET_REFERENCE_GAP_PCT
                ),
                "max_reference_gap_stop_units": (
                    MAX_TESTNET_REFERENCE_GAP_STOP_UNITS
                ),
            },
        )

    # Rebase the strategy's percentage distances onto the live Testnet market.
    if is_buy:
        raw_stop = testnet_mid * (1.0 - strategy["stop_fraction"])
        raw_take_profit = testnet_mid * (1.0 + strategy["take_profit_fraction"])
    else:
        raw_stop = testnet_mid * (1.0 + strategy["stop_fraction"])
        raw_take_profit = testnet_mid * (1.0 - strategy["take_profit_fraction"])

    # Hyperliquid price precision: max 5 significant figures and the
    # asset-specific decimal constraint. Round protective prices outward.
    if is_buy:
        stop_loss = _quantize_hl_price(coin, raw_stop, "down")
        take_profit = _quantize_hl_price(coin, raw_take_profit, "up")
    else:
        stop_loss = _quantize_hl_price(coin, raw_stop, "up")
        take_profit = _quantize_hl_price(coin, raw_take_profit, "down")

    # Use an aggressive IOC limit around the live Testnet midpoint.
    # 0.5% is still bounded by MAX_NOTIONAL_USD and is only for Testnet.
    entry_slippage = 0.005
    if is_buy:
        raw_entry_limit = testnet_mid * (1.0 + entry_slippage)
        entry_price = _quantize_hl_price(coin, raw_entry_limit, "up")
    else:
        raw_entry_limit = testnet_mid * (1.0 - entry_slippage)
        entry_price = _quantize_hl_price(coin, raw_entry_limit, "down")

    # Final geometry must be valid relative to the CURRENT Testnet market,
    # not merely relative to the Mainnet strategy reference.
    if is_buy:
        valid_testnet_geometry = stop_loss < testnet_mid < take_profit
    else:
        valid_testnet_geometry = take_profit < testnet_mid < stop_loss

    if not valid_testnet_geometry:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "TESTNET_BRACKET_GEOMETRY_BLOCKED",
                "reason": "Rebased Testnet TP/SL geometry is invalid",
                "testnet_mid": testnet_mid,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            },
        )

    # Re-run the hard server risk gate using the actual Testnet execution limit.
    execution_approved = validate_order(
        OrderRequest(
            coin=coin,
            is_buy=is_buy,
            size=size,
            limit_price=entry_price,
        )
    )

    exit_is_buy = not is_buy

    orders = [
        {
            "coin": coin,
            "is_buy": is_buy,
            "sz": size,
            "limit_px": entry_price,
            "order_type": {"limit": {"tif": "Ioc"}},
            "reduce_only": False,
        },
        {
            "coin": coin,
            "is_buy": exit_is_buy,
            "sz": size,
            "limit_px": take_profit,
            "order_type": {
                "trigger": {
                    "triggerPx": take_profit,
                    "isMarket": True,
                    "tpsl": "tp",
                }
            },
            "reduce_only": True,
        },
        {
            "coin": coin,
            "is_buy": exit_is_buy,
            "sz": size,
            "limit_px": stop_loss,
            "order_type": {
                "trigger": {
                    "triggerPx": stop_loss,
                    "isMarket": True,
                    "tpsl": "sl",
                }
            },
            "reduce_only": True,
        },
    ]

    try:
        result = exchange.bulk_orders(
            orders,
            grouping="normalTpsl",
        )

        statuses = []
        if isinstance(result, dict):
            statuses = (
                result.get("response", {})
                .get("data", {})
                .get("statuses", [])
            )

        errors = [
            status.get("error")
            for status in statuses
            if isinstance(status, dict) and status.get("error")
        ]

        if errors:
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "HYPERLIQUID_ORDER_REJECTED",
                    "reasons": errors,
                    "strategy_prices": {
                        "entry_price": strategy["strategy_entry_price"],
                        "stop_loss": strategy["strategy_stop_loss"],
                        "take_profit": strategy["strategy_take_profit"],
                    },
                    "testnet_prices": {
                        "mid": testnet_mid,
                        "entry_price": entry_price,
                        "stop_loss": stop_loss,
                        "take_profit": take_profit,
                    },
                    "exchange_result": result,
                },
            )

        return {
            "ok": True,
            "network": NETWORK,
            "mode": "testnet_bracket_execution_v2",
            "request": {
                "coin": coin,
                "side": "BUY" if is_buy else "SELL",
                "size": size,
                "strategy_reference": {
                    "market_data_network": MARKET_DATA_NETWORK,
                    "entry_price": strategy["strategy_entry_price"],
                    "stop_loss": strategy["strategy_stop_loss"],
                    "take_profit": strategy["strategy_take_profit"],
                },
                "testnet_execution": {
                    "mid": testnet_mid,
                    "entry_price": entry_price,
                    "stop_loss": stop_loss,
                    "take_profit": take_profit,
                    "entry_tif": "Ioc",
                    "entry_slippage_cap_pct": entry_slippage * 100,
                    "notional_usd_at_limit": round(size * entry_price, 2),
                },
            },
            "risk_gate": {
                **risk_payload(),
                "approved": True,
                "execution_notional_usd": execution_approved["notional_usd"],
            },
            "exchange_result": result,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))





@app.post("/place_testnet_transport_bracket")
def place_testnet_transport_bracket(
    req: TestnetTransportBracketRequest,
    _: bool = Depends(require_token),
):
    """
    TESTNET-only natural-signal execution transport.

    Signal/side/risk percentages originate from MAINNET strategy logic, while
    absolute execution prices are derived from live TESTNET midpoint.
    This endpoint intentionally does NOT apply the Mainnet/Testnet parity gate,
    because its purpose is execution plumbing validation, not representative
    forward PnL. The stricter /place_bracket_order remains unchanged.
    """
    if NETWORK != "testnet":
        raise HTTPException(status_code=403, detail={"error":"TESTNET_ONLY"})
    if not EXECUTION_ENABLED:
        raise HTTPException(status_code=403, detail={"error":"EXECUTION_DISABLED"})
    if KILL_SWITCH:
        raise HTTPException(status_code=403, detail={"error":"KILL_SWITCH"})

    coin=req.coin.strip().upper()
    if coin!="BTC":
        raise HTTPException(status_code=400, detail="Transport route is BTC-only")

    ensure_flat_and_no_open_orders()

    testnet_mid=_testnet_mid(coin)
    size=float(req.size)
    approved=validate_order(OrderRequest(
        coin=coin,is_buy=bool(req.is_buy),size=size,limit_price=testnet_mid
    ))

    stop_fraction=float(req.stop_loss_pct)/100.0
    tp_fraction=float(req.take_profit_pct)/100.0
    if stop_fraction<=0 or tp_fraction<=0:
        raise HTTPException(status_code=400,detail="Invalid risk percentages")

    if req.is_buy:
        stop_loss=_quantize_hl_price(coin,testnet_mid*(1.0-stop_fraction),"down")
        take_profit=_quantize_hl_price(coin,testnet_mid*(1.0+tp_fraction),"up")
        entry_price=_quantize_hl_price(coin,testnet_mid*1.005,"up")
    else:
        stop_loss=_quantize_hl_price(coin,testnet_mid*(1.0+stop_fraction),"up")
        take_profit=_quantize_hl_price(coin,testnet_mid*(1.0-tp_fraction),"down")
        entry_price=_quantize_hl_price(coin,testnet_mid*0.995,"down")

    orders=[
        {"coin":coin,"is_buy":bool(req.is_buy),"sz":size,"limit_px":entry_price,
         "order_type":{"limit":{"tif":"Ioc"}},"reduce_only":False},
        {"coin":coin,"is_buy":not bool(req.is_buy),"sz":size,"limit_px":take_profit,
         "order_type":{"trigger":{"triggerPx":take_profit,"isMarket":True,"tpsl":"tp"}},
         "reduce_only":True},
        {"coin":coin,"is_buy":not bool(req.is_buy),"sz":size,"limit_px":stop_loss,
         "order_type":{"trigger":{"triggerPx":stop_loss,"isMarket":True,"tpsl":"sl"}},
         "reduce_only":True},
    ]

    try:
        result=exchange.bulk_orders(orders,grouping="normalTpsl")
        statuses=[]
        if isinstance(result,dict):
            statuses=result.get("response",{}).get("data",{}).get("statuses",[])
        errors=[s.get("error") for s in statuses if isinstance(s,dict) and s.get("error")]
        if errors:
            raise HTTPException(status_code=502,detail={
                "error":"HYPERLIQUID_ORDER_REJECTED",
                "reasons":errors,
                "exchange_result":result,
            })
        return {
            "ok":True,
            "network":NETWORK,
            "mode":"TESTNET_TRANSPORT_VALIDATION",
            "coin":coin,
            "side":"LONG" if req.is_buy else "SHORT",
            "strategy_entry_price":float(req.strategy_entry_price),
            "testnet_mid":testnet_mid,
            "size":size,
            "entry_price":entry_price,
            "stop_loss":stop_loss,
            "take_profit":take_profit,
            "stop_loss_pct":float(req.stop_loss_pct),
            "take_profit_pct":float(req.take_profit_pct),
            "risk_gate":approved,
            "representative_forward_pnl":False,
            "exchange_result":result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500,detail=str(exc))


@app.post("/testnet_smoke_bracket")
def testnet_smoke_bracket(req: TestnetSmokeBracketRequest, _: bool = Depends(require_token)):
    """
    Dedicated TESTNET-only execution smoke route.
    Uses live Testnet prices directly and DOES NOT alter/bypass the production
    Mainnet->Testnet parity gate used by /place_bracket_order.
    Hard-capped to <= $15 notional.
    """
    if NETWORK != "testnet":
        raise HTTPException(status_code=403,detail={"error":"TESTNET_ONLY"})
    if not EXECUTION_ENABLED:
        raise HTTPException(status_code=403,detail={"error":"EXECUTION_DISABLED"})
    if KILL_SWITCH:
        raise HTTPException(status_code=403,detail={"error":"KILL_SWITCH"})

    coin=req.coin.strip().upper()
    if coin!="BTC":
        raise HTTPException(status_code=400,detail="Smoke route is BTC-only")

    ensure_flat_and_no_open_orders()
    mid=_testnet_mid(coin)
    notional=min(float(req.notional_usd),15.0,MAX_NOTIONAL_USD)
    qty=math.floor((notional/mid)*100000.0)/100000.0
    if qty<0.00001:
        raise HTTPException(status_code=409,detail={"error":"QTY_TOO_SMALL","mid":mid})

    is_buy=bool(req.is_buy)
    entry_slippage=0.005
    if is_buy:
        entry_price=_quantize_hl_price(coin,mid*(1.0+entry_slippage),"up")
        stop_loss=_quantize_hl_price(coin,mid*0.99,"down")
        take_profit=_quantize_hl_price(coin,mid*1.02,"up")
    else:
        entry_price=_quantize_hl_price(coin,mid*(1.0-entry_slippage),"down")
        stop_loss=_quantize_hl_price(coin,mid*1.01,"up")
        take_profit=_quantize_hl_price(coin,mid*0.98,"down")

    approved=validate_order(OrderRequest(
        coin=coin,is_buy=is_buy,size=qty,limit_price=entry_price
    ))
    exit_is_buy=not is_buy
    orders=[
        {"coin":coin,"is_buy":is_buy,"sz":qty,"limit_px":entry_price,
         "order_type":{"limit":{"tif":"Ioc"}},"reduce_only":False},
        {"coin":coin,"is_buy":exit_is_buy,"sz":qty,"limit_px":take_profit,
         "order_type":{"trigger":{"triggerPx":take_profit,"isMarket":True,"tpsl":"tp"}},
         "reduce_only":True},
        {"coin":coin,"is_buy":exit_is_buy,"sz":qty,"limit_px":stop_loss,
         "order_type":{"trigger":{"triggerPx":stop_loss,"isMarket":True,"tpsl":"sl"}},
         "reduce_only":True},
    ]
    try:
        result=exchange.bulk_orders(orders,grouping="normalTpsl")
        statuses=[]
        if isinstance(result,dict):
            statuses=result.get("response",{}).get("data",{}).get("statuses",[])
        errors=[s.get("error") for s in statuses if isinstance(s,dict) and s.get("error")]
        if errors:
            raise HTTPException(status_code=502,detail={
                "error":"HYPERLIQUID_ORDER_REJECTED",
                "reasons":errors,
                "exchange_result":result,
            })
        return {
            "ok":True,"network":NETWORK,"mode":"TESTNET_SMOKE_BRACKET",
            "coin":coin,"side":"BUY" if is_buy else "SELL",
            "mid":mid,"size":qty,"notional_usd":round(qty*entry_price,2),
            "entry_price":entry_price,"stop_loss":stop_loss,
            "take_profit":take_profit,"risk_gate":approved,
            "exchange_result":result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500,detail=str(exc))


@app.post("/close_testnet_position")
def close_testnet_position(req: TestCloseRequest, _: bool = Depends(require_token)):
    """
    TESTNET-only emergency/validation close.
    Cancels open orders for the selected coin, then closes the live Testnet
    position with an aggressive IOC reduce-only limit.
    """
    if NETWORK != "testnet":
        raise HTTPException(status_code=403, detail={"error":"TESTNET_ONLY"})
    if not EXECUTION_ENABLED:
        raise HTTPException(
            status_code=403,
            detail={"error":"EXECUTION_DISABLED","reason":"Server-side Testnet execution is not armed"},
        )
    if KILL_SWITCH:
        raise HTTPException(
            status_code=403,
            detail={"error":"KILL_SWITCH","reason":"Kill switch is ON"},
        )

    coin=req.coin.strip().upper()
    if coin not in ALLOWED_COINS:
        raise HTTPException(status_code=400, detail="Coin is not allowed")

    try:
        # Cancel all resting protective/open orders for this coin first.
        cancelled=[]
        for order in execution_info.open_orders(ACCOUNT_ADDRESS):
            if str(order.get("coin","")).strip().upper()!=coin:
                continue
            oid=order.get("oid")
            if oid is None:
                continue
            try:
                cancelled.append(exchange.cancel(coin,int(oid)))
            except Exception as exc:
                cancelled.append({"oid":oid,"error":str(exc)})

        state=execution_info.user_state(ACCOUNT_ADDRESS)
        position=None
        for wrapped in state.get("assetPositions",[]):
            p=wrapped.get("position",{})
            if str(p.get("coin","")).strip().upper()!=coin:
                continue
            try:
                szi=float(p.get("szi") or 0)
            except (TypeError,ValueError):
                szi=0.0
            if szi!=0:
                position={"szi":szi,"entryPx":p.get("entryPx")}
                break

        if not position:
            return {"ok":True,"network":NETWORK,"status":"ALREADY_FLAT","cancelled":cancelled}

        szi=float(position["szi"])
        size=abs(szi)
        mid=_testnet_mid(coin)
        # Cross by 1% on Testnet only; reduce_only prevents exposure growth.
        if szi>0:
            is_buy=False
            limit_px=_quantize_hl_price(coin,mid*0.99,"down")
        else:
            is_buy=True
            limit_px=_quantize_hl_price(coin,mid*1.01,"up")

        result=exchange.order(
            coin,is_buy,size,limit_px,{"limit":{"tif":"Ioc"}},True
        )

        time.sleep(0.8)
        state2=execution_info.user_state(ACCOUNT_ADDRESS)
        remaining=0.0
        for wrapped in state2.get("assetPositions",[]):
            p=wrapped.get("position",{})
            if str(p.get("coin","")).strip().upper()==coin:
                try: remaining=float(p.get("szi") or 0)
                except (TypeError,ValueError): remaining=0.0
                break

        return {
            "ok":remaining==0.0,
            "network":NETWORK,
            "status":"FLAT" if remaining==0.0 else "POSITION_REMAINS",
            "coin":coin,
            "closed_size":size,
            "remaining_szi":remaining,
            "limit_px":limit_px,
            "cancelled":cancelled,
            "exchange_result":result,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500,detail=str(exc))


@app.post("/cancel_order")
def cancel_order(req: CancelRequest, _: bool = Depends(require_token)):
    try:
        return exchange.cancel(req.coin.strip().upper(), req.oid)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))