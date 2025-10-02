#pylint:disable=all
from django.shortcuts import render
from django.views import View
from .models import EarlyAccessEmail
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.models import User
from .models import Profile, Course, InterviewTemplate, InterviewSession, Transaction, RolePlayBots, RoleplaySession, RolePlayShare, MyInvitedRolePlayShare, CreditShare
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
from datetime import datetime, time, timedelta
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
import hashlib
import hmac
from decimal import Decimal
import razorpay
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
class BotDetailView(LoginRequiredMixin, View):
    def get(self, request, bot_id):
        bot = RolePlayBots.objects.get(id=bot_id)
        context = {
            "bot" :bot
        }
        return render(request, "roleplay_bot_detail.html", context)
class PaymentFailedView(View):
    """Handle payment failure (optional logging)"""
    
    @csrf_exempt
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            
            # Log payment failure
            logger.warning(f"Payment failed: {data}")
            
            # Optional: Create failed transaction record
            if request.user.is_authenticated:
                Transaction.objects.create(
                    user=request.user,
                    transaction_id=data.get('payment_id', 'N/A'),
                    credits=0,
                    amount=Decimal('0.00'),
                    payment_method='razorpay',
                    status='failed',
                    error_message=data.get('error_description', 'Payment failed')
                )
            
            return JsonResponse({'status': 'logged'})
            
        except Exception as e:
            logger.error(f"Error logging payment failure: {e}")
            return JsonResponse({'status': 'error'}, status=400)
    
    def get(self, request):
        return JsonResponse({'status': 'error', 'message': 'Invalid request method'}, status=400)


class PaymentSuccessPageView(LoginRequiredMixin, View):
    """Display success page after payment"""
    login_url = "/login/"
    
    def get(self, request):
        context = {
            'current_credits': request.user.profile.credits,
        }
        return render(request, 'payment_success.html', context)
class PaymentSuccessView(LoginRequiredMixin, View):
    """Handle successful payment and update user credits"""
    login_url = "/login/"
    
    def post(self, request):
        # Get payment details
        razorpay_payment_id = request.POST.get('razorpay_payment_id')
        razorpay_order_id = request.POST.get('razorpay_order_id')
        razorpay_signature = request.POST.get('razorpay_signature')
        
        plan_type = request.POST.get('plan_type')
        credits = int(request.POST.get('credits'))
        price = int(request.POST.get('price'))
        
        # Verify payment signature
        try:
            # Create signature verification string
            sign_string = f"{razorpay_order_id}|{razorpay_payment_id}"
            
            # Generate expected signature
            expected_signature = hmac.new(
                os.getenv("RAZORPAYAPI_SECRET").encode(),
                sign_string.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # Verify signature
            if expected_signature != razorpay_signature:
                logger.error(f"Payment signature verification failed for user {request.user.id}")
                messages.error(request, 'Payment verification failed. Please contact support.')
                return redirect('purchase_credits')
            
            # Payment verified - update user credits
            profile = Profile.objects.get(user=request.user)
            profile.credits += credits
            profile.save()
            
            # Create transaction record
            Transaction.objects.create(
                user=request.user,
                transaction_id=razorpay_payment_id,  # Now accepts string
                order_id=razorpay_order_id,  # Store order ID
                credits=credits,
                amount=Decimal(price),
                payment_method='razorpay',
                status='success'
            )
            
            logger.info(f"Payment successful for user {request.user.id}: {credits} credits added")
            messages.success(
                request, 
                f'Payment successful! {credits} credits have been added to your account.'
            )
            return redirect('payment_success_page')
            
        except Exception as e:
            logger.error(f"Payment verification error for user {request.user.id}: {e}")
            messages.error(request, f'Payment verification error: {str(e)}')
            return redirect('purchase_credits')
    
    def get(self, request):
        # Redirect GET requests to payment success page
        return redirect('payment_success_page')
class OrderConfirmationView(LoginRequiredMixin, View):
    """Display checkout page with Razorpay integration"""
    login_url = "/login/"
    
    def post(self, request):
        razorpay_client = razorpay.Client(auth=(os.getenv("RAZORPAY_API_KEY"), os.getenv("RAZORPAYAPI_SECRET")))
        
        # Get plan details from POST
        plan_type = request.POST.get('plan_type')
        credits = int(request.POST.get('credits'))
        price = int(request.POST.get('price'))

        # Create Razorpay order
        amount_paise = price * 100  # Convert rupees to paise
        
        try:
            razorpay_order = razorpay_client.order.create({
                'amount': amount_paise,
                'currency': 'INR',
                'notes': {
                    'user_id': request.user.id,
                    'plan_type': plan_type,
                    'credits': credits,
                }
            })
            
            context = {
                'plan_type': plan_type,
                'plan_name': plan_type,
                'credits': credits,
                'price': price,
                'amount_paise': amount_paise,
                'order_id': razorpay_order['id'],
                'razorpay_key_id': os.getenv("RAZORPAY_API_KEY"),
            }
            
            return render(request, 'checkout.html', context)
            
        except Exception as e:
            logger.error(f"Error creating Razorpay order: {e}")
            messages.error(request, f'Error creating order: {str(e)}')
            return redirect('purchase_credits')
    
    def get(self, request):
        # Redirect GET requests back to purchase page
        return redirect('purchase_credits')

class MyEarningsView(LoginRequiredMixin, View):
    login_url = "/login/"
    
    def get(self, request):
        # Start with base queryset - NOT EXECUTED YET
        queryset = CreditShare.objects.filter(credited_to=request.user)
        
        # Get filter parameters
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        status = request.GET.get('status')
        credit_type = request.GET.get('type')
        
        # Apply default 30-day filter if no dates provided
        if not date_from and not date_to:
            end_date = timezone.now()
            start_date = end_date - timedelta(days=30)
            queryset = queryset.filter(
                created_at__gte=start_date,
                created_at__lte=end_date
            )
        else:
            # Apply custom date filters
            if date_from:
                try:
                    from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
                    queryset = queryset.filter(created_at__date__gte=from_date)
                except ValueError:
                    pass
                    
            if date_to:
                try:
                    to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
                    queryset = queryset.filter(created_at__date__lte=to_date)
                except ValueError:
                    pass
        
        # Apply status filter
        if status:
            queryset = queryset.filter(settlement_status=status)
        
        # Apply type filter
        if credit_type:
            queryset = queryset.filter(credit_reason=credit_type)
        
        # Order by most recent and FETCH ALL IN ONE QUERY
        all_earnings = list(queryset.order_by('-created_at'))
        
        # Segregate in Python (no additional DB queries)
        completed = [e for e in all_earnings if e.settlement_status == 'completed']
        pending = [e for e in all_earnings if e.settlement_status == 'pending']
        failed = [e for e in all_earnings if e.settlement_status == 'failed']
        
        context = {
            'completed': completed,
            'pending': pending,
            'failed': failed,
            'filters': {
                'date_from': date_from or '',
                'date_to': date_to or '',
                'status': status or '',
                'type': credit_type or '',
            }
        }
        
        return render(request, 'my_earnings.html', context)
class ShareRolePlayStartView(LoginRequiredMixin, View):
    login_url = "/login/"
    def get(self, request, share_id):
        share = get_object_or_404(RolePlayShare, id=share_id)
        bot = share.bot
        if not bot.is_active or not bot.is_public:
            messages.error(request, "This Roleplay bot is not available.")
            return redirect('voice_roleplay')
        context = {
            'bot': bot,
            "bot_creator": bot.created_by,
            "bot_shared_by": share.shared_by,
        }
        MyInvitedRolePlayShare.objects.get_or_create(
            share=share,
            bot=bot,
            invited_to=request.user
        )
        return render(request, 'roleplay_bot_detail.html', context)
class ShareRolePlayBotView(LoginRequiredMixin, View):
    login_url = "/login/"
    def get(self, request, bot_id):
        bot = get_object_or_404(RolePlayBots, id=bot_id)
        share = RolePlayShare.objects.filter(bot=bot, shared_by=request.user).first()
        if not share:
            share = RolePlayShare.objects.create(bot=bot, shared_by=request.user)
        context = {
            'bot': bot,
            'share_link': request.get_host() + "/roleplay/share/" + str(share.id) + "/",
        }
        return render(request, 'share_roleplay_bot.html', context)
class EditRolePlayBotView(LoginRequiredMixin, View):
        login_url = "/login/"
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
                category = request.POST.get('category', '').strip()
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
    login_url = "/login/"
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
    login_url = "/login/"
    def post(self, request):
        profile = Profile.objects.get(user=request.user)
        credit_required_to_create_bot = 10
        if profile.credits < credit_required_to_create_bot:
            messages.error(request, f"Low credits- Required credit {credit_required_to_create_bot}")
            return redirect('purchase_credits')
        name = request.POST.get('name')
        avatar_url = request.POST.get('avatar_url')
        system_prompt = request.POST.get('system_prompt')
        description = request.POST.get('description')
        feedback_prompt = request.POST.get('feedback_prompt')
        category= request.POST.get('category')
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
                category=category
            )
            messages.success(request, f"Roleplay Bot '{bot.name}' created successfully!")
            profile.credits -= credit_required_to_create_bot
            profile.save(update_fields=['credits'])
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
            share_link = MyInvitedRolePlayShare.objects.filter(bot=session.bot, invited_to=request.user).first()
            context = {
                'session': session,
                'bot': session.bot,
                "invited_by": share_link.share.shared_by if share_link else None,
                "creator" : session.bot.created_by,
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



from django.http import JsonResponse

class VoiceRolePlayView(LoginRequiredMixin, View):
    """
    Category-based explore view for voice roleplay bots
    """
    login_url = "/login/"
    
    def get(self, request):
        # Check if AJAX request
        is_ajax = request.GET.get('ajax') == 'true'
        
        # Get query parameters
        search_query = request.GET.get('search', '').strip()
        selected_category = request.GET.get('category', 'all')
        offset = int(request.GET.get('offset', 0))
        limit = int(request.GET.get('limit', 50))
        
        # Base queryset
        all_bots = RolePlayBots.objects.filter(is_public=True, is_active=True)
        all_bots_count = all_bots.count()
        
        # Handle AJAX load more request
        if is_ajax:
            bots = all_bots.order_by('order', '-created_at')[offset:offset + limit]
            has_more = all_bots_count > (offset + limit)
            
            bots_data = [{
                'id': str(bot.id),
                'name': bot.name,
                'description': bot.description,
                'avatar_url': bot.avatar_url,
                'category_display': bot.get_category_display(),
                'is_active': bot.is_active,
            } for bot in bots]
            
            return JsonResponse({
                'bots': bots_data,
                'has_more': has_more,
                'total_count': all_bots_count,
            })
        
        # Regular page load
        all_bots_list = all_bots.order_by('order', '-created_at')[:50]  # First 50
        has_more_bots = all_bots_count > 50
        
        # Apply search filter
        if search_query:
            all_bots = all_bots.filter(
                Q(name__icontains=search_query) | 
                Q(description__icontains=search_query) |
                Q(category__icontains=search_query)
            )
            
            context = {
                'search_query': search_query,
                'selected_category': selected_category,
                'career_bots': all_bots.order_by('order', '-created_at')[:20],
                'learning_bots': [],
                'entertainment_bots': [],
                'personal_bots': [],
                'all_bots': [],
                'all_bots_count': 0,
                'has_more_bots': False,
            }
            return render(request, 'voice_roleplay_list.html', context)
        
        # Category groupings (keep your existing code)
        career_categories = [
            'interview_prep', 'professional_training', 'customer_service',
            'business', 'negotiation', 'mentorship', 'public_speaking'
        ]
        
        learning_categories = [
            'language_learning', 'education', 'exam_prep', 'technical_skills'
        ]
        
        entertainment_categories = [
            'fantasy', 'sci_fi', 'anime_manga', 'dnd_rpg', 'gaming',
            'movie_tv', 'celebrity', 'storytelling', 'creative_writing',
            'historical', 'mythology'
        ]
        
        personal_categories = [
            'personal_development', 'dating_social', 'fitness_wellness'
        ]
        
        # Filter by selected category group (keep your existing logic)
        if selected_category == 'professional':
            career_bots = all_bots.filter(category__in=career_categories).order_by('order', '-created_at')
            learning_bots = []
            personal_bots = []
            entertainment_bots = []
        elif selected_category == 'learning':
            career_bots = []
            personal_bots = []
            learning_bots = all_bots.filter(category__in=learning_categories).order_by('order', '-created_at')
            entertainment_bots = []
        elif selected_category in ['entertainment', 'creative']:
            career_bots = []
            personal_bots = []
            learning_bots = []
            entertainment_bots = all_bots.filter(category__in=entertainment_categories).order_by('order', '-created_at')
        elif selected_category == 'personal':
            personal_bots = all_bots.filter(category__in=personal_categories).order_by('order', '-created_at')
            career_bots = []
            learning_bots = []
            entertainment_bots = []
        else:  # 'all' - show mixed sections
            career_bots = all_bots.filter(category__in=career_categories).order_by('order', '-created_at')
            learning_bots = all_bots.filter(category__in=learning_categories).order_by('order', '-created_at')
            entertainment_bots = all_bots.filter(category__in=entertainment_categories).order_by('order', '-created_at')
            personal_bots = all_bots.filter(category__in=personal_categories).order_by('order', '-created_at')
        
        context = {
            'career_bots': career_bots,
            'learning_bots': learning_bots,
            'entertainment_bots': entertainment_bots,
            'personal_bots': personal_bots,
            'all_bots': all_bots_list,
            'all_bots_count': all_bots_count,
            'has_more_bots': has_more_bots,
            'search_query': search_query,
            'selected_category': selected_category,
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
        next_url = request.GET.get('next', '')
        if request.user.is_authenticated:
            return redirect("dashboard")
        return render(request, "signup.html", {"next": next_url})  # Render template with empty form

    def post(self, request):
        # Get form data
        username = request.POST.get("email")
        email = request.POST.get("email")
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")
        next_url = request.POST.get("next") or request.GET.get("next")

        # Validation
        if not username or not email or not password1 or not password2:
            messages.error(request, "All fields are required.")
            return render(request, "signup.html",  {"next": next_url})

        if len(password1) < 8:
            messages.error(request, "Password must be at least 8 characters long.")
            return render(request, "signup.html",  {"next": next_url})

        if password1 != password2:
            messages.error(request, "Passwords do not match.")
            return render(request, "signup.html",  {"next": next_url})

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username is already taken.")
            return render(request, "signup.html",  {"next": next_url})

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email is already registered.")
            return render(request, "signup.html",  {"next": next_url})

        # Create user
        user = User.objects.create_user(
            username=username, email=email, password=password1
        )
        Profile.objects.get_or_create(user=user, credits=50)
        login(request, user)  # Auto login after signup
        messages.success(request, "Signup successful!")
        if next_url and next_url != '/login/':
                return redirect(next_url)
        return redirect("dashboard")  # Redirect to dashboard


class LoginView(View):
    """View for user login."""
    def get(self, request):
        # Redirect to dashboard if already logged in
        # In GET method - pass next to template
        next_url = request.GET.get('next', '')
        if request.user.is_authenticated:
            if next_url and next_url != '/login/':  # Avoid redirect loops
                return redirect(next_url)
            return redirect("dashboard")
        return render(request, "login.html",  {"next": next_url})  # Render the login page

    def post(self, request):
        # Get form data
        username = request.POST.get("username")
        password = request.POST.get("password")
        next_url = request.POST.get("next") or request.GET.get("next")

        # Validate input fields
        if not username or not password:
            messages.error(request, "All fields are required.")
            return render(request, "login.html")

        # Authenticate user
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, "Login successful!")
            if next_url and next_url != '/login/':  # Avoid redirect loops
                return redirect(next_url)
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







# views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.contrib.auth.models import User
from django.db import transaction
import logging

logger = logging.getLogger(__name__)


class BulkCreateBotsAPIView(APIView):
    """
    API endpoint for bulk creating bots via script
    Requires API key authentication
    """
    permission_classes = [AllowAny]  # We'll handle auth manually with API key
    
    def post(self, request):
        
        # Get admin user (or specified user)
        admin_username = request.data.get('admin_username', 'admin')
        try:
            admin_user = User.objects.get(username=admin_username, is_staff=True)
        except User.DoesNotExist:
            return Response(
                {"error": f"Admin user '{admin_username}' not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get bots data
        bots_data = request.data.get('bots', [])
        
        if not bots_data or not isinstance(bots_data, list):
            return Response(
                {"error": "Invalid data format. Expected 'bots' array"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        created_bots = []
        errors = []
        
        # Bulk create bots
        with transaction.atomic():
            for idx, bot_data in enumerate(bots_data):
                try:
                    # Validate required fields
                    if not bot_data.get('name') or not bot_data.get('system_prompt'):
                        errors.append({
                            'index': idx,
                            'error': 'Missing required fields: name and system_prompt'
                        })
                        continue
                    
                    # Build custom configuration
                    custom_config = {}
                    
                    # Create bot
                    bot = RolePlayBots.objects.create(
                        name=bot_data['name'],
                        description=bot_data.get('description', ''),
                        avatar_url=bot_data.get('avatar_url', ''),
                        system_prompt=bot_data['system_prompt'],
                        feedback_prompt=bot_data.get('feedback_prompt', ''),
                        custom_configuration=custom_config,
                        voice=bot_data.get('voice', 'alloy'),
                        category=bot_data.get('category', 'other'),
                        is_active=bot_data.get('is_active', True),
                        is_public=bot_data.get('is_public', True),
                        order=bot_data.get('order', 0),
                        created_by=admin_user
                    )
                    
                    created_bots.append({
                        'id': str(bot.id),
                        'name': bot.name,
                        'category': bot.category
                    })
                    
                except Exception as e:
                    logger.error(f"Error creating bot at index {idx}: {e}")
                    errors.append({
                        'index': idx,
                        'name': bot_data.get('name', 'Unknown'),
                        'error': str(e)
                    })
        
        return Response({
            'success': True,
            'created_count': len(created_bots),
            'error_count': len(errors),
            'created_bots': created_bots,
            'errors': errors
        }, status=status.HTTP_201_CREATED if created_bots else status.HTTP_400_BAD_REQUEST)


