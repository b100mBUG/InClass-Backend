# Lesson Attendance Tracker — Backend

GPS-based attendance system. Lecturer's phone is the truth centre.

## Stack
- **FastAPI** — API framework
- **SQLAlchemy 2** — ORM
- **Pydantic v2** — schema validation
- **passlib + jose** — auth (bcrypt + JWT)
- **geopy (haversine)** — distance calculation

---

## Project Structure

```
app/
├── main.py                    # FastAPI app + CORS + router mount
├── core/
│   ├── config.py              # Settings (env vars)
│   └── security.py            # JWT, password hashing, auth dependencies
├── db/
│   └── session.py             # SQLAlchemy engine + get_db dependency
├── models/
│   ├── user.py                # User (lecturer / student)
│   └── attendance.py          # AttendanceSession + AttendanceRecord
├── schemas/
│   ├── user.py                # UserCreate, UserRead, Token
│   └── attendance.py          # SessionCreate/Read, MarkAttendance, Reports
├── services/
│   ├── geo.py                 # Haversine distance calculation
│   ├── auth_service.py        # register / login logic
│   └── attendance_service.py  # All attendance business logic
└── api/v1/endpoints/
    ├── auth.py                # POST /register  POST /login
    ├── sessions.py            # Lecturer session management
    └── attendance.py          # Student mark-present + history
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
| POST | `/api/v1/sessions` | Open a session (capture GPS) |
| POST | `/api/v1/sessions/{id}/close` | Close session early |
| GET | `/api/v1/sessions` | List my sessions with counts |
| GET | `/api/v1/sessions/{id}/report` | Full attendance report |

### Attendance (Student)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/attendance/active-sessions` | Browse open sessions |
| POST | `/api/v1/attendance/mark` | Mark present (send GPS) |
| GET | `/api/v1/attendance/my-history` | View own attendance history |

---

## How It Works

1. **Lecturer** logs in → opens a session with their GPS coordinates + time window (default 15 min)
2. **Student** logs in → sees active sessions → taps "Mark Present" → phone sends GPS
3. **Backend** computes Haversine distance between lecturer & student GPS
4. If distance ≤ `MAX_DISTANCE_METERS` (default 50m) → **PRESENT**, else → **REJECTED**
5. Session auto-expires after the window; lecturer can also close it manually

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
| `DATABASE_URL` | sqlite | Postgres recommended for prod |
| `SECRET_KEY` | — | Change in production! |
| `MAX_DISTANCE_METERS` | 50 | Radius around lecturer allowed |
| `SESSION_WINDOW_MINUTES` | 15 | How long students can mark attendance |

## Production Notes
- Replace `Base.metadata.create_all()` in `main.py` with **Alembic migrations**
- Wire `expire_stale_sessions()` to **APScheduler** or a cron job
- Tighten `allow_origins` in CORS middleware
- Use **PostgreSQL** instead of SQLite
