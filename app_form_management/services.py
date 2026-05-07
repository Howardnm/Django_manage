from django.contrib.contenttypes.models import ContentType
from .models import FormSubmission


class FormSubmissionService:
    """Stateless service for creating and finding FormSubmissions via GFK."""

    def create_or_update(self, template, target_object, submitted_by, form_data,
                         status='SUBMITTED', remark=''):
        """Create or update a FormSubmission bound to `target_object` via GFK."""
        ct = ContentType.objects.get_for_model(target_object)
        existing = FormSubmission.objects.filter(
            template=template,
            content_type=ct,
            object_id=target_object.pk,
            submitted_by=submitted_by,
            status='DRAFT',
        ).first()

        if existing:
            existing.form_data = form_data
            existing.remark = remark
            existing.status = status
            existing.save()
            return existing
        else:
            return FormSubmission.objects.create(
                template=template,
                target_object=target_object,
                submitted_by=submitted_by,
                form_data=form_data,
                status=status,
                remark=remark,
            )

    def get_draft(self, template, target_object, submitted_by):
        """Return the DRAFT submission for (template, target, user), or None."""
        ct = ContentType.objects.get_for_model(target_object)
        return FormSubmission.objects.filter(
            template=template,
            content_type=ct,
            object_id=target_object.pk,
            submitted_by=submitted_by,
            status='DRAFT',
        ).first()

submission_service = FormSubmissionService()
