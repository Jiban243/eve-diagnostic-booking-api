# EVE Diagnostic Booking API

A FastAPI backend for diagnostic test bookings, JWT authentication,
simulated payments, and idempotent payment webhooks.

## Technology

- Python and FastAPI
- Pydantic request validation
- PostgreSQL and SQLAlchemy
- Alembic migrations
- PyJWT authentication
- Argon2 password hashing through pwdlib
- pytest and FastAPI TestClient

## Features

- User signup, login, and JWT authentication.
- Admin-only catalogue creation and updates.
- Public retrieval of centres, tests, and available offerings.
- Centre-specific prices and currencies.
- Authenticated bookings with ownership checks.
- Server-calculated booking amounts.
- Simulated successful and failed payments.
- Authenticated, idempotent payment webhooks.
- Transactional payment updates and database row locking.
- Pagination and interactive Swagger documentation.

## Local setup

Run commands from the project root.

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On Windows, activate with:

```powershell
.venv\Scripts\Activate.ps1
```

### 2. Set up PostgreSQL

Start PostgreSQL and connect using a database administrator account:

```bash
psql postgres
```

Create the role and databases:

```sql
CREATE ROLE eve_user WITH LOGIN;
\password eve_user
CREATE DATABASE eve_db OWNER eve_user;
CREATE DATABASE eve_test OWNER eve_user;
\q
```

Skip creation of any role or database that already exists.

### 3. Configure the environment

```bash
cp .env.example .env
```

Set the following values:

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

Generate each secret separately:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Do not commit `.env`.

### 4. Apply migrations and start the server

```bash
python -m alembic upgrade head
python -m uvicorn app.main:app --reload
```

- Swagger: http://127.0.0.1:8000/docs
- ReDoc: http://127.0.0.1:8000/redoc
- Health: http://127.0.0.1:8000/health

The health endpoint reports application availability, not database readiness.

## Authentication and admin setup

Register through `POST /auth/signup`:

```json
{
  "name": "Demo User",
  "email": "demo@example.com",
  "password": "DemoPassword123!"
}
```

Log in through `POST /auth/login`:

```json
{
  "email": "demo@example.com",
  "password": "DemoPassword123!"
}
```

In Swagger, click **Authorize** and paste only the returned
`access_token` value. Page refreshes may clear Swagger authorization.

Outside Swagger, send:

```http
Authorization: Bearer YOUR_ACCESS_TOKEN
```

Signup creates ordinary users. To create an administrator, first register
the intended account, then connect to PostgreSQL:

```bash
psql -h localhost -U eve_user -d eve_db
```

Promote the registered account using its email:

```sql
UPDATE users
SET is_admin = TRUE
WHERE email = 'admin@example.com'
RETURNING id, email, is_admin;
```

Admin privileges cannot be requested through public signup.

## API endpoints

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| GET | `/health` | Public | Application health |
| POST | `/auth/signup` | Public | Register |
| POST | `/auth/login` | Public | Obtain JWT |
| GET | `/auth/me` | Authenticated | Current user |
| POST | `/centres` | Admin | Create centre |
| GET | `/centres` | Public | List centres |
| GET | `/centres/{centre_id}` | Public | Retrieve centre |
| PUT | `/centres/{centre_id}` | Admin | Update centre |
| POST | `/tests` | Admin | Create diagnostic test |
| GET | `/tests` | Public | List tests |
| PUT | `/tests/{test_id}` | Admin | Update test |
| POST | `/centres/{centre_id}/tests` | Admin | Create offering |
| GET | `/centres/{centre_id}/tests` | Public | List active offerings |
| PUT | `/centres/{centre_id}/tests/{offering_id}` | Admin | Update offering |
| POST | `/bookings/` | Authenticated | Create booking |
| GET | `/bookings/` | Authenticated | List own bookings |
| GET | `/bookings/{booking_id}` | Owner | Retrieve booking |
| POST | `/payments/` | Owner | Simulate payment |
| POST | `/payments/webhook/` | Webhook secret | Process payment event |

List endpoints accept `limit` and `offset`.
The default limit is 50; the maximum is 100.

## Example booking and payment workflow

Use the IDs returned by your requests; the IDs below are examples.

### 1. Create catalogue entries as an admin

`POST /centres`:

```json
{
  "name": "Demo Diagnostics",
  "location": "Delhi"
}
```

`POST /tests`:

```json
{
  "name": "CBC"
}
```

`POST /centres/1/tests`:

```json
{
  "test_id": 1,
  "price": "450.00",
  "currency": "INR"
}
```

### 2. Book as an authenticated user

`POST /bookings/`:

```json
{
  "offering_id": 1,
  "appointment_at": "2030-10-04T10:00:00+05:30"
}
```

Use a future appointment time with a timezone offset.

The server determines the user from the JWT and copies the price and
currency from the offering. The initial booking status is `PENDING`.

### 3. Simulate a payment

`POST /payments/`:

```json
{
  "booking_id": 1,
  "outcome": "SUCCESS"
}
```

| Payment outcome | Resulting booking status |
|---|---|
| `SUCCESS` | `CONFIRMED` |
| `FAILED` | `FAILED` |

To demonstrate failure, create another booking and submit its ID with
`"outcome": "FAILED"`.

A recorded simulated failure returns HTTP 200: the API successfully
processed the requested outcome.

Save the returned `provider_reference`.

### 4. Send a webhook

`POST /payments/webhook/` requires this header:

```http
X-Webhook-Secret: YOUR_WEBHOOK_SECRET
```

Body:

```json
{
  "event_id": "evt_demo_001",
  "provider_reference": "REPLACE_WITH_RETURNED_PAYMENT_UUID",
  "status": "SUCCESS"
}
```

Replace the reference placeholder with the actual payment UUID.

The first accepted event returns `duplicate: false`.
An identical repeated event returns `duplicate: true`.

Webhook authentication is independent of user JWT authentication.

## Database design

| Table | Purpose |
|---|---|
| `users` | Accounts, password hashes, admin privileges |
| `diagnostic_centres` | Centre names and locations |
| `diagnostic_tests` | Test catalogue |
| `centre_tests` | Centre/test associations, prices, currencies, availability |
| `bookings` | User, offering, appointment, price snapshot, status |
| `payments` | One simulated payment per booking |
| `webhook_events` | Accepted event IDs and outcomes |

Foreign keys connect bookings to users and offerings, offerings to centres
and tests, payments to bookings, and webhook events to payments.

Unique constraints prevent duplicate centre/test offerings, multiple
payments for one booking, and duplicate webhook event IDs.

Amounts use PostgreSQL `NUMERIC` and Python `Decimal`.
Check constraints validate positive amounts and supported statuses.

A booking stores its amount and currency at creation so later catalogue
price changes do not change the booked amount.

## Payment consistency and idempotency

- Repeating a payment request with the same outcome returns the existing payment.
- Completed payment outcomes cannot be reversed.
- Reusing a webhook event ID with different contents returns HTTP 409.
- A new event conflicting with a completed payment also returns HTTP 409.
- Payment processing locks booking and payment rows in a consistent order.
- Payment, booking, and accepted event changes share a transaction.
- Failed processing rolls back its changes.

The simulated payment endpoint applies its outcome immediately.
A subsequent matching webhook acknowledges the result.

The webhook handler can also transition an existing pending payment.
Automated tests seed a pending payment to exercise that transition directly.

## Error handling

| Status | Examples |
|---|---|
| 401 | Missing/invalid token, incorrect login, invalid webhook credentials |
| 403 | Non-admin attempts catalogue modification |
| 404 | Missing resource or another user's booking |
| 409 | Duplicate record, unavailable offering, conflicting payment/event |
| 422 | Invalid fields, invalid IDs, past or timezone-free appointment |

## Tests

Create `eve_test` with `eve_user` as owner, then run:

```bash
python -m pytest tests/ -q
```

Tests use the configured PostgreSQL host, port, and credentials but select
the separate `eve_test` database explicitly.

Tables are created from SQLAlchemy metadata. Each test's changes are
rolled back through an outer transaction, including API-handler commits.
The suite does not validate migration generation.

Eight cases cover:

- Signup, login, duplicate email, and incorrect passwords.
- Authentication and admin restrictions.
- Booking prices and ownership.
- Invalid booking inputs and client-supplied price rejection.
- Successful and failed payments, repeated requests, and conflicting outcomes.
- Webhook authentication, state transitions, duplicates, and conflict rollback.

Local result: **8 passed**.

## Assumptions and scope

- Payments are simulated; no real gateway is integrated.
- Clients choose the mock outcome for reproducible demonstrations.
- Bookings belong to the authenticated user; separate patient profiles are omitted.
- Each booking has one payment. A failed payment requires a new booking to try again.
- Future appointment times are required, but opening hours and slot capacity are not modelled.
- `CANCELLED` is reserved in the status model; cancellation has no exposed endpoint.
- Webhooks reference existing payments.
- Webhook authentication uses a shared secret rather than provider-specific signatures.
- Currency codes require three uppercase letters but are not checked against a currency registry.
- Concurrency and load testing are outside this submission's automated test scope.

## What I would improve with more time

1. Add concurrent-request integration tests for simultaneous payments and webhook deliveries.
2. Add CI checks that apply Alembic migrations to a fresh PostgreSQL database and run tests.
3. Add appointment availability and capacity rules, with transactional protection against overbooking.
4. Model payment attempts separately to support controlled retries after failed payments.
5. Add provider-specific webhook signatures and timestamp validation for a real integration.
6. Add structured logs with request/event IDs, excluding credentials and sensitive data.
7. Add rate limits to authentication endpoints and a database-readiness endpoint.
8. Add Docker Compose to simplify reproducible local setup.

These are future improvements, not implemented features.

