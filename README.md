# Trading Bot for Binance Futures Testnet

Production-oriented CLI trading bot for Binance USDT-M Futures Testnet. The implementation uses direct REST calls with `requests`, HMAC-SHA256 signing, exchange metadata validation, structured logging, and a small but explicit CLI surface.

## Architecture

```text
CLI (cli.py)
  -> Validators (pure input normalization and fast failure)
  -> OrderService (order construction + symbol filter checks)
  -> BinanceFuturesClient (auth, signing, retries, HTTP)
  -> Binance Futures Testnet REST API
```

Implemented behaviors include MARKET-order poll-and-confirm handling and a pre-order depth snapshot for diagnostics.

## Project Layout

```text
trading_bot/
  bot/
    __init__.py
    client.py
    orders.py
    validators.py
    logging_config.py
    exceptions.py
  cli.py
  tests/
    test_validators.py
    test_client.py
  logs/
    .gitkeep
  .env.example
  README.md
  requirements.txt
  .gitignore
```

## Setup

1. Create a Binance Futures Testnet account and enable Futures Testnet access.
2. Generate a Testnet API key and secret from Binance Futures Testnet.
3. Clone the repository and open the `trading_bot` folder.
4. Create and activate a virtual environment.
5. Install dependencies with `pip install -r requirements.txt`.
6. Copy `.env.example` to `.env` and set:

```env
BINANCE_API_KEY=your_testnet_api_key_here
BINANCE_API_SECRET=your_testnet_api_secret_here
```

The CLI loads `.env` automatically through `python-dotenv`.

## Runnable Examples

Market buy:

```bash
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001
```

Limit sell:

```bash
python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.001 --price 72000
```

Bonus stop-limit order:

```bash
python cli.py --symbol BTCUSDT --side SELL --type STOP_LIMIT --quantity 0.001 --price 71500 --stop-price 71000
```

If you omit required arguments, the CLI falls back to interactive prompts.

## Exit Codes

- `0`: Success
- `1`: Validation error, including malformed input or symbol filter violations
- `2`: Binance API error, including insufficient balance, invalid symbol, or rate limit exhaustion
- `3`: Network error, including timeout or connection failure

## Error Handling Notes

- Missing API credentials are surfaced explicitly before any signed request is sent.
- Invalid symbols are rejected before order submission.
- Quantity and price are validated against the symbol's `LOT_SIZE` and `PRICE_FILTER` values from `exchangeInfo`.
- Binance rate-limit responses are retried with basic exponential backoff.
- Raw tracebacks are written to the rotating log file, not shown to the user.

## Assumptions

- Only USDT-margined symbols are supported.
- Order quantities and prices must satisfy Binance symbol filters exactly; no automatic rounding is applied.
- Stop-limit orders are sent using Binance Futures `STOP` order parameters with both `price` and `stopPrice`.
- OCO orders are out of scope because the bot is intentionally limited to the three requested order types.
- `--testnet` is enabled by default; a hidden `--mainnet` switch exists only for local experimentation.
- MARKET orders on Binance Futures Testnet (USDT-M) were observed to return status=NEW with executedQty=0 immediately after the initial order placement response, before settling to status=FILLED shortly after (typically within ~1-2 seconds). To handle this reliably, the bot polls GET /fapi/v1/order up to 3 times (500ms apart) after placing a MARKET order, and reports the final settled state to the console and log file rather than the initial POST response. The bot also logs a pre-order snapshot of top-of-book bid/ask depth (via GET /fapi/v1/depth) for diagnostic visibility into liquidity conditions at order time.

## Testing

Run the test suite with:

```bash
pytest tests/ -v
```

The tests mock HTTP calls and do not touch the live API.

## Sample Log Output

```text
2026-07-04 12:00:00,123 | INFO | orders | Order request summary: symbol=BTCUSDT side=BUY type=MARKET quantity=0.001 price=N/A stopPrice=N/A timeInForce=N/A
2026-07-04 12:00:00,456 | INFO | client | Response received: method=POST endpoint=/fapi/v1/order status=200
2026-07-04 12:00:00,456 | INFO | orders | Order response summary: {'orderId': 12345, 'status': 'FILLED', 'symbol': 'BTCUSDT', 'side': 'BUY', 'type': 'MARKET', 'executedQty': '0.001', 'avgPrice': '27300.10', 'origQty': '0.001', 'price': '0'}
```

## Sample Terminal Transcripts

### Successful MARKET Order

```text
$ python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001
ORDER REQUEST
-------------
Symbol    : BTCUSDT
Side      : BUY
Type      : MARKET
Quantity  : 0.001
Price     : N/A
Stop Price: N/A
Testnet   : yes

ORDER RESPONSE
--------------
Order ID     : 12345
Status       : FILLED
Symbol       : BTCUSDT
Side         : BUY
Type         : MARKET
Executed Qty : 0.001
Avg Price    : 27300.10
Orig Qty     : 0.001
Price        : 0
```

Log file entries:

```text
2026-07-04 12:00:00,123 | INFO | orders | Order request summary: symbol=BTCUSDT side=BUY type=MARKET quantity=0.001 price=N/A stopPrice=N/A timeInForce=N/A
2026-07-04 12:00:00,456 | INFO | client | Response received: method=POST endpoint=/fapi/v1/order status=200
2026-07-04 12:00:00,456 | INFO | orders | Order response summary: {'orderId': 12345, 'status': 'FILLED', 'symbol': 'BTCUSDT', 'side': 'BUY', 'type': 'MARKET', 'executedQty': '0.001', 'avgPrice': '27300.10', 'origQty': '0.001', 'price': '0'}
```

### Successful LIMIT Order

```text
$ python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.001 --price 72000
ORDER REQUEST
-------------
Symbol    : BTCUSDT
Side      : SELL
Type      : LIMIT
Quantity  : 0.001
Price     : 72000
Stop Price: N/A
Testnet   : yes

ORDER RESPONSE
--------------
Order ID     : 12346
Status       : NEW
Symbol       : BTCUSDT
Side         : SELL
Type         : LIMIT
Executed Qty : 0
Avg Price    : N/A
Orig Qty     : 0.001
Price        : 72000
```

Log file entries:

```text
2026-07-04 12:01:00,123 | INFO | orders | Order request summary: symbol=BTCUSDT side=SELL type=LIMIT quantity=0.001 price=72000 stopPrice=N/A timeInForce=GTC
2026-07-04 12:01:00,456 | INFO | client | Response received: method=POST endpoint=/fapi/v1/order status=200
2026-07-04 12:01:00,456 | INFO | orders | Order response summary: {'orderId': 12346, 'status': 'NEW', 'symbol': 'BTCUSDT', 'side': 'SELL', 'type': 'LIMIT', 'executedQty': '0', 'avgPrice': 'N/A', 'origQty': '0.001', 'price': '72000'}
```
