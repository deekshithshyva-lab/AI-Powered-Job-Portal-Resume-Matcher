"""DRF views."""
import logging

from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status, viewsets
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.throttling import ScopedRateThrottle

from .models import Application, JobPosting
from .permissions import IsApplicant, IsJobOwnerOrReadOnly, IsRecruiter, IsRecruiterOrReadOnly
from .serializers import (
    ApplicantApplicationSerializer,
    ApplicationCreateSerializer,
    JobPostingSerializer,
    RecruiterApplicationSerializer,
)
from .tasks import process_resume

logger = logging.getLogger(__name__)


def _enqueue_resume_processing(application_id: int) -> None:
    """Dispatch the Celery task; never let a broker outage fail the HTTP request.

    The application stays PENDING and can be re-queued by a periodic sweeper.
    """
    try:
        process_resume.delay(application_id)
    except Exception:
        logger.exception("Could not enqueue process_resume for application %s", application_id)


class JobPostingViewSet(viewsets.ModelViewSet):
    """CRUD for job postings. Recruiters write (own jobs only); everyone authenticated reads."""

    serializer_class = JobPostingSerializer
    permission_classes = [IsAuthenticated, IsRecruiterOrReadOnly, IsJobOwnerOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        return JobPosting.objects.select_related("posted_by").filter(
            Q(is_active=True) | Q(posted_by=user)
        )

    def perform_create(self, serializer):
        serializer.save(posted_by=self.request.user)


class JobApplicationListCreateView(generics.ListCreateAPIView):
    """
    POST /api/jobs/<job_id>/applications/  (Applicant)  -> 202 Accepted
        multipart/form-data with a `resume` file (PDF/DOCX).
    GET  /api/jobs/<job_id>/applications/  (Recruiter who owns the job)
        Applications ranked by match_score DESC (unscored last).
        Optional filter: ?status=pending|processing|completed|failed
    """

    parser_classes = [MultiPartParser, FormParser]
    throttle_scope = "resume_upload"

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsApplicant()]
        return [IsAuthenticated(), IsRecruiter()]

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.request.method == "POST":
            throttles.append(ScopedRateThrottle())
        return throttles

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ApplicationCreateSerializer
        return RecruiterApplicationSerializer

    def get_job(self) -> JobPosting:
        job_id = self.kwargs["job_id"]
        if self.request.method == "POST":
            return get_object_or_404(JobPosting, pk=job_id, is_active=True)
        # 404 (not 403) for other recruiters' jobs avoids leaking existence.
        return get_object_or_404(JobPosting, pk=job_id, posted_by=self.request.user)

    def get_queryset(self):
        qs = (
            Application.objects.filter(job=self.get_job())
            .select_related("applicant")
            .order_by(F("match_score").desc(nulls_last=True), "created_at")
        )
        status_param = self.request.query_params.get("status")
        if status_param in Application.ParsingStatus.values:
            qs = qs.filter(parsing_status=status_param)
        return qs

    def create(self, request, *args, **kwargs):
        job = self.get_job()
        serializer = ApplicationCreateSerializer(
            data=request.data, context={"request": request, "job": job}
        )
        serializer.is_valid(raise_exception=True)
        application = serializer.save()

        # Enqueue only after the row is committed so the worker can always find it.
        transaction.on_commit(lambda: _enqueue_resume_processing(application.pk))

        status_url = reverse("application-detail", args=[application.pk], request=request)
        body = ApplicantApplicationSerializer(application, context={"request": request}).data
        return Response(
            {**body, "status_url": status_url},
            status=status.HTTP_202_ACCEPTED,
            headers={"Location": status_url},
        )


class ApplicationDetailView(generics.RetrieveAPIView):
    """GET /api/applications/<id>/ - poll status. Applicants: own only. Recruiters: own jobs only."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Application.objects.select_related("job", "applicant")
        return qs.filter(job__posted_by=user) if user.is_recruiter else qs.filter(applicant=user)

    def get_serializer_class(self):
        if self.request.user.is_recruiter:
            return RecruiterApplicationSerializer
        return ApplicantApplicationSerializer
