# pylint:disable=all
from django.db import models
from django.contrib.auth.models import User
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.text import slugify
from datetime import timedelta
import uuid


class InterviewTemplate(models.Model):
    """
    Simplified interview template for AI mock interviews
    """

    ROLE_CHOICES = [
        ("software_engineer", "Software Engineer"),
        ("data_scientist", "Data Scientist"),
        ("product_manager", "Product Manager"),
        ("entry_level", "Entry Level"),
    ]

    DIFFICULTY_CHOICES = [
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField()
    role_type = models.CharField(max_length=50, choices=ROLE_CHOICES)
    difficulty = models.CharField(
        max_length=20, choices=DIFFICULTY_CHOICES, default="medium"
    )

    # AI Configuration
    system_prompt = models.TextField(
        help_text="Main prompt for AI interviewer behavior"
    )

    # Settings
    estimated_duration_minutes = models.PositiveIntegerField(default=30)
    is_active = models.BooleanField(default=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True)

    class Meta:
        ordering = ["role_type", "difficulty"]

    def __str__(self):
        return f"{self.get_role_type_display()} - {self.title}"


class InterviewSession(models.Model):
    """
    Individual interview session by a user
    """

    STATUS_CHOICES = [
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("abandoned", "Abandoned"),
        ("disconnected", "Disconnected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(InterviewTemplate, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="in_progress"
    )
    feedback = models.JSONField(blank=True, default=dict)
    transcript = models.TextField(blank=True)

    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.user.username} - {self.template.title}"


class EarlyAccessEmail(models.Model):
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    # Core billing unit
    credits = models.IntegerField(default=0)  # total balance

    configurations = models.JSONField(default=dict, blank=True, null=True)

    def __str__(self):
        return self.user.username

    def has_credit(self, required=10):
        return self.credits >= required

    def deduct_credits(self, used=10):
        if self.credits >= used:
            self.credits -= used
            self.save()
            return True
        return False

    def add_minutes(self, minutes):
        self.credits += minutes
        self.save()


# models.py


class Course(models.Model):
    """
    Main course model containing general course information
    """

    DIFFICULTY_CHOICES = [
        ("beginner", "Beginner"),
        ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
        ("expert", "Expert"),
    ]

    CATEGORY_CHOICES = [
        ("programming", "Programming"),
        ("data_science", "Data Science"),
        ("web_development", "Web Development"),
        ("databases", "Databases"),
        ("machine_learning", "Machine Learning"),
        ("business", "Business"),
        ("design", "Design"),
        ("other", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=250, unique=True, blank=True)
    description = models.TextField()
    short_description = models.CharField(
        max_length=300, help_text="Brief description for cards"
    )

    # Course metadata
    category = models.CharField(
        max_length=50, choices=CATEGORY_CHOICES, default="programming"
    )
    difficulty_level = models.CharField(
        max_length=20, choices=DIFFICULTY_CHOICES, default="beginner"
    )
    estimated_hours = models.PositiveIntegerField(
        help_text="Estimated completion time in hours"
    )

    # Visual elements
    icon = models.CharField(
        max_length=10, default="📚", help_text="Emoji icon for the course"
    )
    cover_image = models.ImageField(upload_to="course_covers/", blank=True, null=True)

    # Course settings
    is_active = models.BooleanField(default=True)
    is_premium = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0, help_text="Display order")

    # OpenAI Assistant configuration
    assistant_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="OpenAI Assistant ID for this course",
    )
    system_prompt = models.TextField(
        blank=True, help_text="Base system prompt for the course assistant"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="courses_created", null=True
    )

    class Meta:
        ordering = ["order", "title"]
        indexes = [
            models.Index(fields=["category", "difficulty_level"]),
            models.Index(fields=["is_active", "order"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def get_total_subtopics(self):
        return self.subtopics.count()

    def get_estimated_completion_time(self):
        return sum(subtopic.estimated_minutes for subtopic in self.subtopics.all())


class Subtopic(models.Model):
    """
    Individual subtopic/lesson within a course
    """

    CONTENT_TYPE_CHOICES = [
        ("lesson", "Lesson"),
        ("practice", "Practice Exercise"),
        ("project", "Project"),
        ("assessment", "Assessment"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="subtopics"
    )

    # Basic info
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=250, blank=True)
    description = models.TextField()

    # Content and syllabus
    syllabus_content = models.TextField(
        help_text="Detailed syllabus/curriculum content for this subtopic that will be fed to OpenAI assistant"
    )
    learning_objectives = models.TextField(
        help_text="What students will learn after completing this subtopic"
    )
    order = models.PositiveIntegerField(default=0)
    content_type = models.CharField(
        max_length=20, choices=CONTENT_TYPE_CHOICES, default="lesson"
    )

    # Time estimates
    estimated_minutes = models.PositiveIntegerField(
        default=30, help_text="Estimated time to complete in minutes"
    )

    # OpenAI-specific content
    teaching_prompt = models.TextField(
        blank=True,
        help_text="Specific prompt for teaching this subtopic via voice assistant",
    )
    assessment_prompt = models.TextField(
        blank=True, help_text="Specific prompt for testing knowledge of this subtopic"
    )

    # Additional resources
    reference_materials = models.TextField(
        blank=True, help_text="Additional reference materials, links, or resources"
    )
    code_examples = models.TextField(
        blank=True, help_text="Code examples or snippets relevant to this subtopic"
    )

    # Settings
    is_active = models.BooleanField(default=True)
    is_optional = models.BooleanField(default=False)
    difficulty_rating = models.IntegerField(
        default=3,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Difficulty rating from 1 (easy) to 5 (very hard)",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["course", "order", "title"]
        unique_together = ["course", "slug"]
        indexes = [
            models.Index(fields=["course", "order"]),
            models.Index(fields=["course", "is_active"]),
        ]

    def __str__(self):
        return f"{self.course.title} - {self.title}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class Transaction(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("card", "Credit Card"),
        ("paypal", "PayPal"),
        ("gpay", "Google Pay"),
    ]

    transaction_id = models.UUIDField(default=uuid.uuid4, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    credits = models.IntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    error_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class RolePlayBots(models.Model):
    VOICE_CHOICES = [
        ("alloy", "Alloy (Male, Default)"),
        ("ash", "Ash (Male)"),
        ("ballad", "Ballad (Female)"),
        ("coral", "Coral (Female)"),
        ("echo", "Echo (Male)"),
        ("fable", "Fable (Female)"),
        ("nova", "Nova (Female)"),
        ("onyx", "Onyx (Male)"),
        ("sage", "Sage (Male)"),
        ("shimmer", "Shimmer (Female)"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    avatar_url = models.URLField(blank=True, null=True)
    system_prompt = models.TextField(
        help_text="System prompt defining the bot's behavior"
    )
    feedback_prompt = models.TextField(
        blank=True, null=True, help_text="Prompt for gathering user feedback"
    )
    custom_configuration = models.JSONField(
        blank=True, null=True, help_text="Additional configuration parameters"
    )
    voice = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Voice setting for TTS",
        default="alloy",
        choices=VOICE_CHOICES,
    )
    is_active = models.BooleanField(default=True)
    is_public = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0, help_text="Display order")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return f"{self.name}"


class RoleplaySession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    bot = models.ForeignKey(RolePlayBots, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20,
        choices=[
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
            ("disconnected", "Disconnected"),
        ],
    )
    transcript = models.TextField(blank=True)
    feedback = models.JSONField(blank=True, default=dict)
    duration_seconds = models.IntegerField(default=0)
    credits_used = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.user.username} - {self.bot.name}"

class RolePlayShare(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bot = models.ForeignKey(RolePlayBots, on_delete=models.CASCADE)
    shared_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('bot', 'shared_by')

    def __str__(self):
        return f"{self.bot.name} shared by {self.shared_by.username}"
    
class MyInvitedRolePlayShare(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    share = models.ForeignKey(RolePlayShare, on_delete=models.CASCADE)
    bot = models.ForeignKey(RolePlayBots, on_delete=models.CASCADE)
    invited_to = models.ForeignKey(User, on_delete=models.CASCADE, default=None)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('share','invited_to')

    def __str__(self):
        return f"{self.share.bot.name} invited by {self.share.shared_by} to {self.invited_to.username}"
    
    

class CreditShare(models.Model):
    CREDITED_FOR_CHOICES = [
        ("creator_share", "Creator Share"),
        ("referral_share", "Referral Share"),
        ("other", "Other"),
    ]
    SETTLEMENT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    credit = models.IntegerField(default=0)
    share = models.ForeignKey(RolePlayShare, on_delete=models.CASCADE, null=True, blank=True)
    bot = models.ForeignKey(RolePlayBots, on_delete=models.CASCADE)
    credited_to = models.ForeignKey(User, on_delete=models.CASCADE, default=None)
    credited_from = models.ForeignKey(User, on_delete=models.CASCADE, related_name='credited_from', default=None)
    credit_reason = models.CharField(max_length=50, choices=CREDITED_FOR_CHOICES, default="other")
    settlement_status = models.CharField(max_length=20, choices=SETTLEMENT_STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.credit} credited to {self.credited_to} from {self.credited_from}"