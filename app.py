from flask import Flask, render_template, request, redirect, url_for, session, flash
import json
import os
import hashlib
import datetime
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from gtts import gTTS
import playsound
import tempfile
from flask_login import login_required

import time


app = Flask(__name__)
app.secret_key = '9be8967f3f5464751d17aa6d24262123'  # Change this to a random secret key in production

# File to store user data
USER_FILE = 'user.json'

# Initialize user.json if it doesn't exist
if not os.path.exists(USER_FILE):
    with open(USER_FILE, 'w') as f:
        json.dump({}, f)

# Function to load user data
def load_users():
    try:
        with open(USER_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

# Function to save user data
def save_users(users):
    with open(USER_FILE, 'w') as f:
        json.dump(users, f, indent=4)

# Hash password
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Login required decorator
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Configure LangChain with Gemini API
llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key="AIzaSyB7E6nRyakki3o6cyiDiwLGw0PilhrFsWQ")

# LangChain Prompt Template for Single Word Translation
translation_prompt = PromptTemplate(
    input_variables=["input_lang", "target_lang", "word"],
    template="Translate the word '{word}' from {input_lang} to {target_lang}. Provide only a multiple-words translation."
)

# Combine the prompt with the LLM
translation_chain = translation_prompt | llm

# Routes
@app.route('/')
@login_required
def index():
    return render_template('index.html', username=session['username'])

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        users = load_users()
        
        # Check if username already exists
        if username in users:
            flash('Username already exists')
            return render_template('signup.html')
        
        # Create new user
        users[username] = {
            'email': email,
            'password': hash_password(password),
            'points': 0,
            'last_claim_date': '',
            'translation_history': []
        }
        
        save_users(users)
        flash('Account created successfully! Please log in.')
        return redirect(url_for('login'))
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        users = load_users()
        
        # Check if username exists and password is correct
        if username in users and users[username]['password'] == hash_password(password):
            session['username'] = username
            
            # Check for daily points
            today = datetime.datetime.now().strftime('%Y-%m-%d')
            if users[username]['last_claim_date'] != today:
                users[username]['points'] += 10
                users[username]['last_claim_date'] = today
                save_users(users)
                flash('You claimed 10 points today!')
            
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))


@app.route('/translate', methods=['POST'])
@login_required
def translate():
    # Get user input
    source_lang = request.form['source_lang']
    target_lang = request.form['target_lang']
    word = request.form['word']

    try:
        # Get translation
        translated_text = translation_chain.invoke({
            "input_lang": source_lang,
            "target_lang": target_lang,
            "word": word
        })

        # Extract translation text
        translation = translated_text.content.strip() if hasattr(translated_text, "content") else str(translated_text)

        # Generate TTS and save audio file in static folder
        audio_filename = f"tts_{int(time.time())}.mp3"
        audio_path = os.path.join('static', audio_filename)

        try:
            tts = gTTS(text=translation, lang='en')  # Replace 'en' with target_lang if supported
            tts.save(audio_path)
        except Exception as tts_err:
            print("Text-to-speech error:", tts_err)
            audio_filename = None

        # Save to user's translation history
        username = session['username']
        users = load_users()

        translation_entry = {
            'date': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source_lang': source_lang,
            'target_lang': target_lang,
            'original_text': word,
            'translated_text': translation
        }

        users[username]['translation_history'].append(translation_entry)
        save_users(users)

        # Render result page
        return render_template('index.html',
                               username=username,
                               source_lang=source_lang,
                               target_lang=target_lang,
                               original_text=word,
                               translated_text=translation,
                               audio_file=audio_filename)

    except Exception as e:
        print(f"Error during translation: {e}")
        flash(f'Translation error: {str(e)}')
        return redirect(url_for('index'))


@app.route('/profile')
@login_required
def profile():
    username = session['username']
    users = load_users()
    user_data = users[username]
    
    gift_card = None
    if user_data['points'] >= 1000 and not user_data.get('gift_card'):
        # Load available gift cards
        try:
            with open('giftcards.json', 'r') as f:
                cards_data = json.load(f)
            
            for card in cards_data['cards']:
                if not card['used']:
                    gift_card = card['code']
                    card['used'] = True
                    users[username]['gift_card'] = gift_card
                    break
            
            # Save updated cards
            with open('giftcards.json', 'w') as f:
                json.dump(cards_data, f, indent=4)

            save_users(users)
        except Exception as e:
            print("Error loading gift cards:", e)

    # If user already got one before
    gift_card = user_data.get('gift_card', gift_card)

    return render_template('profile.html', 
                          username=username,
                          email=user_data['email'],
                          points=user_data['points'],
                          last_claim_date=user_data['last_claim_date'],
                          translation_history=user_data['translation_history'],
                          gift_card=gift_card)


if __name__ == '__main__':
    app.run(debug=True)
