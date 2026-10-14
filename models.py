"""Domain models for the AI-powered job portal."""
import os
import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models


class User(AbstractUser):
    """Custom user with a coarse role used for authorization."""

    class Role(models.TextChoices):
        RECRUITER = "recruiter", "Recruiter"
        APPLICANT = "applicant", "Applicant"

    email = models.EmailField("email address", unique=True)
    role = models.CharField(
        max_length=20, choices=Role.choices, default=Role.APPLICANT, db_index=True
    )

    @property
    def is_recruiter(self) -> bool:
        return self.role == self.Role.RECRUITER

    @property
    def is_applicant(self) -> bool:
        return self.role == self.Role.APPLICANT

    def __str__(self) -> str:
        return f"{self.username} ({self.role})"


class JobPosting(models.Model):
    """A job opening created by a recruiter."""

    title = models.CharField(max_length=255)
    description = models.TextField()
    requirements = models.TextField(blank=True)
    posted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="job_postings",
        limit_choices_to={"role": User.Role.RECRUITER},
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.posted_by_id and not self.posted_by.is_recruiter:
            raise ValidationError({"posted_by": "Only recruiters can post jobs."})

    @property
    def full_text(self) -> str:
        """Text used as the matching target (description + requirements)."""
        return f"{self.description}\n{self.requirements}".strip()

    def __str__(self) -> str:
        return self.title


def resume_upload_path(instance: "Application", filename: str) -> str:
    """Store resumes under an unguessable name; never trust the client filename."""
    ext = os.path.splitext(filename)[1].lower()
    return f"resumes/job_{instance.job_id}/{uuid.uuid4().hex}{ext}"


class Application(models.Model):
    """An applicant's submission (resume) to a specific job posting."""

    class ParsingStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    applicant = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="applications",
        limit_choices_to={"role": User.Role.APPLICANT},
    )
    job = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name="applications")
    resume = models.FileField(
        upload_to=resume_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=["pdf", "docx"])],
    )
    match_score = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(100.0)],
    )
    parsing_status = models.CharField(
        max_length=20,
        choices=ParsingStatus.choices,
        default=ParsingStatus.PENDING,
        db_index=True,
    )
    extracted_skills = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["applicant", "job"], name="uniq_application_per_applicant_job"
            )
        ]
        indexes = [models.Index(fields=["job", "-match_score"], name="app_job_score_idx")]

    def __str__(self) -> str:
        return f"Application #{self.pk}: {self.applicant_id} -> {self.job_id}"
