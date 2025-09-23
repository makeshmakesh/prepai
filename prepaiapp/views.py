#pylint:disable=all
from django.shortcuts import render
from django.views import View
from .models import EarlyAccessEmail
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.models import User
from .models import Profile, Course, InterviewTemplate, InterviewSession, Transaction, RolePlayBots, RoleplaySession
import os
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
from django.core.cache import cache
from openai import OpenAI
from datetime import datetime, time
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
class EditRolePlayBotView(LoginRequiredMixin, View):
        def get(self, request, bot_id):
            bot = get_object_or_404(RolePlayBots, id=bot_id, created_by=request.user)
            context = {
                'bot': bot,
            }
            return render(request, 'edit_roleplay_bot.html', context)
        
        def post(self, request, bot_id):
            bot = get_object_or_404(RolePlayBots, id=bot_id, created_by=request.user)
            
            try:
                # Get form data
                name = request.POST.get('name', '').strip()
                description = request.POST.get('description', '').strip()
                avatar_url = request.POST.get('avatar_url', '').strip()
                system_prompt = request.POST.get('system_prompt', '').strip()
                feedback_prompt = request.POST.get('feedback_prompt', '').strip()
                custom_configuration = request.POST.get('custom_configuration', '').strip()
                order = request.POST.get('order', 0)
                is_active = request.POST.get('is_active') == 'on'
                is_public = request.POST.get('is_public') == 'on'
                voice = request.POST.get('voice', 'alloy').strip()

                # Validation
                if not name:
                    messages.error(request, 'Bot name is required.')
                    return render(request, 'edit_roleplay_bot.html', {'bot': bot})
                
                if not system_prompt:
                    messages.error(request, 'System prompt is required.')
                    return render(request, 'edit_roleplay_bot.html', {'bot': bot})
                
                if len(system_prompt) < 50:
                    messages.error(request, 'System prompt should be more detailed (at least 50 characters).')
                    return render(request, 'edit_roleplay_bot.html', {'bot': bot})

                # Validate JSON if provided
                if custom_configuration:
                    try:
                        json.loads(custom_configuration)
                    except json.JSONDecodeError:
                        messages.error(request, 'Custom configuration must be valid JSON format.')
                        return render(request, 'edit_roleplay_bot.html', {'bot': bot})

                # Validate order
                try:
                    order = int(order)
                    if order < 0:
                        order = 0
                except (ValueError, TypeError):
                    order = 0

                # Update bot
                bot.name = name
                bot.description = description if description else None
                bot.avatar_url = avatar_url if avatar_url else None
                bot.system_prompt = system_prompt
                bot.is_active = is_active
                bot.is_public = is_public
                bot.voice = voice if voice else "alloy"
                
                bot.save()
                
                messages.success(request, f'"{bot.name}" has been updated successfully!')
                return redirect('my-roleplay-bots')
                
            except Exception as e:
                messages.error(request, f'An error occurred while updating the bot: {str(e)}')
                return render(request, 'edit_roleplay_bot.html', {'bot': bot})
            
class DeleteRolePlayBotView(LoginRequiredMixin, View):
    def post(self, request, bot_id):
        bot = get_object_or_404(RolePlayBots, id=bot_id, created_by=request.user)
        bot_name = bot.name
        
        try:
            bot.delete()
            messages.success(request, f'"{bot_name}" has been deleted successfully!')
        except Exception as e:
            messages.error(request, f'An error occurred while deleting the bot: {str(e)}')
        
        return redirect('my-roleplay-bots')

    def get(self, request, bot_id):
        # Redirect GET requests to the edit page
        return redirect('edit-roleplay-bot', bot_id=bot_id)

class MyRolePlayBotView(LoginRequiredMixin, View):
    """
    View to display user's created roleplay bots
    """
    login_url = "/login/"
    
    def get(self, request):
        # Fetch roleplay templates (assuming they are a subset of InterviewTemplate)
        roleplay_bots = RolePlayBots.objects.filter(created_by=request.user).order_by('order', '-created_at')
        
        context = {
            'bots': roleplay_bots,
            "total_bots" : roleplay_bots.count(),
            "active_bots" : roleplay_bots.filter(is_active=True).count(),
            "total_sessions" : RoleplaySession.objects.filter(user=request.user).count(),
        }
        return render(request, 'my_roleplay_bots.html', context)
class CreateRolePlayBotView(LoginRequiredMixin, View):
    def post(self, request):
        name = request.POST.get('name')
        avatar_url = request.POST.get('avatar_url')
        system_prompt = request.POST.get('system_prompt')
        description = request.POST.get('description')
        feedback_prompt = request.POST.get('feedback_prompt')
        is_active = request.POST.get('is_active') == 'on'
        is_public = request.POST.get('is_public') == 'on'
        # scenario_description = request.POST.get('scenario_description') --- IGNORE ---
        custom_configuration = {
            "temperature": float(request.POST.get('temperature', 0.7)),
            "max_tokens": int(request.POST.get('max_tokens', 150)),
            "top_p": float(request.POST.get('top_p', 1.0)),
            "frequency_penalty": float(request.POST.get('frequency_penalty', 0.0)),
            "presence_penalty": float(request.POST.get('presence_penalty', 0.0)),
            "required_minimum_credits": int(request.POST.get('required_minimum_credits', 10)),
        }
        
        if not name or not system_prompt:
            messages.error(request, "Name and System Prompt are required.")
            return redirect('create_roleplay_bot')
        
        try:
            bot = RolePlayBots.objects.create(
                name=name,
                description=description,
                avatar_url=avatar_url,
                system_prompt=system_prompt,
                feedback_prompt=feedback_prompt,
                custom_configuration=custom_configuration,
                created_by=request.user,
                is_active=is_active,
                is_public=is_public,
            )
            messages.success(request, f"Roleplay Bot '{bot.name}' created successfully!")
            return redirect('voice_roleplay')
        except Exception as e:
            logger.error(f"Error creating Roleplay Bot: {e}")
            messages.error(request, "An error occurred while creating the bot. Please try again.")
            return redirect('create_roleplay_bot')
    def get(self, request):
        return render(request, 'create_roleplay_bot.html')
class MarketplaceView(LoginRequiredMixin, View):
    """
    View to display the marketplace of interview templates
    """
    login_url = "/login/"
    
    def get(self, request):
        context = {
        }
        return render(request, 'marketplace.html', context)

class RolePlaySessionView(LoginRequiredMixin, View):
    """
    Display the actual roleplay session interface
    """
    login_url = "/login/"
    
    def get(self, request, session_id):
        try:
            # Get the interview session
            session = get_object_or_404(
                RoleplaySession,
                id=session_id,
                user=request.user
            )
            
            # Only allow access to in-progress sessions
            if session.status not in ['in_progress', 'pending']:
                messages.info(request, "This Roleplay session has already been completed.")
                return redirect('voice_roleplay', session_id=session.id)
            
            context = {
                'session': session,
                'bot': session.bot,
            }
            
            return render(request, 'roleplay_session.html', context)
            
        except InterviewSession.DoesNotExist:
            messages.error(request, "Interview session not found.")
            return redirect('voice_roleplay')
class RolePlayStartView(LoginRequiredMixin, View):
    """
    Start a new interview session
    """
    login_url = "/login/"
    
    def get(self, request, bot_id):
        try:
            # Get the interview template
            role_play_bot = get_object_or_404(
                RolePlayBots, 
                id=bot_id, 
                is_active=True
            )
            profile = Profile.objects.get(user=request.user)
            if not profile.has_credit(required=role_play_bot.custom_configuration.get("required_minimum_credits", 10)):
                messages.error(request, "You don’t have enough credits. Please top up.")
                return redirect("purchase_credits")  # redirect to your top-up page
            # Check if user has an ongoing session for this bot
            ongoing_session = RoleplaySession.objects.filter(
                user=request.user,
                bot=role_play_bot,
                status='in_progress'
            ).first()
            
            if ongoing_session:
                # Redirect to existing session
                return redirect('roleplay_session', session_id=ongoing_session.id)
            profile.deduct_credits(used=role_play_bot.custom_configuration.get("required_minimum_credits", 10))
            # Create new interview session
            session = RoleplaySession.objects.create(
                bot=role_play_bot,
                user=request.user,
                status='in_progress',
                started_at=timezone.now()
            )
            # Redirect to roleplay_session session page
            return redirect('roleplay_session', session_id=session.id)
            
        except RolePlayBots.DoesNotExist:
            messages.error(request, "Roleplay bot not found or inactive.")
            return redirect('voice_roleplay')
        except Exception as e:
            print(f"Error starting Roleplay session: {e}")
            messages.error(request, "Failed to start Roleplay session. Please try again.")
            return redirect('voice_roleplay')
class VoiceRolePlayView(LoginRequiredMixin, View):
    """
    View to display voice roleplay options
    """
    login_url = "/login/"
    
    def get(self, request):
        # Fetch roleplay templates (assuming they are a subset of InterviewTemplate)
        roleplay_bots = RolePlayBots.objects.filter(is_active=True, is_public=True).order_by('order', '-created_at')
        
        context = {
            'roleplay_bots': roleplay_bots,
        }
        return render(request, 'voice_roleplay_list.html', context)

class ProfileView(LoginRequiredMixin, View):
    """
    View to display and update user profile
    """
    login_url = "/login/"
    
    def get(self, request):
        profile = Profile.objects.get(user=request.user)
        context = {
            'profile': profile,
        }
        return render(request, 'profile.html', context)
    
    def post(self, request):
        try:
            profile = Profile.objects.get(user=request.user)
            # Update profile fields from form data
            profile.save()
            
            messages.success(request, "Profile updated successfully!")
            return redirect('profile')
        except Exception as e:
            logger.error(f"Error updating profile: {e}")
            messages.error(request, "An error occurred while updating your profile. Please try again.")
            return redirect('profile')
class PurchaseCredits(LoginRequiredMixin, View):
    """
    View to handle purchasing credits (minutes)
    """
    login_url = "/login/"
    
    def get(self, request):
        profile = Profile.objects.get(user=request.user)
        context = {
            'current_credits': profile.credits,
        }
        return render(request, 'purchase_credits.html', context)
    
    def post(self, request):
        try:
            amount = int(request.POST.get('amount', 0))
            if amount <= 0:
                messages.error(request, "Invalid amount. Please enter a positive number.")
                return redirect('purchase_credits')
            
            profile = Profile.objects.get(user=request.user)
            profile.credits += amount
            profile.save()
            
            messages.success(request, f"Successfully purchased {amount} minutes!")
            return redirect('dashboard')
        except ValueError:
            messages.error(request, "Invalid input. Please enter a valid number.")
            return redirect('purchase_credits')
        except Exception as e:
            logger.error(f"Error purchasing credits: {e}")
            messages.error(request, "An error occurred while processing your purchase. Please try again.")
            return redirect('purchase_credits')

class InterviewHistoryView(LoginRequiredMixin, View):
    """
    View to display user's past interview sessions with statistics
    """
    login_url = "/login/"
    
    def get(self, request):
        # Get all sessions for the user
        base_sessions = InterviewSession.objects.filter(user=request.user).select_related('template')
        
        # Apply filters
        filtered_sessions = self.apply_filters(base_sessions, request.GET)
        
        # Calculate statistics
        stats = self.calculate_statistics(base_sessions)
        
        # Order sessions by most recent first
        sessions = filtered_sessions.order_by('-started_at')
        
        context = {
            'sessions': sessions,
            'stats': stats,
            'filters': {
                'status': request.GET.get('status', ''),
                'role_type': request.GET.get('role_type', ''),
                'difficulty': request.GET.get('difficulty', ''),
            },
            'role_choices': InterviewTemplate.ROLE_CHOICES,
            'difficulty_choices': InterviewTemplate.DIFFICULTY_CHOICES,
            'status_choices': InterviewSession.STATUS_CHOICES,
        }
        return render(request, 'interview_history.html', context)
    
    def apply_filters(self, queryset, filters):
        """Apply filters to the queryset"""
        status = filters.get('status')
        role_type = filters.get('role_type')
        difficulty = filters.get('difficulty')
        
        if status:
            queryset = queryset.filter(status=status)
        if role_type:
            queryset = queryset.filter(template__role_type=role_type)
        if difficulty:
            queryset = queryset.filter(template__difficulty=difficulty)
            
        return queryset
    
    def calculate_statistics(self, sessions):
        """Calculate statistics for the dashboard"""
        # Basic counts
        total_interviews = sessions.count()
        completed_count = sessions.filter(status='completed').count()
        in_progress_count = sessions.filter(status='in_progress').count()
        abandoned_count = sessions.filter(status='abandoned').count()
        
        # Get latest difficulty
        latest_session = sessions.order_by('-started_at').first()
        latest_difficulty = None
        if latest_session:
            latest_difficulty = latest_session.template.get_difficulty_display()
        
        # Additional useful stats
        completion_rate = 0
        if total_interviews > 0:
            completion_rate = round((completed_count / total_interviews) * 100, 1)
        
        # Most attempted role
        role_stats = (sessions
                     .values('template__role_type')
                     .annotate(count=Count('template__role_type'))
                     .order_by('-count')
                     .first())
        
        most_attempted_role = None
        if role_stats:
            # Get display name for the role
            role_dict = dict(InterviewTemplate.ROLE_CHOICES)
            most_attempted_role = role_dict.get(role_stats['template__role_type'])
        
        return {
            'total_interviews': total_interviews,
            'completed_count': completed_count,
            'in_progress_count': in_progress_count,
            'abandoned_count': abandoned_count,
            'latest_difficulty': latest_difficulty,
            'completion_rate': completion_rate,
            'most_attempted_role': most_attempted_role,
        }
class InterviewResultView(LoginRequiredMixin, View):
    """
    View to display interview results and feedback
    """
    login_url = "/login/"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    def get(self, request, session_id):
        try:
            # Get the interview session
            session = get_object_or_404(
                InterviewSession,
                id=session_id,
                user=request.user
            )
            # Check if we have transcript to analyze
            if not session.transcript:
                messages.warning(request, "Interview transcript not available yet.")
                return redirect('interview_types')
            
            # Check cache first to avoid re-analysis
            cache_key = f"interview_analysi_{session_id}"
            analysis_results = cache.get(cache_key)
            if not analysis_results:
                analysis_results = json.loads(session.feedback) if session.feedback else None
            
            if not analysis_results:
                # Generate analysis using OpenAI
                analysis_results = self.analyze_interview_transcript(session)
                if analysis_results:
                    # Cache for 1 hour
                    cache.set(cache_key, analysis_results, 3600)
            
            if not analysis_results:
                messages.error(request, "Unable to analyze interview results. Please try again.")
                return redirect('interview_types')
            
            # Calculate session duration
            session_duration = self.calculate_session_duration(session)
            
            # Parse conversation history from transcript
            conversation_history = self.parse_conversation_history(session.transcript)
            
            context = {
                'session': session,
                'template': session.template,
                'analysis': analysis_results,
                # Main scores
                'overall_score': analysis_results.get('overall_score', 0),
                'confidence_level': analysis_results.get('confidence_level', 0),
                'communication_score': analysis_results.get('communication_score', 0),
                'engagement_score': analysis_results.get('engagement_score', 0),
                'technical_accuracy': analysis_results.get('technical_accuracy', 0),
                # Session metadata
                'session_duration': session_duration,
                # Skills assessment
                'skills_assessment': self.format_skills_assessment(analysis_results.get('skills_assessment', [])),
                # Feedback sections
                'strengths': self.format_feedback_items(analysis_results.get('detailed_feedback', {}).get('strengths', [])),
                'improvements': self.format_feedback_items(analysis_results.get('detailed_feedback', {}).get('areas_for_improvement', [])),
                'recommendations': self.format_feedback_items(analysis_results.get('detailed_feedback', {}).get('recommendations', [])),
                # Statistics
                'total_questions': analysis_results.get('statistics', {}).get('questions_asked', 0),
                'total_responses': analysis_results.get('statistics', {}).get('candidate_responses', 0),
                'words_spoken': analysis_results.get('statistics', {}).get('words_spoken', 0),
                'avg_response_time': self.extract_response_time_seconds(analysis_results.get('statistics', {}).get('avg_response_time', '0s')),
                # Conversation history
                'conversation_history': conversation_history,
            }
            print("Context for interview results:", context)  # Debug print
            if not session.feedback:
                self.update_session_feedback(session, context)
            
            return render(request, 'interview_results.html', context)
            
        except InterviewSession.DoesNotExist:
            messages.error(request, "Interview session not found.")
            return redirect('interview_types')
        except Exception as e:
            logger.error(f"Error in InterviewResultView: {e}")
            messages.error(request, "An error occurred while loading results.")
            return redirect('interview_types')

    def analyze_interview_transcript(self, session):
        """
        Analyze interview transcript using OpenAI and return structured results
        """

        try:
            return self.get_fallback_analysis()  # Temporary fallback for testing
            transcript = session.transcript
            template = session.template
            
            # Create analysis prompt
            analysis_prompt = self.create_analysis_prompt(transcript, template)
            
            # Call OpenAI API
            response = self.openai_client.chat.completions.create(
                model="gpt-4",  # or "gpt-4-turbo" for faster response
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert interview assessor. Analyze interview transcripts and provide detailed, constructive feedback in the exact JSON format requested."
                    },
                    {
                        "role": "user", 
                        "content": analysis_prompt
                    }
                ],
                temperature=0.3,  # Lower temperature for more consistent analysis
                max_tokens=2000
            )
            
            # Parse the response
            analysis_text = response.choices[0].message.content.strip()
            
            # Try to extract JSON from the response
            analysis_results = self.parse_analysis_response(analysis_text)
            
            return analysis_results
            
        except Exception as e:
            print(f"Error analyzing interview transcript: {e}")
            return None

    def create_analysis_prompt(self, transcript, template):
        """
        Create a detailed prompt for OpenAI analysis
        """
        prompt = f"""
Please analyze the following interview transcript and provide a comprehensive assessment.

**Interview Context:**
- Role Type: {template.get_role_type_display()}
- Difficulty Level: {template.get_difficulty_display()}
- Duration: {template.estimated_duration_minutes} minutes
- Interview Title: {template.title}
- Description: {template.description}

**Interview Transcript:**
{transcript}

**Analysis Requirements:**
Please provide your analysis in the following JSON format only. Do not include any other text outside the JSON:

{{
    "overall_score": <number between 0-100>,
    "confidence_level": <number between 0-100>,
    "communication_score": <number between 0-100>,
    "engagement_score": <number between 0-100>,
    "technical_accuracy": <number between 0-100>,
    "statistics": {{
        "questions_asked": <number>,
        "candidate_responses": <number>,
        "words_spoken": <estimated number>,
        "avg_response_time": "<time estimate like '15s'>"
    }},
    "detailed_feedback": {{
        "strengths": [
            "<strength 1>",
            "<strength 2>",
            "<strength 3>"
        ],
        "areas_for_improvement": [
            "<area 1>",
            "<area 2>",
            "<area 3>"
        ],
        "recommendations": [
            "<recommendation 1>",
            "<recommendation 2>",
            "<recommendation 3>"
        ]
    }},
    "skills_assessment": [
        {{
            "skill": "<skill name>",
            "score": <0-100>,
            "description": "<brief assessment>"
        }},
        {{
            "skill": "<skill name>",
            "score": <0-100>,
            "description": "<brief assessment>"
        }}
    ]
}}

**Scoring Criteria:**
- **Overall Score**: Holistic assessment based on role requirements, communication, and technical competency
- **Confidence Level**: Based on response clarity, voice tone, and engagement throughout the interview
- **Communication**: Effectiveness of verbal communication, clarity, and professional presentation
- **Engagement Score**: Level of interaction, enthusiasm, and active participation
- **Technical Accuracy**: Correctness and depth of technical responses (if applicable)

**Guidelines:**
1. Be constructive and specific in feedback
2. Provide actionable recommendations
3. Consider the role type and difficulty level in your assessment
4. Focus on both strengths and growth opportunities
5. Ensure scores reflect realistic performance levels
6. Base word count estimation on transcript length
7. Estimate response times based on conversation flow

Please ensure your response contains ONLY the JSON object with no additional formatting or explanation.
"""
        return prompt

    def parse_analysis_response(self, analysis_text):
        """
        Parse the OpenAI response and extract JSON analysis
        """
        try:
            # Try to find JSON in the response
            start_idx = analysis_text.find('{')
            end_idx = analysis_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx != -1:
                json_str = analysis_text[start_idx:end_idx]
                analysis_data = json.loads(json_str)
                
                # Validate required fields
                required_fields = [
                    'overall_score', 'confidence_level', 'communication_score',
                    'engagement_score', 'technical_accuracy', 'statistics',
                    'detailed_feedback', 'skills_assessment'
                ]
                
                for field in required_fields:
                    if field not in analysis_data:
                        logger.warning(f"Missing required field in analysis: {field}")
                        return None
                
                return analysis_data
            else:
                logger.error("No JSON found in OpenAI response")
                return None
                
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON from OpenAI response: {e}")
            logger.error(f"Response text: {analysis_text[:500]}...")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing analysis response: {e}")
            return None

    def calculate_session_duration(self, session):
        """Calculate interview duration in minutes"""
        try:
            if session.completed_at and session.created_at:
                duration = session.completed_at - session.created_at
                return int(duration.total_seconds() / 60)
            return session.template.estimated_duration_minutes
        except:
            return session.template.estimated_duration_minutes

    def format_skills_assessment(self, skills_data):
        """Format skills data for template"""
        formatted_skills = []
        for skill in skills_data:
            formatted_skills.append({
                'name': skill.get('skill', 'Unknown Skill'),
                'score': skill.get('score', 0),
                'feedback': skill.get('description', 'No feedback available')
            })
        return formatted_skills

    def format_feedback_items(self, feedback_list):
        """Format feedback items with titles and descriptions"""
        formatted_items = []
        for i, feedback in enumerate(feedback_list, 1):
            if isinstance(feedback, str):
                # Simple string feedback
                formatted_items.append({
                    'title': f'Point {i}',
                    'description': feedback
                })
            elif isinstance(feedback, dict):
                # Structured feedback
                formatted_items.append({
                    'title': feedback.get('title', f'Point {i}'),
                    'description': feedback.get('description', str(feedback))
                })
        return formatted_items

    def extract_response_time_seconds(self, time_str):
        """Extract numeric seconds from time string like '15s' or '2m 30s'"""
        try:
            if not time_str:
                return 0
            
            time_str = str(time_str).lower()
            total_seconds = 0
            
            # Extract minutes
            if 'm' in time_str:
                minutes_part = time_str.split('m')[0]
                if minutes_part.strip().isdigit():
                    total_seconds += int(minutes_part.strip()) * 60
            
            # Extract seconds
            if 's' in time_str:
                seconds_part = time_str.split('s')[0]
                if 'm' in time_str:
                    # Get seconds after minutes (e.g., "2m 30s" -> "30")
                    seconds_part = time_str.split('m')[1].replace('s', '').strip()
                else:
                    # Just seconds (e.g., "15s" -> "15")
                    seconds_part = seconds_part.strip()
                
                if seconds_part.isdigit():
                    total_seconds += int(seconds_part)
            
            return total_seconds
        except:
            return 0

    def parse_conversation_history(self, transcript):
        """Parse transcript into conversation history for template"""
        if not transcript:
            return []
        
        conversation_history = []
        lines = transcript.split('\n')
        current_item = None
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('==='):
                continue
                
            # Check for speaker indicators
            if line.startswith('[') and ']' in line:
                # New speaker entry like "[14:30:15] INTERVIEWER:" or "[14:30:45] CANDIDATE:"
                try:
                    # Extract timestamp and speaker
                    timestamp_end = line.index(']')
                    timestamp_str = line[1:timestamp_end]
                    remainder = line[timestamp_end + 1:].strip()
                    
                    if ':' in remainder:
                        speaker = remainder.split(':')[0].strip()
                        content_start = remainder.index(':') + 1
                        content = remainder[content_start:].strip()
                        
                        # Map speaker to role
                        role = 'assistant' if 'INTERVIEWER' in speaker.upper() else 'user'
                        
                        # Save previous item
                        if current_item:
                            conversation_history.append(current_item)
                        
                        # Create new item
                        current_item = {
                            'role': role,
                            'content': content,
                            'timestamp': self.parse_timestamp(timestamp_str)
                        }
                    
                except (ValueError, IndexError):
                    # If parsing fails, treat as continuation of current content
                    if current_item:
                        current_item['content'] += ' ' + line
                    
            else:
                # Continuation of current speaker's content
                if current_item:
                    if current_item['content']:
                        current_item['content'] += ' ' + line
                    else:
                        current_item['content'] = line
        
        # Add the last item
        if current_item:
            conversation_history.append(current_item)
        
        return conversation_history

    def parse_timestamp(self, timestamp_str):
        """Parse timestamp string to datetime object"""
        
        try:
            # Parse time like "14:30:15"
            time_parts = timestamp_str.split(':')
            if len(time_parts) == 3:
                hour, minute, second = map(int, time_parts)
                return time(hour, minute, second)
            elif len(time_parts) == 2:
                hour, minute = map(int, time_parts)
                return time(hour, minute, 0)
        except:
            pass
        
        # Return current time as fallback
        return datetime.now().time()

    def update_session_feedback(self, session, context):
        """
        Save the complete context data to session feedback field
        """
        try:
            # Create a clean copy of context without Django objects
            feedback_data = {
                'analysis_timestamp': str(datetime.now().isoformat()),
                'scores': {
                    'overall_score': context.get('overall_score', 0),
                    'confidence_level': context.get('confidence_level', 0),
                    'communication_score': context.get('communication_score', 0),
                    'engagement_score': context.get('engagement_score', 0),
                    'technical_accuracy': context.get('technical_accuracy', 0),
                },
                'session_duration': context.get('session_duration', 0),
                'skills_assessment': context.get('skills_assessment', []),
                'strengths': context.get('strengths', []),
                'improvements': context.get('improvements', []),
                'recommendations': context.get('recommendations', []),
                'statistics': {
                    'total_questions': context.get('total_questions', 0),
                    'total_responses': context.get('total_responses', 0),
                    'words_spoken': context.get('words_spoken', 0),
                    'avg_response_time': context.get('avg_response_time', 0),
                },
                'conversation_history': context.get('conversation_history', []),
                'template_info': {
                    'title': session.template.title,
                    'role_type': session.template.get_role_type_display(),
                    'difficulty': session.template.get_difficulty_display(),
                },
            }
            
            # Save to feedback field
            session.feedback = json.dumps(feedback_data)
            session.save(update_fields=['feedback'])
            
            logger.info(f"Context data saved to session {session.id} feedback field")
            return True
            
        except Exception as e:
            logger.error(f"Error saving context to session feedback: {e}")
            return False

    def get_fallback_analysis(self):
        """
        Provide fallback analysis if OpenAI fails
        """
        return {
            "overall_score": 75,
            "confidence_level": 70,
            "communication_score": 80,
            "engagement_score": 75,
            "technical_accuracy": 70,
            "statistics": {
                "questions_asked": 5,
                "candidate_responses": 5,
                "words_spoken": 500,
                "avg_response_time": "20s"
            },
            "detailed_feedback": {
                "strengths": [
                    "Good communication skills demonstrated",
                    "Professional demeanor throughout interview",
                    "Attempted to answer all questions"
                ],
                "areas_for_improvement": [
                    "Could provide more specific examples",
                    "Consider elaborating on technical details",
                    "Practice structuring responses more clearly"
                ],
                "recommendations": [
                    "Practice common interview questions",
                    "Prepare specific examples from experience", 
                    "Work on concise yet comprehensive answers"
                ]
            },
            "skills_assessment": [
                {
                    "skill": "Communication",
                    "score": 80,
                    "description": "Clear verbal communication"
                },
                {
                    "skill": "Problem Solving",
                    "score": 70,
                    "description": "Good analytical approach"
                }
            ]
        }
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
            profile = Profile.objects.get(user=request.user)
            if not profile.has_credit(required=template.estimated_duration_minutes):
                messages.error(request, "You don’t have enough credits. Please top up.")
                return redirect("purchase_credits")  # redirect to your top-up page
            # Check if user has an ongoing session for this template
            ongoing_session = InterviewSession.objects.filter(
                user=request.user,
                template=template,
                status='in_progress'
            ).first()
            
            if ongoing_session:
                # Redirect to existing session
                return redirect('interview_session', session_id=ongoing_session.id)
            profile.deduct_credits(used=template.estimated_duration_minutes)
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
            print(f"Error starting interview session: {e}")
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
    
    def get_overall_score(self, sessions):
        if not sessions:
            return 0
        total_score = 0
        count = 0
        for session in sessions:
            if session.feedback:
                try:
                    feedback_data = json.loads(session.feedback)
                    score = feedback_data.get('scores', {}).get('overall_score', 0)
                    total_score += score
                    count += 1
                except json.JSONDecodeError:
                    continue
        return int(total_score / count) if count > 0 else 0
    
    def recent_interviews(self, sessions, limit=5):
        res = []
        for session in sessions[:limit]:
            feedback = {}
            if session.feedback:
                try:
                    feedback = json.loads(session.feedback)
                except json.JSONDecodeError:
                    feedback = {}
            res.append({
                'session': session,
                'template': session.template,
                'overall_score': feedback.get('scores', {}).get('overall_score', None),
                'created_at': session.completed_at
            })
        return res
    
    def get(self, request):
        sessions = InterviewSession.objects.filter(user=request.user).order_by('-started_at')
        session_count = sessions.count()
        overall_score = self.get_overall_score(sessions)
        context = {
            "interview_count" : session_count,
            "avg_score" : overall_score,
            "recent_interviews" : self.recent_interviews(sessions),
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



@login_required 
@csrf_exempt
def process_purchase(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        
        # Create transaction record
        transaction = Transaction.objects.create(
            user=request.user,
            credits=int(data['credits']),
            amount=float(data['amount']),
            payment_method=data['payment_method'],
            status='pending'
        )
        
        # Mock payment processing
        success = mock_payment_processing(data)
        
        if success:
            transaction.status = 'success'
            transaction.save()
            
            # Update user credits
            profile = request.user.profile
            profile.credits += transaction.credits
            profile.save()
            
            return JsonResponse({
                'success': True,
                'transaction_id': str(transaction.transaction_id)
            })
        else:
            transaction.status = 'failed'
            transaction.error_message = 'Payment declined'
            transaction.save()
            
            return JsonResponse({
                'success': False,
                'transaction_id': str(transaction.transaction_id),
                'error': 'Payment processing failed'
            })

def mock_payment_processing(data):
    # Mock payment logic - 90% success rate
    # import random
    # return random.random() < 0.5
    return False

@login_required
def purchase_confirmation(request, transaction_id):
    transaction = get_object_or_404(Transaction, 
                                  transaction_id=transaction_id,
                                  user=request.user)
    
    return render(request, 'purchase_confirmation.html', {
        'transaction': transaction
    })

@login_required
def transaction_status(request, transaction_id):
    transaction = get_object_or_404(Transaction,
                                  transaction_id=transaction_id,
                                  user=request.user)
    
    return JsonResponse({
        'status': transaction.status,
        'credits': transaction.credits,
        'amount': str(transaction.amount)
    })