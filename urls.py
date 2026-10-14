from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ApplicationDetailView, JobApplicationListCreateView, JobPostingViewSet

router = DefaultRouter()
router.register("jobs", JobPostingViewSet, basename="job")

urlpatterns = [
    path("jobs/<int:job_id>/applications/", JobApplicationListCreateView.as_view(), name="job-applications"),
    path("applications/<int:pk>/", ApplicationDetailView.as_view(), name="application-detail"),
    path("", include(router.urls)),
]
