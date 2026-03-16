# Lesson Attendance Tracker — Backend

GPS + rotating QR-based attendance system. Built with FastAPI.

## Stack
- **FastAPI** — API framework
- **SQLAlchemy 2** — ORM
- **Pydantic v2** — schema validation
- **passlib + jose** — auth (bcrypt + JWT)
- **APScheduler** — background QR token rotation (every 30s)
- **qrcode + Pillow** — QR image generation
- **geopy (haversine)** — distance calculation

---

## How Attendance Verification Works

Every mark-attendance request passes through **4 layers in order**:

| Layer | Check | Failure behaviour |
|-------|-------|-------------------|
| 1 | **QR token** — student must submit the token from the current rotating QR code | Hard reject (400) |
| 2 | **Session expiry** — attendance window must still be open | Hard reject (410) |
| 3 | **Duplicate guard** — student can only mark once per session | Hard reject (409) |
| 4 | **GPS radius** — student must be within `MAX_DISTANCE_METERS` of the lecturer | Saved as REJECTED record |

Layer 4 saves a REJECTED record rather than erroring so the lecturer can see who attempted to mark from outside the room.

---

## QR Code Rotation

- When a lecturer opens a session, the **first QR token is generated immediately**.
- **APScheduler** runs a background job every `QR_ROTATION_INTERVAL_SECONDS` (default: **30 seconds**) that replaces all active-session tokens simultaneously.
- Tokens have a lifetime of `QR_TOKEN_LIFETIME_SECONDS` (default: **45 seconds**) — slightly longer than the rotation interval to absorb scheduler lag.
- The lecturer's frontend should poll `GET /api/v1/qr/{session_id}` on the same 30-second interval to always display a fresh PNG.
- A student **cannot** share the QR via screenshot to an absent friend — the token will have rotated before it can be submitted.

---

## Project Structure

```
app/
├── main.py                    # FastAPI app + CORS + APScheduler lifespan
├── core/
│   ├── config.py              # Settings (env vars, QR rotation config)
│   └── security.py            # JWT, password hashing, auth dependencies
├── db/
│   └── session.py             # SQLAlchemy engine + get_db dependency
├── models/
│   ├── user.py                # User (lecturer / student)
│   ├── attendance.py          # AttendanceSession + AttendanceRecord
│   └── qr.py                  # QRToken (one per active session, rotates)
├── schemas/
│   ├── user.py                # UserCreate, UserRead, Token
│   └── attendance.py          # SessionCreate/Read, MarkAttendance (+qr_token), Reports
├── services/
│   ├── geo.py                 # Haversine distance calculation
│   ├── auth_service.py        # register / login logic
│   ├── attendance_service.py  # All attendance business logic (4-layer verification)
│   └── qr_service.py          # QR token generation, rotation, validation, image
└── api/v1/endpoints/
    ├── auth.py                # POST /register  POST /login
    ├── sessions.py            # Lecturer session management
    ├── attendance.py          # Student mark-present + history
    └── qr.py                  # GET /qr/{id} (PNG)  GET /qr/{id}/meta (JSON)
```

---

## API Endpoints

### Auth
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Register lecturer or student |
| POST | `/api/v1/auth/login` | Login → JWT token |

### Sessions (Lecturer)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/sessions` | Open a session (capture GPS, generate first QR token) |
| POST | `/api/v1/sessions/{id}/close` | Close session early |
| GET | `/api/v1/sessions` | List my sessions with attendance counts |
| GET | `/api/v1/sessions/{id}/report` | Full attendance report |

### QR Codes (Lecturer)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/qr/{id}` | Current QR code as PNG image (poll every 30s) |
| GET | `/api/v1/qr/{id}/meta` | Token metadata: created_at, expires_at, token_hint |

### Attendance (Student)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/attendance/active-sessions` | Browse open sessions |
| POST | `/api/v1/attendance/mark` | Mark present (send QR token + GPS) |
| GET | `/api/v1/attendance/my-history` | View own attendance history |

---

## Mark Attendance Request

```json
{
  "session_id": 1,
  "qr_token": "a3f1b2c4d5e6f7a8b9c0d1e2f3a4b5c6",
  "student_latitude": -0.3045,
  "student_longitude": 36.0812
}
```

`qr_token` is the 32-character hex string the student's app reads from scanning the QR code.

---

## Setup

```bash
cp .env.example .env          # fill in your values
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Interactive docs: http://localhost:8000/docs

## Configuration (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | sqlite | Postgres recommended for production |
| `SECRET_KEY` | — | Change in production! |
| `MAX_DISTANCE_METERS` | 50 | GPS radius around lecturer |
| `SESSION_WINDOW_MINUTES` | 15 | How long students can mark attendance |
| `QR_TOKEN_LIFETIME_SECONDS` | 45 | How long each QR token stays valid |
| `QR_ROTATION_INTERVAL_SECONDS` | 30 | How often the scheduler rotates tokens |

## Running Tests

```bash
pytest tests/ -v
```

## Production Notes
- Replace `Base.metadata.create_all()` with **Alembic migrations**
- Switch `DATABASE_URL` to **PostgreSQL**
- Tighten `allow_origins` in CORS middleware to your frontend domain
- The scheduler runs in-process — for multi-worker deployments (Gunicorn), move rotation to a dedicated **Celery beat** worker or a database-level cron job to avoid duplicate rotations
