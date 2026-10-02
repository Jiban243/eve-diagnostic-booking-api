from fastapi import FastAPI

from app.routers import auth, bookings, catalogue, payments


app = FastAPI(
    title="EVE Diagnostic Booking API",
    version="0.1.0",
)

app.include_router(auth.router)
app.include_router(catalogue.router)
app.include_router(bookings.router)
app.include_router(payments.router)


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}

