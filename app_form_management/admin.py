from django.contrib import admin
from .models import FormTemplate, FormSubmission


@admin.register(FormTemplate)
class FormTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'created_by', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')


@admin.register(FormSubmission)
class FormSubmissionAdmin(admin.ModelAdmin):
    list_display = ('template', 'submitted_by', 'status', 'created_at')
    list_filter = ('status', 'template')
    search_fields = ('template__name', 'submitted_by__username')
