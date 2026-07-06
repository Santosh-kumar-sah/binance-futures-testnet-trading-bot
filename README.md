# Trading Bot for Binance Futures Testnet

Small CLI trading bot for Binance USDT-M Futures Testnet. It signs requests with HMAC-SHA256, validates symbol filters before order submission, retries selected API failures, and writes structured logs for troubleshooting.

## What It Does

- Places `MARKET`, `LIMIT`, and `STOP_LIMIT` orders.
- Validates quantity and price against Binance exchange filters.
- Prompts interactively for any missing required inputs.
- Polls MARKET orders after submission so the console shows the settled result instead of the first transient response.
- Captures a pre-order depth snapshot in the logs for extra context.

## Project Layout

```text
trading_bot/
  bot/
    client.py
    orders.py
    validators.py
    logging_config.py
    exceptions.py
  cli.py
  check_order.py
  demo_error_cases.py
  logs/
  tests/
  .env.example
  README.md
  requirements.txt
```

## Requirements

- Python environment with the dependencies from `requirements.txt`.
- Binance Futures Testnet API key and secret.
- A `.env` file with credentials or the ability to enter them when prompted.

## Setup

1. Create or activate your virtual environment.
2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in your Testnet credentials.

```env
BINANCE_API_KEY=your_testnet_api_key_here
BINANCE_API_SECRET=your_testnet_api_secret_here
```

4. Run the CLI from the project root so imports like `bot.*` resolve correctly.

## Usage

The CLI accepts arguments, then falls back to prompts if required values are missing.

```bash
python cli.py --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001
python cli.py --symbol BTCUSDT --side SELL --type LIMIT --quantity 0.001 --price 72000
python cli.py --symbol BTCUSDT --side SELL --type STOP_LIMIT --quantity 0.001 --price 71500 --stop-price 71000
```

Supported flags:

- `--symbol` for the trading pair, for example `BTCUSDT`.
- `--side` for `BUY` or `SELL`.
- `--type` for `MARKET`, `LIMIT`, or `STOP_LIMIT`.
- `--quantity` for order size.
- `--price` for `LIMIT` and `STOP_LIMIT` orders.
- `--stop-price` for `STOP_LIMIT` orders.
- `--testnet` is enabled by default; `--mainnet` exists only for local experimentation and is hidden from help output.

## Testing

Run the test suite from the project root:

```bash
d:/Bot/.venv/Scripts/python.exe -m pytest tests -v
```

The tests mock HTTP calls, so they do not hit the live Binance API.

## Logging

Runtime logs are written under `logs/`. Sensitive values are redacted, and stack traces stay in the log file rather than being printed directly to the console.

## Exit Codes

- `0`: Success.
- `1`: Validation error, including malformed input or symbol filter failures.
- `2`: Binance API error, including insufficient balance, invalid symbol, or rate limiting.
- `3`: Network error, including timeout or connection failure.

## Notes

- Only USDT-margined symbols are supported.
- Order quantities and prices must already satisfy Binance filters; the bot does not round values automatically.
- Stop-limit orders are submitted with Binance Futures `STOP` parameters using both `price` and `stopPrice`.
- Missing credentials are handled before any signed request is sent.
- The codebase includes focused tests for validators, client behavior, and MARKET-order polling.
