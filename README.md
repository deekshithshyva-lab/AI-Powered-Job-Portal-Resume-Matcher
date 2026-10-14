# AI-Powered Job Portal & Resume Matcher: Backend

Django REST Framework backend where applicants upload resumes to job postings and recruiters get applications automatically ranked by how well each resume matches the job. Parsing and NLP scoring run asynchronously in Celery.

## Tech Stack

| Layer | Technology |
|---|---|
| API | Python, Django, Django REST Framework |
| Auth | JWT (`djangorestframework-simplejwt`) |
| Database | PostgreSQL |
| Queue | Celery + Redis |
| NLP | spaCy (cleaning, lemmatization, skill matching), scikit-learn (TF-IDF + cosine similarity) |
| File parsing | `pdfminer.six` (PDF), `python-docx` (DOCX) |

## Architecture

```
Applicant ──POST resume──▶ DRF view ──▶ save Application (PENDING) ──▶ 202 Accepted
                                              │
                                              └─ on_commit ─▶ Redis ─▶ Celery worker
                                                                         │
                          extract text → spaCy clean → TF-IDF cosine → skills
                                                                         │
                                       Application: match_score, extracted_skills, COMPLETED/FAILED
                                              │
Recruiter ──GET /jobs/<id>/applications/──────┘  (sorted by match_score DESC)
```

## Project Layout

```
jobportal_backend/
├── config/
│   ├── __init__.py        # loads the Celery app
│   └── celery.py
├── portal/
│   ├── models.py          # User, JobPosting, Application
│   ├── utils.py           # clean_text, extract_skills, calculate_match_score
│   ├── tasks.py           # process_resume Celery task
│   ├── serializers.py
│   ├── views.py
│   ├── permissions.py
│   └── urls.py
├── settings_snippet.py    # settings to merge into config/settings.py
├── requirements.txt
└── README.md
```

## Quick Start

```bash
# 1. Install
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# 2. Configure: merge settings_snippet.py into config/settings.py, then export env vars
export POSTGRES_PASSWORD=change-me
export REDIS_URL=redis://localhost:6379/0

# 3. Add to config/urls.py
#    path("api/", include("portal.urls")),
#    path("api/token/", TokenObtainPairView.as_view()),

# 4. Migrate  (AUTH_USER_MODEL = "portal.User" must be set BEFORE the first migrate)
python manage.py makemigrations portal
python manage.py migrate
python manage.py createsuperuser

# 5. Run (three terminals)
redis-server
celery -A config worker -l info --concurrency=2
python manage.py runserver
```

## API

| Method | Endpoint | Role | Description |
|---|---|---|---|
| POST | `/api/token/` | any | Obtain JWT |
| GET | `/api/jobs/` | any | List active jobs |
| POST | `/api/jobs/` | Recruiter | Create a job |
| PUT/PATCH/DELETE | `/api/jobs/<id>/` | Owning recruiter | Modify a job |
| POST | `/api/jobs/<id>/applications/` | Applicant | Upload resume, returns **202** |
| GET | `/api/applications/<id>/` | Applicant (own) / Recruiter (own jobs) | Poll parsing status |
| GET | `/api/jobs/<id>/applications/` | Owning recruiter | Ranked applications, optional `?status=` |

### Example

```bash
# Upload a resume (applicant token)
curl -X POST http://localhost:8000/api/jobs/1/applications/ \
  -H "Authorization: Bearer $APPLICANT_TOKEN" \
  -F "resume=@/path/to/resume.pdf"
# 202 → {"id": 7, "job": 1, "job_title": "...", "parsing_status": "pending", "status_url": "..."}

# Ranked list (recruiter token)
curl "http://localhost:8000/api/jobs/1/applications/?status=completed" \
  -H "Authorization: Bearer $RECRUITER_TOKEN"
# → {"results": [{"id": 7, "match_score": 63.42, "extracted_skills": ["django", "python"], ...}]}
```

## How Matching Works

1. **Extract**: text is pulled from the PDF/DOCX (DOCX tables included).
2. **Clean**: spaCy removes URLs, e-mails, stop words, punctuation and numbers, then lemmatizes.
3. **Score**: TF-IDF (unigrams + bigrams, sublinear tf) over the resume and the job's description plus requirements. Cosine similarity is scaled to 0-100 and rounded to 2 decimals.
4. **Skills**: a spaCy `PhraseMatcher` finds known skills. Override the taxonomy with `RESUME_SKILLS` in settings.

Parsing status moves through `pending → processing → completed | failed`. Failures (corrupt file, scanned/image-only PDF) store a human-readable `error_message`.

## Configuration

| Setting / env var | Purpose | Default |
|---|---|---|
| `POSTGRES_DB / USER / PASSWORD / HOST / PORT` | Database | `jobportal` / `jobportal` / required / `localhost` / `5432` |
| `REDIS_URL` | Celery broker and result backend | `redis://localhost:6379/0` |
| `SPACY_MODEL` | spaCy pipeline | `en_core_web_sm` |
| `RESUME_SKILLS` | Custom skill list | built-in starter list |
| `MAX_RESUME_BYTES` (`serializers.py`) | Upload size limit | 5 MB |
| `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["resume_upload"]` | Upload rate limit | `20/hour` |

## Design Notes and Limitations

- **Idempotent task**: completed applications are skipped, so Celery redelivery is safe. Only transient DB errors are retried; bad files go straight to `failed`.
- **Enqueue after commit**: the task is queued via `transaction.on_commit`, so workers never see a missing row. A broker outage leaves the application `pending` rather than failing the request.
- **Lexical, not semantic**: TF-IDF scores typically land in the 20-60 range for real resumes. Use it for ranking, or add sentence embeddings or skill-overlap blending for absolute thresholds.
- **Applicants don't see scores**: change `ApplicantApplicationSerializer` if you want them to.
- **No OCR**: scanned PDFs fail with a clear message. Add `pytesseract` if you need them.
- **`.doc` files are not supported**, only `.pdf` and `.docx`.

## Production Checklist

- [ ] Store resumes in private object storage (S3/GCS via `django-storages`) and serve signed URLs. Resumes are personal data.
- [ ] Add a Celery beat job that re-queues applications stuck in `pending`/`processing`.
- [ ] Malware-scan uploads.
- [ ] Run workers with enough memory (each process loads spaCy, roughly 100-200 MB).
- [ ] Set `DEBUG=False`, a real `SECRET_KEY`, `ALLOWED_HOSTS`, HTTPS, and CORS rules.
- [ ] Add tests, Sentry/monitoring, and Flower for queue visibility.
