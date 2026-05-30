from django.shortcuts import render, redirect
from django.utils.text import slugify
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login as auth_login, update_session_auth_hash
from django.db.models import F
from django.core.cache import cache
# Named django_settings to avoid conflict with settings.py (my view)
from django.conf import settings as django_settings
from allauth.account.models import EmailAddress

from .forms import LoginForm, VexillologistCreationForm, VexillologistChangeForm, UsernameChangeForm, PasswordChangeForm
from .models import Country, Vexillologist
import random
import requests


def get_client_ip(request):
    """
    Behind Fly.io's proxy, REMOTE_ADDR is always Fly's internal IP, not the user's

    Fly sets the real client IP in the Fly-Client-IP header
    Falls back to X-Forwarded-For, then REMOTE_ADDR for local dev
    """
    fly_ip = request.META.get('HTTP_FLY_CLIENT_IP')
    if fly_ip:
        return fly_ip.strip()

    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        # Rightmost entry is the one the proxy itself saw (most trustworthy)
        return xff.split(',')[-1].strip()

    return request.META.get('REMOTE_ADDR', 'unknown')

"""
The key used to store the country list in the cache

The :v1 suffix is a versioning trick; if we ever change the shape of the
dictionaries below (add a key, rename one), we bump this to :v2 and all
old cached values simply age out on their own
"""
COUNTRIES_CACHE_KEY = 'countries:v1'

"""
How long (in seconds) to keep the cached list before Django discards it and
re-queries the database

The post_save/post_delete signals in models.py will also clear the cache immediately 
whenever an admin edits a Country record
"""
COUNTRIES_CACHE_TTL = 60 * 60  # 1 hour

def filter_countries(countries, query="", continent="", min_area=None, min_population=None, entry_type="", common_entry_types=None):
    query = (query or "").strip().lower()
    continent = (continent or "").strip()
    entry_type = (entry_type or "").strip()

    result = countries

    # Filter the countries based on the query, continent, entry type, min area, and min population
    if query:
        result = [c for c in result if c['name'].lower().startswith(query)]
    if continent:
        result = [c for c in result if (c.get('region') or "") == continent]
    if entry_type:
        result = [c for c in result if (c.get('entry_type') or "") == entry_type]
    if min_area is not None:
        result = [c for c in result if (c.get('area_km2') or 0) >= min_area]
    if min_population is not None:
        result = [c for c in result if (c.get('population_2024') or 0) >= min_population]

    return result

def get_countries():
    """
    1. Try the cache first
    
    cache.get() returns None on a cache miss
    
    On a hit it returns the previously stored list from RAM, no database round-trip
    """
    cached = cache.get(COUNTRIES_CACHE_KEY)
    if cached is not None:
        return cached

    """
    2. Cache miss: query the database and build the list of dicts
    
    Original code path, now only reached on the very first
    request (or after the cache expires / is invalidated by a signal)
    """
    result = [
        {
            'name': c.name,
            'flag_emoji': c.flag_emoji,
            'flag_image_url': c.flag_image_url,
            'capital': c.capital,
            'population_2024': c.population,
            'area_km2': c.area_km2,
            'official_language': c.official_language,
            'region': c.region,
            'entry_type': c.entry_type,
            'fact': c.fact,
        }
        for c in Country.objects.all().order_by('name')
    ]

    """
    3. Store the result in the cache so every subsequent call within the
    TTL window returns the in-memory copy instead of hitting the DB
    """
    cache.set(COUNTRIES_CACHE_KEY, result, COUNTRIES_CACHE_TTL)
    return result

GAMEMODES = {
    'world_tour': {
        'name': 'World Tour',
        # lambda is used to create an anonymous function that returns the countries list
        'filter': lambda countries: countries,
    },
    'north_america': {
        'name': 'North America',
        # countries only from North America
        'filter': lambda countries: [c for c in countries if c['region'] == 'North America'],
    },
    'south_america': {
        'name': 'South America',
        'filter': lambda countries: [c for c in countries if c['region'] == 'South America'],
    },
    'asia': {
        'name': 'Asia',
        'filter': lambda countries: [c for c in countries if c['region'] == 'Asia'],
    },
    'europe': {
        'name': 'Europe',
        'filter': lambda countries: [c for c in countries if c['region'] == 'Europe'],
    },
    'oceania': {
        'name': 'Oceania',
        'filter': lambda countries: [c for c in countries if c['region'] == 'Oceania'],
    },
    'africa': {
        'name': 'Africa',
        'filter': lambda countries: [c for c in countries if c['region'] == 'Africa'],
    },
    'autonomous_regions': {
        'name': 'Autonomous Regions',
        'filter': lambda countries: [c for c in countries if c['entry_type'] == 'Autonomous Region'],
    },
    'occupied_or_disputed_countries': {
        'name': 'Occupied or Disputed Countries',
        'filter': lambda countries: [c for c in countries if c['entry_type'] == 'Occupied or Disputed Country'],
    },
    'subnational_entities': {
        'name': 'Subnational Entities',
        'filter': lambda countries: [c for c in countries if c['entry_type'] == 'Subnational Entity'],
    },
}

def index(request):
    countries = get_countries()

    # Get the filter values from the HTMX GET request
    selected_query = request.GET.get("search_countries", "")
    selected_continent = request.GET.get("continent", "")
    selected_type = request.GET.get("entry_type", "")
    selected_min_area = request.GET.get("min_area", "")
    selected_min_population = request.GET.get("min_population", "")

    # Convert the min_area and min_population values to integers
    try:
        min_area = int(selected_min_area.strip()) if selected_min_area.strip() else None
    except ValueError:
        min_area = None
    try:
        min_population = int(selected_min_population.strip()) if selected_min_population.strip() else None
    except ValueError:
        min_population = None

    # Filter the countries based on the filter values
    filtered_countries = filter_countries(
        countries,
        query=selected_query,
        continent=selected_continent,
        min_area=min_area,
        min_population=min_population,
        entry_type=selected_type,
    )

    # Get the continents and entry types from the countries
    continents = sorted({
        (c.get('region') or "").strip()
        for c in countries
        if (c.get('region') or "").strip()
    })
    entry_types = sorted({
        (c.get('entry_type') or "").strip()
        for c in countries
        if (c.get('entry_type') or "").strip()
    })

    return render(request, 'index.html', context={
        'countries': filtered_countries,
        'continents': continents,
        'entry_types': entry_types,
        'selected_query': selected_query,
        'selected_continent': selected_continent,
        'selected_type': selected_type,
        'selected_min_area': selected_min_area,
        'selected_min_population': selected_min_population,
    })

def signup(request):
    # On the sign up page, get the form with post
    if request.method == 'POST':
        token = request.POST.get('g-recaptcha-response', '')
        # Verify the CAPTCHA with Google -- timeout so a slow Google can't freeze the site
        captcha_ok = False
        try:
            resp = requests.post('https://www.google.com/recaptcha/api/siteverify', data={
                'secret': django_settings.RECAPTCHA_SECRET_KEY,
                'response': token,
            }, timeout=(5, 10))
            captcha_ok = resp.json().get('success', False)
        except requests.exceptions.RequestException:
            pass  # Network error -- treat as failed CAPTCHA

        if not captcha_ok:
            messages.error(request, 'Please complete the CAPTCHA.')
            return render(request, 'signup.html', {
                'form': VexillologistCreationForm(),
                'recaptcha_site_key': django_settings.RECAPTCHA_SITE_KEY,
            })

        # If the CAPTCHA is successful, process the form
        form = VexillologistCreationForm(request.POST)
        # If the form is valid, save the user and login the user
        if form.is_valid():
            user = form.save()
            auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            # EmailAddress is from allauth.account.models for storing email addresses for users
            # create() creates a new email address record in the database
            email_address = EmailAddress.objects.create(
                user=user, email=user.email, primary=True, verified=False
            )
            # send_confirmation() generates the confirmation token and fires the email
            # signup=True tells allauth to use the signup-specific email template
            email_address.send_confirmation(request, signup=True)
            return redirect('index')
    else:
        form = VexillologistCreationForm()

    return render(request, 'signup.html', {
        'form': form,
        'recaptcha_site_key': django_settings.RECAPTCHA_SITE_KEY,
    })

def login_view(request):
    if request.method == 'POST':
        ip = get_client_ip(request)
        cache_key = f'login_attempts_{ip}'
        attempts = cache.get(cache_key, 0)

        if attempts >= 5:
            messages.error(request, 'Too many login attempts. Please wait a minute and try again.')
            return render(request, 'login.html', {'form': LoginForm()})

        form = LoginForm(request.POST)
        # If the form is valid, delete the cache key and login the user
        if form.is_valid():
            cache.delete(cache_key)
            auth_login(request, form.user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('index')
        else:
            # Set the cache key to the number of attempts + 1, and the timeout to 60 seconds
            cache.set(cache_key, attempts + 1, 60)
    else:
        form = LoginForm()
    return render(request, 'login.html', {'form': form})

def search_countries(request):
    countries = get_countries()
    
    # Get the filter values from the HTMX GET request
    query = request.GET.get("search_countries", "")
    continent = request.GET.get("continent", "")
    entry_type = request.GET.get("entry_type", "")
    min_area_raw = request.GET.get("min_area", "")
    min_population_raw = request.GET.get("min_population", "")

    # Convert the min_area and min_population values to integers
    try:
        min_area = int(min_area_raw.strip()) if min_area_raw.strip() else None
    except ValueError:
        min_area = None
    try:
        min_population = int(min_population_raw.strip()) if min_population_raw.strip() else None
    except ValueError:
        min_population = None

    # Filter the countries based on the filter values
    filtered_countries = filter_countries(
        countries,
        query=query,
        continent=continent,
        min_area=min_area,
        min_population=min_population,
        entry_type=entry_type,
    )

    return render(request, "list.html", context={'countries': filtered_countries })

def search_guesses(request):
    countries = get_countries()
    query = request.GET.get("guess", "")
    filtered_countries = filter_countries(countries, query=query)
    return render(request, "guesses.html", context={'countries': filtered_countries })

@login_required
def country(request, country_name):
    countries = get_countries()
    # Slugify makes it a cleaner string
    chosen_country = [country for country in countries if slugify(country['name']) == country_name]
    if chosen_country:
        return render(request, 'country.html', context={'chosen_country': chosen_country[0]})
    else:
        return redirect("/")

def quiz(request):
    """
    Reworked to use session data instead of hidden form fields
    
    Hidden form fields are vulnerable to tampering (a player could edit the streak value in DevTools)
    
    Session data is stored server-side so only the server can modify it

    request.session is a dictionary-like object. We set keys on it just like a regular dict. 
    
    Django automatically saves it and associates it with this user's session ID cookie
    """
    if request.method == "GET":
        """
        After a POST guess, the POST handler redirects here and leaves a 'quiz_result' key in the session with the outcome of that guess
        
        pop() reads it and immediately removes it so a second refresh won't re-display it 
        (it's consumed exactly once, like a flash message)
        """
        result = request.session.pop('quiz_result', None)
        # Get the gamemode key from the session, default to world_tour if not set
        gamemode_key = request.session.get('quiz_gamemode', 'world_tour')
        gamemode_name = GAMEMODES.get(gamemode_key, GAMEMODES['world_tour'])['name']

        if result:
            # Continuing an in-progress game after a guess redirect
            # The POST already chose the next country and wrote it to the session,
            # so we don't need to touch get_countries() at all here
            random_country = request.session.get('quiz_country')
            streak = request.session.get('quiz_streak', 0)
            collected_flags = request.session.get('quiz_collected_flags', [])
            
            return render(request, 'quiz.html', context={
                'random_country': random_country,
                'streak': streak,
                'collected_flags': collected_flags,
                'game_over': result['game_over'],
                'game_won': result.get('game_won', False),
                'final_streak': result['final_streak'],
                'final_collected_flags': result['final_collected_flags'],
                'truth_name': result.get('truth_name', ''),
                'truth_flag': result.get('truth_flag', ''),
                'gamemode_name': gamemode_name,
                'pool_size': request.session.get('quiz_pool_size', 0),
            })

        # No gamemode selected yet: show the gamemode selection screen
        if 'quiz_gamemode' not in request.session:
            countries = get_countries()
            # Get the set of country names the authenticated user has mastered
            # If the user is not logged in, use an empty set
            if request.user.is_authenticated:
                # Get all mastered flag Country names for the current user as a set
                mastered_flag_names_queryset = request.user.mastered_flags.values_list('name', flat=True)
                mastered_names = set(mastered_flag_names_queryset)
            else:
                mastered_names = set()
 
            gamemode_progress = {
                key: {
                    'mastered': len({c['name'] for c in gm['filter'](countries)} & mastered_names),
                    'total': len(gm['filter'](countries)),
                }
                for key, gm in GAMEMODES.items()
            }
            return render(request, 'quiz.html', context={
                'show_gamemode_select': True,
                'gamemode_progress': gamemode_progress,
            })

        # Fresh page load with a gamemode set - reset all game state
        gm = GAMEMODES.get(gamemode_key, GAMEMODES['world_tour'])
        pool = gm['filter'](get_countries())
        random_country = random.choice(pool) if pool else None
        
        request.session['quiz_country'] = random_country
        request.session['quiz_streak'] = 0
        request.session['quiz_collected_flags'] = []
        request.session['quiz_collected_names'] = []
        
        return render(request, 'quiz.html', context={
            'random_country': random_country,
            'streak': 0,
            'collected_flags': [],
            'gamemode_name': gamemode_name,
            'pool_size': request.session.get('quiz_pool_size', 0),
        })

    elif request.method == "POST":
        # Handle gamemode selection (submitted from the gamemode picker screen)
        gamemode = request.POST.get('gamemode')
        if gamemode:
            gm = GAMEMODES.get(gamemode, GAMEMODES['world_tour'])
            pool = gm['filter'](get_countries())
            request.session['quiz_gamemode'] = gamemode
            request.session['quiz_pool_size'] = len(pool)
            return redirect('quiz')
        """
        Read game state from the server-side session, not from POST data
        
        request.session.get(key, default) reads the value back from the
        server-side session that was stored on the previous GET/POST
        """
        truth = request.session.get('quiz_country')
        streak = request.session.get('quiz_streak', 0)
        collected_flags = request.session.get('quiz_collected_flags', [])
        collected_names = request.session.get('quiz_collected_names', [])

        if not truth:
            return redirect('quiz')

        # Get the guess from the POST data
        guess = request.POST.get('guess', '').strip()
        truth_name = truth['name']
        truth_flag = truth['flag_image_url']
    
        user = request.user
        # Anonymous players can still play; we just skip persisting their progress
        is_authenticated = user.is_authenticated
        # Get the gamemode key from the session, default to world_tour if not set
        gamemode_key = request.session.get('quiz_gamemode', 'world_tour')
        pool_size = request.session.get('quiz_pool_size', 0)

        update_fields = []

        game_over = False
        game_won = False
        final_streak = 0
        final_collected_flags = []

        if truth_name.lower() == guess.lower():
            streak += 1
            collected_flags = collected_flags + [truth_flag]
            collected_names = collected_names + [truth_name]

            if is_authenticated and streak > user.high_score:
                user.high_score = streak
                update_fields.append('high_score')

            # Win condition: player has guessed every country in the pool
            if pool_size > 0 and len(collected_names) >= pool_size:
                game_won = True
                final_streak = streak
                final_collected_flags = collected_flags[:]
                if is_authenticated:
                    if collected_names:
                        mastered = Country.objects.filter(name__in=collected_names)
                        user.mastered_flags.add(*mastered)
                    user.games_played = F('games_played') + 1
                    update_fields.append('games_played')
                streak = 0
                collected_flags = []
                collected_names = []
            else:
                messages.success(request, f"Correct 🥳 It was {truth_name}!")

        else:
            game_over = True
            final_streak = streak
            final_collected_flags = collected_flags[:]

            if is_authenticated:
                if collected_names:
                    mastered = Country.objects.filter(name__in=collected_names)
                    user.mastered_flags.add(*mastered)
                user.games_played = F('games_played') + 1
                update_fields.append('games_played')
            streak = 0
            collected_flags = []
            collected_names = []
            messages.error(request, f"Noooo 😢 it was {truth_name}")

        # Only hit the database if there is actually something to update
        if update_fields:
            user.save(update_fields=update_fields)

        # Pick the next country from the gamemode pool, excluding already-collected ones
        gm = GAMEMODES.get(gamemode_key, GAMEMODES['world_tour'])
        pool = gm['filter'](get_countries())
        if not pool:
            return redirect('quiz')
        available = [c for c in pool if c['name'] not in collected_names]
        if not available:
            available = pool
            
        random_country = random.choice(available)
        request.session['quiz_country'] = random_country
        request.session['quiz_streak'] = streak
        request.session['quiz_collected_flags'] = collected_flags
        request.session['quiz_collected_names'] = collected_names

        # Store the result in the session and redirect to GET (prevents form resubmission on refresh)
        request.session['quiz_result'] = {
            'game_over': game_over,
            'game_won': game_won,
            'final_streak': final_streak,
            'final_collected_flags': final_collected_flags,
            'truth_name': truth_name if not game_won else '',
            'truth_flag': truth_flag if not game_won else '',
        }
        return redirect('quiz')

    else:
        return redirect('quiz')

def change_gamemode(request):
    """Clear all quiz session state so the player is returned to the gamemode selection screen."""
    if request.method != 'POST':
        return redirect('quiz')
    for key in ['quiz_gamemode', 'quiz_country', 'quiz_streak',
                'quiz_collected_flags', 'quiz_collected_names', 'quiz_result', 'quiz_pool_size']:
        request.session.pop(key, None)
    return redirect('quiz')

@login_required
def leaderboard(request):
    top_players = Vexillologist.objects.order_by('-high_score')[:10]
    return render(request, 'leaderboard.html', {'top_players': top_players, 'current_user': request.user})

@login_required
def mastery(request):
    countries = get_countries()
    # Fetch just the names of countries this user has already mastered
    # A flat list query is cheaper than loading full Country objects
    mastered_names = set(request.user.mastered_flags.values_list('name', flat=True))
    entries = [
        # **c is a dictionary unpacking operation, it unpacks the dictionary c into the dictionary entries
        {**c, 'mastered': c['name'] in mastered_names}
        for c in countries
    ]
    return render(request, 'mastery.html', {
        'entries': entries,
        'mastered_count': len(mastered_names),
        'total_count': len(countries),
    })

def about(request):
    return render(request, 'about.html')

def privacy(request):
    return render(request, 'privacy.html')

def contact(request):
    return render(request, 'contact.html')

def release_notes(request):
    return render(request, 'release_notes.html')

@login_required
def settings(request):
    profile_form = VexillologistChangeForm(instance=request.user)
    username_form = UsernameChangeForm(instance=request.user)
    password_form = PasswordChangeForm(user=request.user)

    if request.method == 'POST':
        form_type = request.POST.get('form_type')

        if form_type == 'profile':
            # 'instance' parameter tells the Django form which record to update
            # Necessary since we are updating (current logged-in user) rather than creating
            profile_form = VexillologistChangeForm(request.POST, instance=request.user)
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, 'Profile updated!')
                return redirect('settings')

        elif form_type == 'username':
            username_form = UsernameChangeForm(request.POST, instance=request.user)
            if username_form.is_valid():
                username_form.save()
                messages.success(request, 'Username updated!')
                return redirect('settings')

        elif form_type == 'password':
            password_form = PasswordChangeForm(user=request.user, data=request.POST)
            if password_form.is_valid():
                password_form.save()
                update_session_auth_hash(request, password_form.user)
                messages.success(request, 'Password updated!')
                return redirect('settings')

    email_record = EmailAddress.objects.filter(user=request.user, primary=True).first()
    email_verified = email_record.verified if email_record else False
    return render(request, 'settings.html', {
        'form': profile_form,
        'username_form': username_form,
        'password_form': password_form,
        'email_verified': email_verified,
    })

@login_required
def resend_confirmation(request):
    # If the user clicks the "Resend Confirmation Email" button, this view is called
    if request.method == 'POST':
        '''
        get_or_create() creates a new email address record in the database if it doesn't exist
        
        get_or_create always returns a 2-tuple (instance, created_bool)
        
        The object we want and a boolean for whether it was just created. Without unpacking it, email_record was holding the whole tuple, hence the error. 
        
        The , _ discards the boolean since we don't need it.
        '''
        email_record, _ = EmailAddress.objects.get_or_create(
            user=request.user,
            defaults={'email': request.user.email, 'primary': True, 'verified': False},
        )
        if email_record.verified:
            messages.info(request, 'Your email is already confirmed.')
        else:
            email_record.send_confirmation(request)
            messages.success(request, 'Confirmation email sent! Check your inbox.')
    return redirect('settings')

@login_required
def delete_account(request):
    if request.method == 'POST':
        user = request.user
        user.delete()
        messages.success(request, 'Your account has been successfully deleted.')
        return redirect('index')
    return redirect('settings')