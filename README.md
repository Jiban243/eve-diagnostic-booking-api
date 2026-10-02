# EVE Diagnostic Booking API

A FastAPI backend for user authentication, diagnostic centre and test catalogues, bookings, simulated payments, and idempotent payment webhooks.

## Technology

- Python
- FastAPI and Pydantic
- PostgreSQL
- SQLAlchemy
- Alembic
- PyJWT
- Argon2 password hashing through pwdlib
- pytest and FastAPI TestClient

## Features

- User signup, login, and JWT authentication.
- Admin-only creation and updates of centres, tests, and centre-specific offerings.
- Public catalogue retrieval with pagination.
- Authenticated booking creation and retrieval.
- Booking ownership checks.
- Server-calculated booking prices.
- Simulated successful and failed payments.
- Webhook authentication through a shared secret.
- Duplicate webhook detection and conflicting-event rejection.
- Database transactions and row locks for payment updates.

## Local setup

Run commands from the project root.

### 1. Create the Python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate with:

```powershell
.venv\Scripts\Activate.ps1
```

### 2. Configure PostgreSQL

Start PostgreSQL and connect using a database administrator account:

```bash
psql postgres
```

Create the application role and databases:

```sql
CREATE ROLE eve_user WITH LOGIN;
\password eve_user
CREATE DATABASE eve_db OWNER eve_user;
CREATE DATABASE eve_test OWNER eve_user;
\q
```

The password command prompts for a password without putting it directly in the SQL statement. Skip creation of any role or database that already exists.

### 3. Configure environment variables

Copy the example configuration:

```bash
cp .env.example .env
```

Populate these values in `.env`:

```dotenv
DB_HOST=localhost
DB_PORT=5432
DB_NAME=eve_db
DB_USER=eve_user
DB_PASSWORD=replace_with_your_database_password
JWT_SECRET=replace_with_a_random_secret_at_least_32_characters
ACCESS_TOKEN_EXPIRE_MINUTES=60
WEBHOOK_SECRET=replace_with_a_different_random_secret_at_least_32_characters
```

Generate a secret with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Run it separately for the JWT and webhook secrets.

Do not commit `.env`.

### 4. Apply migrations

```bash
python -m alembic upgrade head
```

### 5. Start the API

```bash
python -m uvicorn app.main:app --reload
```

- Swagger UI: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- Health endpoint: http://127.0.0.1:8000/health

The health endpoint reports application availability; it does not check database connectivity.

## Authentication

1. Create a user through `POST /auth/signup`.
2. Log in through `POST /auth/login`.
3. Copy the returned `access_token`.
4. In Swagger, click **Authorize** and paste only the token value.

For requests outside Swagger, send:

```http
Authorization: Bearer YOUR_ACCESS_TOKEN
```

Swagger authorization may be cleared when the page is refreshed.

Passwords are hashed with Argon2. Signup creates ordinary users and does not grant admin access.

### Creating an administrator

First create the intended admin account through signup.

Then connect to the application database:

```bash
psql -h localhost -U eve_user -d eve_db
```

Promote the account, replacing the example email with the registered email:

```sql
UPDATE users
SET is_admin = TRUE
WHERE email = 'admin@example.com'
RETURNING id, email, is_admin;
```

Admin privileges are managed through database access, not public signup.

## API endpoints

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| GET | `/health` | Public | Application health |
| POST | `/auth/signup` | Public | Register |
| POST | `/auth/login` | Public | Obtain a JWT |
| GET | `/auth/me` | Authenticated | Current user |
| POST | `/centres` | Admin | Create a centre |
| GET | `/centres` | Public | List centres |
| GET | `/centres/{centre_id}` | Public | Retrieve a centre |
| PUT | `/centres/{centre_id}` | Admin | Update a centre |
| POST | `/tests` | Admin | Create a diagnostic test |
| GET | `/tests` | Public | List diagnostic tests |
| PUT | `/tests/{test_id}` | Admin | Update a test |
| POST | `/centres/{centre_id}/tests` | Admin | Create a priced offering |
| GET | `/centres/{centre_id}/tests` | Public | List active offerings |
| PUT | `/centres/{centre_id}/tests/{offering_id}` | Admin | Update price, currency, and availability |
| POST | `/bookings/` | Authenticated | Create a booking |
| GET | `/bookings/` | Authenticated | List own bookings |
| GET | `/bookings/{booking_id}` | Owner | Retrieve a booking |
| POST | `/payments/` | Owner | Simulate a payment |
| POST | `/payments/webhook/` | Webhook secret | Process a payment event |

List endpoints support `limit` and `offset`. The default limit is 50 and the maximum is 100.

## Example workflow

IDs below are examples. Use the IDs returned by your own requests.

### 1. Create catalogue entries as an admin

Create a centre:

```json
{
  "name": "Demo Diagnostics",
  "location": "Delhi"
}
```

Create a test:

```json
{
  "name": "CBC"
}
```

Create an offering through `POST /centres/{centre_id}/tests`:

```json
{
  "test_id": 1,
  "price": "450.00",
  "currency": "INR"
}
```

### 2. Create a booking as a user

Send to `POST /bookings/`:

```json
{
  "offering_id": 1,
  "appointment_at": "2030-10-04T10:00:00+05:30"
}
```

Use a future appointment date with a timezone offset.

The booking starts as `PENDING`. Its amount and currency are copied from the offering by the server. Clients cannot supply their own booking price or user ID.

### 3. Simulate payment

Send to `POST /payments/`:

```json
{
  "booking_id": 1,
  "outcome": "SUCCESS"
}
```

Supported outcomes:

| Payment outcome | Booking status |
|---|---|
| `SUCCESS` | `CONFIRMED` |
| `FAILED` | `FAILED` |

A simulated payment failure returns HTTP 200 because the API successfully records the requested failure outcome.

Save the returned `provider_reference` for webhook requests.

### 4. Send a webhook

Send to `POST /payments/webhook/` with:

```http
X-Webhook-Secret: YOUR_WEBHOOK_SECRET
```

Request body:

```json
{
  "event_id": "evt_demo_001",
  "provider_reference": "REPLACE_WITH_PAYMENT_PROVIDER_REFERENCE",
  "status": "SUCCESS"
}
```

Replace the reference placeholder with the UUID returned by the payment endpoint.

The first accepted event returns `duplicate: false`. Repeating the exact event returns `duplicate: true`.

Webhook authentication uses the configured webhook secret independently of user JWT authentication.

## Payment consistency and idempotency

- Each booking has at most one payment record, enforced by a unique database constraint.
- Repeating a payment request with the same outcome returns the existing payment.
- A completed payment outcome cannot be reversed by a later request.
- Webhook event IDs are unique.
- Reusing an event ID with different contents returns HTTP 409.
- A new webhook event that conflicts with a completed payment also returns HTTP 409.
- Payment, booking, and webhook-event changes are committed in one transaction.
- Failed processing rolls back the transaction.
- Payment processing locks the booking and payment rows in a consistent order.

The simulated payment endpoint applies its outcome immediately. A subsequent matching webhook acknowledges that result. The webhook handler also supports transitioning an existing pending payment, which is exercised by the automated tests.

## Data model

- `users`: accounts, password hashes, and admin privileges.
- `diagnostic_centres`: centre names and locations.
- `diagnostic_tests`: diagnostic test names.
- `centre_tests`: centre/test associations, prices, currencies, and availability.
- `bookings`: user bookings with appointment times and price snapshots.
- `payments`: one simulated payment per booking.
- `webhook_events`: accepted event IDs and outcomes for deduplication.

Prices use decimal values backed by PostgreSQL `NUMERIC`, avoiding binary floating-point arithmetic.

## Error handling

- `401`: missing or invalid authentication, invalid login, or invalid webhook credentials.
- `403`: an ordinary user attempts an admin operation.
- `404`: a resource is missing or a booking belongs to another user.
- `409`: duplicate records, unavailable offerings, or conflicting payment/event states.
- `422`: invalid request fields, invalid IDs, or invalid appointment times.

## Tests

Create `eve_test` with `eve_user` as owner before running:

```bash
python -m pytest tests/ -q
```

The tests use the configured PostgreSQL host, port, and credentials but explicitly select `eve_test`.

Tables are created from SQLAlchemy metadata. Each test runs inside an outer transaction that is rolled back afterward, including changes committed by API handlers. This suite does not validate migration generation.

Eight test cases cover:

- Signup, login, duplicate email, and incorrect passwords.
- Missing/invalid authentication and admin access restrictions.
- Booking prices and ownership restrictions.
- Invalid booking inputs and client-supplied price rejection.
- Successful and failed payments, repeated requests, and conflicting outcomes.
- Webhook authentication, pending-state transitions, duplicate events, and conflict rollback.

Verified locally: **8 passed**.

## Scope and assumptions

- Payments are simulated; no real gateway or money movement is involved.
- The caller selects the simulated outcome to make demonstrations reproducible.
- Bookings are for the authenticated user; separate patient profiles are not implemented.
- One payment is allowed per booking. Failed-payment retries require a new booking.
- Appointment times must be in the future, but centre hours and slot capacity are not modelled.
- `CANCELLED` is reserved in the booking status model; no cancellation endpoint is exposed.
- Webhooks refer to existing payments.
- Webhook authentication uses a shared secret; provider-specific signatures are not implemented.
- Currency codes must contain three uppercase letters; supported currencies are not checked against an external registry.
- Automated concurrency/load testing is outside this submission's test scope.

