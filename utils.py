"""NLP utilities: text cleaning, skill extraction and resume/job matching."""
import logging
import re
from functools import lru_cache

import spacy
from django.conf import settings
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from spacy.matcher import PhraseMatcher

logger = logging.getLogger(__name__)

SPACY_MODEL = getattr(settings, "SPACY_MODEL", "en_core_web_sm")
MAX_CHARS = 200_000  # hard cap to protect memory / spaCy's max_length

# Starter taxonomy. Override with settings.RESUME_SKILLS (or load from DB / ESCO / O*NET).
DEFAULT_SKILLS = [
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust", "ruby", "php",
    "sql", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "django", "django rest framework", "flask", "fastapi", "celery", "react", "angular",
    "vue", "node.js", "spring boot", ".net",
    "docker", "kubernetes", "aws", "azure", "gcp", "terraform", "ansible", "jenkins",
    "ci/cd", "git", "linux", "rest", "graphql", "microservices", "kafka", "rabbitmq",
    "machine learning", "deep learning", "nlp", "natural language processing",
    "computer vision", "pytorch", "tensorflow", "scikit-learn", "spacy", "pandas", "numpy",
    "data analysis", "data engineering", "spark", "airflow", "tableau", "power bi",
    "agile", "scrum", "project management", "communication", "leadership",
]

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
_WS_RE = re.compile(r"\s+")


@lru_cache(maxsize=1)
def get_nlp():
    """Load (once per process) the spaCy pipeline. Parser/NER are unused, so disabled."""
    try:
        return spacy.load(SPACY_MODEL, disable=["parser", "ner"])
    except OSError as exc:  # model not installed
        raise RuntimeError(
            f"spaCy model '{SPACY_MODEL}' is missing. Run: python -m spacy download {SPACY_MODEL}"
        ) from exc


@lru_cache(maxsize=1)
def _skill_matcher():
    nlp = get_nlp()
    skills = list(getattr(settings, "RESUME_SKILLS", DEFAULT_SKILLS))
    matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
    matcher.add("SKILL", [nlp.make_doc(s) for s in skills])
    canonical = {s.lower(): s for s in skills}
    return matcher, canonical


def clean_text(text: str) -> str:
    """Normalise text for vectorisation.

    Strips URLs/e-mails, drops stop words, punctuation, numbers and whitespace tokens,
    and lemmatises. Single-character lemmas are dropped as PDF-extraction noise; short
    skills like "c" or "r" are handled separately by `extract_skills`.
    """
    if not text:
        return ""
    text = _EMAIL_RE.sub(" ", _URL_RE.sub(" ", text[:MAX_CHARS]))
    doc = get_nlp()(text)
    tokens = (
        tok.lemma_.lower().strip()
        for tok in doc
        if not (tok.is_stop or tok.is_punct or tok.is_space or tok.like_num)
    )
    return " ".join(t for t in tokens if len(t) > 1)


def extract_skills(text: str) -> list[str]:
    """Return a sorted, de-duplicated list of known skills found in `text`."""
    if not text:
        return []
    nlp = get_nlp()
    matcher, canonical = _skill_matcher()
    doc = nlp.make_doc(_WS_RE.sub(" ", text[:MAX_CHARS]))
    found = {canonical[doc[s:e].text.lower()] for _, s, e in matcher(doc) if doc[s:e].text.lower() in canonical}
    return sorted(found)


def calculate_match_score(resume_text: str, job_description: str) -> float:
    """Compute a 0-100 similarity score between a resume and a job description.

    Both texts are cleaned with spaCy, vectorised with TF-IDF (unigrams + bigrams,
    sublinear tf) and compared with cosine similarity.

    Note: TF-IDF measures lexical overlap, so raw scores for real resumes are typically
    modest (20-60). Rank by it, or calibrate/blend with skill overlap or embeddings
    (e.g. sentence-transformers) if you need absolute thresholds.
    """
    resume_clean = clean_text(resume_text)
    job_clean = clean_text(job_description)
    if not resume_clean or not job_clean:
        return 0.0

    try:
        matrix = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True).fit_transform(
            [resume_clean, job_clean]
        )
    except ValueError:  # empty vocabulary
        return 0.0

    similarity = float(cosine_similarity(matrix[0], matrix[1])[0, 0])
    return round(max(0.0, min(1.0, similarity)) * 100, 2)
