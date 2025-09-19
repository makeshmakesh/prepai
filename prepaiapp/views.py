#pylint:disable=all
from django.shortcuts import render
from django.views import View
from .models import EarlyAccessEmail
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.models import User
from .models import Profile, Course, InterviewTemplate, InterviewSession

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.mixins import LoginRequiredMixin
import json
import logging
from django.contrib.auth import authenticate, login, logout
logger = logging.getLogger(__name__)
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
class StartInterviewView(LoginRequiredMixin, View):
    """
    Start a new interview session
    """
    login_url = "/login/"
    
    def get(self, request, template_id):
        try:
            # Get the interview template
            template = get_object_or_404(
                InterviewTemplate, 
                id=template_id, 
                is_active=True
            )
            
            # Check if user has an ongoing session for this template
            ongoing_session = InterviewSession.objects.filter(
                user=request.user,
                template=template,
                status='in_progress'
            ).first()
            
            if ongoing_session:
                # Redirect to existing session
                return redirect('interview_session', session_id=ongoing_session.id)
            
            # Create new interview session
            session = InterviewSession.objects.create(
                template=template,
                user=request.user,
                status='in_progress',
                started_at=timezone.now()
            )
            
            # Redirect to interview session page
            return redirect('interview_session', session_id=session.id)
            
        except InterviewTemplate.DoesNotExist:
            messages.error(request, "Interview template not found or inactive.")
            return redirect('interview_types')
        except Exception as e:
            messages.error(request, "Failed to start interview session. Please try again.")
            return redirect('interview_types')

class InterviewSessionView(LoginRequiredMixin, View):
    """
    Display the actual interview session interface
    """
    login_url = "/login/"
    
    def get(self, request, session_id):
        try:
            # Get the interview session
            session = get_object_or_404(
                InterviewSession,
                id=session_id,
                user=request.user
            )
            
            # Only allow access to in-progress sessions
            if session.status not in ['in_progress', 'pending']:
                messages.info(request, "This interview session has already been completed.")
                return redirect('interview_results', session_id=session.id)
            
            context = {
                'session': session,
                'template': session.template,
            }
            
            return render(request, 'interview_session.html', context)
            
        except InterviewSession.DoesNotExist:
            messages.error(request, "Interview session not found.")
            return redirect('interview_types')
class InterviewView(LoginRequiredMixin, View):
    """
    View to display available interview templates
    """
    login_url = "/login/"
    
    def get(self, request):
        templates = InterviewTemplate.objects.filter(is_active=True)
        
        context = {
            'templates': templates,
        }
        return render(request, 'interviews.html', context)
    



class DashboardView(LoginRequiredMixin, View):
    """
    Class-based version of course subtopics view
    """
    login_url = "/login/"
    
    def get(self, request):
        
        context = {
        }
        return render(request, 'dashboard.html', context)
class CourseSubtopicsView(LoginRequiredMixin, View):
    """
    Class-based version of course subtopics view
    """
    login_url = "/login/"
    
    def get(self, request, slug):
        course = get_object_or_404(Course, slug=slug, is_active=True)
        subtopics = course.subtopics.filter(is_active=True).order_by('order', 'title')
        
        context = {
            'course': course,
            'subtopics': subtopics,
        }
        return render(request, 'subtopics.html', context)

class CourseView(LoginRequiredMixin, View):
    """
    View for the main dashboard/topics page.
    Displays available courses with optional category filtering.
    Requires user authentication.
    """
    login_url = "/login/"
    redirect_field_name = "next"

    def get(self, request):
        # Debug: Print request info
        print(f"User: {request.user}")
        print(f"User authenticated: {request.user.is_authenticated}")
        print(f"Template being rendered: topic.html")
        
        # Get category filter from query parameters
        category_filter = request.GET.get('category', 'all')
        print(f"Category filter: {category_filter}")
        
        # Get all courses for debugging
        all_courses = Course.objects.all()
        print(f"Total courses in database: {all_courses.count()}")
        
        # Start with active courses, ordered by display order
        courses_queryset = Course.objects.filter(is_active=True).order_by('order', 'title')
        print(f"Active courses: {courses_queryset.count()}")
        
        # Apply category filter if specified and not 'all'
        if category_filter and category_filter != 'all':
            courses_queryset = courses_queryset.filter(category=category_filter)
            print(f"Filtered courses for {category_filter}: {courses_queryset.count()}")
        
        # Get all available categories for the filter tabs
        available_categories = Course.objects.filter(is_active=True).values_list('category', flat=True).distinct()
        print(f"Available categories: {list(available_categories)}")
        
        # Debug: Print each course
        for course in courses_queryset:
            print(f"Course: {course.title} - Icon: {course.icon} - Category: {course.category}")
            print(f"  Subtopics: {course.get_total_subtopics()}")
            print(f"  Active: {course.is_active}")
        
        # Prepare context data
        context = {
            'courses': courses_queryset,
            'current_category': category_filter,
            'available_categories': available_categories,
            'category_choices': Course.CATEGORY_CHOICES,
            # Add debug info to template
            'debug_info': {
                'total_courses': all_courses.count(),
                'active_courses': courses_queryset.count(),
                'user_authenticated': request.user.is_authenticated,
                'user_staff': request.user.is_staff if request.user.is_authenticated else False,
            }
        }
        
        print(f"Context keys: {list(context.keys())}")
        
        return render(request, "topic.html", context)
class LogoutView(View):
    """View for handling user logout."""
    def post(self, request):
        logout(request)  # Logs out the user
        return redirect("login")  # Redirect to login page
    
    
class SignupView(View):
    """View for user registration."""
    def get(self, request):
        # Redirect to dashboard if already logged in
        if request.user.is_authenticated:
            return redirect("dashboard")
        return render(request, "signup.html")  # Render template with empty form

    def post(self, request):
        # Get form data
        username = request.POST.get("email")
        email = request.POST.get("email")
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")

        # Validation
        if not username or not email or not password1 or not password2:
            messages.error(request, "All fields are required.")
            return render(request, "signup.html")

        if len(password1) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(request, "signup.html")

        if password1 != password2:
            messages.error(request, "Passwords do not match.")
            return render(request, "signup.html")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username is already taken.")
            return render(request, "signup.html")

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email is already registered.")
            return render(request, "signup.html")

        # Create user
        user = User.objects.create_user(
            username=username, email=email, password=password1
        )
        Profile.objects.get_or_create(user=user)
        login(request, user)  # Auto login after signup
        messages.success(request, "Signup successful!")
        return redirect("dashboard")  # Redirect to dashboard


class LoginView(View):
    """View for user login."""
    def get(self, request):
        # Redirect to dashboard if already logged in
        if request.user.is_authenticated:
            return redirect("dashboard")
        return render(request, "login.html")  # Render the login page

    def post(self, request):
        # Get form data
        username = request.POST.get("username")
        password = request.POST.get("password")

        # Validate input fields
        if not username or not password:
            messages.error(request, "All fields are required.")
            return render(request, "login.html")

        # Authenticate user
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, "Login successful!")
            return redirect("dashboard")  # Redirect to dashboard
        else:
            messages.error(request, "Invalid username or password.")
            return render(request, "login.html")

def voice_agent_view(request):
    """Main voice agent interface"""
    return render(request, 'voice_agent.html')

@csrf_exempt
def health_check(request):
    """Health check endpoint"""
    return JsonResponse({
        'status': 'healthy',
        'service': 'voice-agent'
    })

def api_status(request):
    """API status endpoint"""
    return JsonResponse({
        'websocket_url': '/ws/voice-agent/',
        'status': 'ready'
    })
class HomePage(View):
    """Renders the landing page."""
    def get(self, request):

        return render(request, "landing.html")
    
    

class EarlyAccessSignupView(View):
    template_name = "landing.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        email = request.POST.get("email", "").strip().lower()
        print("Received email:", email)
        if email:
            obj, created = EarlyAccessEmail.objects.get_or_create(email=email)
            if created:
                return JsonResponse({"status": "success", "message": "Thanks for joining!"})
            else:
                return JsonResponse({"status": "info", "message": "You're already on the list."})
        else:
            return JsonResponse({"status": "error", "message": "Please enter a valid email."})


def realtime_view(request):
    # This would later connect to your Realtime agent logic
    # but for now just return something simple
    return render(request, "realtime.html")


def topic(request):
    # This would later connect to your Realtime agent logic
    # but for now just return something simple
    return render(request, "topic.html")

def sub_topic(request):
    # This would later connect to your Realtime agent logic
    # but for now just return something simple
    return render(request, "subtopic.html")