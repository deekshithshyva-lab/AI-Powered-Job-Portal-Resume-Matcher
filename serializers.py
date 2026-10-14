"""DRF serializers."""
from django.db import IntegrityError
from rest_framework import serializers

from .models import Application, JobPosting

MAX_RESUME_BYTES = 5 * 1024 * 1024  # 5 MB
_MAGIC = {".pdf": b"%PDF", ".docx": b"PK\x03\x04"}  # DOCX is a ZIP container


class JobPostingSerializer(serializers.ModelSerializer):
    posted_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = JobPosting
        fields = ["id", "title", "description", "requirements", "posted_by", "is_active", "created_at"]
        read_only_fields = ["id", "posted_by", "created_at"]


class ApplicationCreateSerializer(serializers.ModelSerializer):
    """Validates the upload and creates a PENDING application.

    Requires `request` and `job` in the serializer context.
    """

    class Meta:
        model = Application
        fields = ["resume"]

    def validate_resume(self, f):
        if f.size > MAX_RESUME_BYTES:
            raise serializers.ValidationError("Resume must be 5 MB or smaller.")
        ext = "." + f.name.rsplit(".", 1)[-1].lower() if "." in f.name else ""
        if ext not in _MAGIC:
            raise serializers.ValidationError("Only PDF and DOCX files are accepted.")
        head = f.read(4)
        f.seek(0)
        if not head.startswith(_MAGIC[ext]):  # don't trust the extension alone
            raise serializers.ValidationError("File content does not match its extension.")
        return f

    def validate(self, attrs):
        request, job = self.context["request"], self.context["job"]
        if Application.objects.filter(applicant=request.user, job=job).exists():
            raise serializers.ValidationError("You have already applied to this job.")
        return attrs

    def create(self, validated_data):
        try:
            return Application.objects.create(
                applicant=self.context["request"].user,
                job=self.context["job"],
                parsing_status=Application.ParsingStatus.PENDING,
                **validated_data,
            )
        except IntegrityError:  # race on the unique constraint
            raise serializers.ValidationError("You have already applied to this job.")


class ApplicantApplicationSerializer(serializers.ModelSerializer):
    """What applicants see: status only (no score/skills, a product decision)."""

    job_title = serializers.CharField(source="job.title", read_only=True)

    class Meta:
        model = Application
        fields = ["id", "job", "job_title", "parsing_status", "created_at"]
        read_only_fields = fields


class RecruiterApplicationSerializer(serializers.ModelSerializer):
    applicant = serializers.SerializerMethodField()
    resume_url = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = [
            "id", "applicant", "resume_url", "match_score", "parsing_status",
            "extracted_skills", "error_message", "created_at",
        ]
        read_only_fields = fields

    def get_applicant(self, obj):
        return {"id": obj.applicant_id, "username": obj.applicant.username, "email": obj.applicant.email}

    def get_resume_url(self, obj):
        request = self.context.get("request")
        url = obj.resume.url if obj.resume else None
        return request.build_absolute_uri(url) if (url and request) else url
