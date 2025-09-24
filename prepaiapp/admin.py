# pylint:disable=all
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    EarlyAccessEmail, Course, Subtopic, InterviewTemplate, InterviewSession, Profile, Transaction, RolePlayBots, RoleplaySession, RolePlayShare, MyInvitedRolePlayShare
)
@admin.register(RoleplaySession)
class RolePlaySessionAdmin(admin.ModelAdmin):
    pass
@admin.register(MyInvitedRolePlayShare)
class MyInvitedRolePlayShareAdmin(admin.ModelAdmin):
    pass
@admin.register(RolePlayShare)
class RolePlayShareAdmin(admin.ModelAdmin):
    pass

@admin.register(EarlyAccessEmail)
class EarlyAccessEmailAdmin(admin.ModelAdmin):
    list_display = ("email", "created_at")
    search_fields = ("email",)
    
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    pass
@admin.register(RolePlayBots)
class RolePlayBotsAdmin(admin.ModelAdmin):
    pass

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    pass
    
@admin.register(InterviewTemplate)
class InterviewTemplateAdmin(admin.ModelAdmin):
    pass
    
@admin.register(InterviewSession)
class InterviewSessionAdmin(admin.ModelAdmin):
    pass


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = (
        "title", "category", "difficulty_level", "estimated_hours", "is_active", "is_premium", "order", "created_at"
    )
    list_filter = ("category", "difficulty_level", "is_active", "is_premium", "created_at")
    search_fields = ("title", "description", "short_description")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("order", "title")
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("title", "slug", "description", "short_description", "icon")
        }),
        ("Course Details", {
            "fields": ("category", "difficulty_level", "estimated_hours", "cover_image")
        }),
        ("Settings", {
            "fields": ("is_active", "is_premium", "order")
        }),
        ("OpenAI Integration", {
            "fields": ("assistant_id", "system_prompt"),
            "classes": ("collapse",)
        }),
    )
    
    readonly_fields = ("created_at", "updated_at")
    
    def make_active(self, request, queryset):
        queryset.update(is_active=True)
    make_active.short_description = "Mark selected courses as active"
    
    def make_inactive(self, request, queryset):
        queryset.update(is_active=False)
    make_inactive.short_description = "Mark selected courses as inactive"


class SubtopicInline(admin.TabularInline):
    model = Subtopic
    extra = 1
    fields = ("title", "order", "estimated_minutes", "difficulty_rating", "is_active")
    ordering = ("order",)


@admin.register(Subtopic)
class SubtopicAdmin(admin.ModelAdmin):
    list_display = (
        "title", "course", "order", "content_type", "difficulty_rating", 
        "estimated_minutes", "is_active", "created_at"
    )
    list_filter = (
        "course", "content_type", "difficulty_rating", "is_active", 
        "is_optional", "created_at"
    )
    search_fields = ("title", "description", "syllabus_content")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("course", "order")
    
    fieldsets = (
        ("Basic Information", {
            "fields": ("course", "title", "slug", "description", "content_type")
        }),
        ("Structure", {
            "fields": ("order", "is_optional", "difficulty_rating")
        }),
        ("Content & Syllabus", {
            "fields": ("syllabus_content", "learning_objectives", "reference_materials", "code_examples"),
            "classes": ("wide",)
        }),
        ("OpenAI Prompts", {
            "fields": ("teaching_prompt", "assessment_prompt"),
            "classes": ("collapse", "wide")
        }),
        ("Settings", {
            "fields": ("estimated_minutes", "is_active")
        }),
    )
    
    readonly_fields = ("created_at", "updated_at")
    
    def make_active(self, request, queryset):
        queryset.update(is_active=True)
    make_active.short_description = "Mark selected subtopics as active"
    
    def make_inactive(self, request, queryset):
        queryset.update(is_active=False)
    make_inactive.short_description = "Mark selected subtopics as inactive"
















# Additional admin configurations
admin.site.site_header = "PrepAI Administration"
admin.site.site_title = "PrepAI Admin"
admin.site.index_title = "Welcome to PrepAI Administration"

# Customize Course admin to include subtopics inline
CourseAdmin.inlines = [SubtopicInline]