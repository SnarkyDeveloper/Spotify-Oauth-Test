#########################   IMPORTS & INIT    #####################################
import httpx
import os
import secrets
import string
import flask
import base64
from flask import Flask, redirect, request
from urllib.parse import quote_plus
from dotenv import load_dotenv, set_key
import json
from datetime import datetime, timedelta
dotenv_path = '.env'
load_dotenv(dotenv_path)

app = Flask(__name__)
requests = httpx.Client()

#########################   AUTH VARIABLES    #####################################
def generaterandomstring(length):
    characters = string.ascii_letters + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
scope = "user-library-read, app-remote-control, user-modify-playback-state, user-read-playback-state, user-top-read, playlist-read-private"

if os.getenv('AUTH_CODE') == None:
    code = None
else:
    code = os.getenv('AUTH_CODE')

#########################   LOGIN    #####################################
@app.route('/login')
def login():
    state = generaterandomstring(16)
    return redirect(f'https://accounts.spotify.com/authorize?response_type=code&client_id={quote_plus(CLIENT_ID)}&redirect_uri={quote_plus(REDIRECT_URI)}&scope={quote_plus(scope)}&state={quote_plus(state)}')

#########################   CALLBACK & MAIN AUTH   #####################################
@app.route('/code')
def getcode():
    code = request.args.get('code')
    if code == None:
        return redirect('http://localhost:5500/login')
    
    return flask.redirect(f'http://localhost:5500/callback?code={code}')

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        load_dotenv()
        code = os.getenv('AUTH_CODE')
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    headers = {
        "content-type": "application/x-www-form-urlencoded", 
        "Authorization": f"Basic {base64.b64encode(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode()).decode()}"
    }
    
    spotify = requests.post("https://accounts.spotify.com/api/token", data=data, headers=headers)
    auth_data = spotify.json()
    
    with open('.auth.json', 'w') as f:
        json.dump(auth_data, f, indent=2)
    
    return auth_data

######################### PRIMARY BACKEND FUNCTIONS #####################################
class AuthTokens:
    def __init__(self):
        try:
            with open('.auth.json', 'r') as f:
                self.auth = json.load(f)
                if 'timestamp' not in self.auth:
                    self.auth['timestamp'] = datetime.now().timestamp()
                    self.save_auth()
        except FileNotFoundError:
            self.auth = None
    
    def save_auth(self):
        with open('.auth.json', 'w') as f:
            json.dump(self.auth, f, indent=2)
    
    def get_access_token(self):
        return self.auth.get('access_token') if self.auth else None
        
    def get_refresh_token(self):
        env_token = os.getenv('REFRESH_TOKEN')
        auth_token = self.auth.get('refresh_token') if self.auth else None
        
        if auth_token and env_token != auth_token:
            set_key('.env', 'REFRESH_TOKEN', auth_token)            
            load_dotenv(dotenv_path)
            return auth_token
            
        return env_token or auth_token
        
    def get_token_type(self):
        return self.auth.get('token_type') if self.auth else None
        
    def get_expires_in(self):
        return self.auth.get('expires_in') if self.auth else None
        
    def is_token_valid(self):
        if not self.auth:
            return False
        
        created_at = datetime.fromtimestamp(self.auth.get('timestamp', 0))
        expires_in = timedelta(seconds=self.auth.get('expires_in', 0))
        is_valid = datetime.now() < (created_at + expires_in - timedelta(minutes=5))
        
        return is_valid

def refresh_token():
    auth = AuthTokens()
    
    if auth.is_token_valid():
        return "Token still valid!"
        
    headers = {
        "content-type": "application/x-www-form-urlencoded", 
        "Authorization": f"Basic {base64.b64encode(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode()).decode()}"
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": auth.get_refresh_token(),
    }
    spotify = requests.post("https://accounts.spotify.com/api/token", data=data, headers=headers)
    auth_data = spotify.json()
    
    auth_data['timestamp'] = datetime.now().timestamp()
    
    with open('.auth.json', 'w') as f:
        json.dump(auth_data, f, indent=2)
    return "Token refreshed!"

def ensure_valid_token():
    if not AuthTokens().is_token_valid():
        refresh_token()
        
class Action:
    def __init__(self, url, type="post"):
        self.url = url
        self.type = type
    link = "https://api.spotify.com/v1"
    
    def make_request(self, headers):
        request_methods = {
            "put": requests.put,
            "get": requests.get,
            "post": requests.post
        }
        method = request_methods.get(self.type, requests.post)
        return method(f'{self.link}{self.url}', headers=headers)
    
    def action(self):
        headers = {
            "Authorization": f"Bearer {AuthTokens().get_access_token()}"
        }
        self.a = self.make_request(headers)
            
        if self.a.status_code == 200:
            return True
        elif self.a.status_code == 401:
            refresh_token()
            headers["Authorization"] = f"Bearer {AuthTokens().get_access_token()}"
            self.a = self.make_request(headers)
            return self.a.status_code == 200
        return False

def returns(answer, url, type="post"):
    action_req = Action(url, type)
    if action_req.action() == True:
        return f'{answer}!'
    else:
        return f'Error: {action_req.a.status_code}'
#########################   DEBUG   #####################################
@app.route('/force-refresh')
def force_refresh():
    headers = {
        "content-type": "application/x-www-form-urlencoded", 
        "Authorization": f"Basic {base64.b64encode(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode()).decode()}"
    }
    data = {
        "grant_type": "refresh_token",
        "refresh_token": AuthTokens().get_refresh_token(),
    }
    spotify = requests.post("https://accounts.spotify.com/api/token", data=data, headers=headers)
    auth_data = spotify.json()
    print(spotify.text)
    auth_data['timestamp'] = datetime.now().timestamp()
    
    with open('.auth.json', 'w') as f:
        json.dump(auth_data, f, indent=2)
    return "Token refreshed!"

#########################   MAIN   #####################################
@app.route('/skip')

def skip():
    ensure_valid_token()
    return returns("Skipped", "/me/player/next")

@app.route('/previous')
@app.route('/prev') 
def previous():
    ensure_valid_token()
    return returns("Previous", "/me/player/previous")

@app.route('/pause')
def pause():
    ensure_valid_token()
    return returns("Paused", "/me/player/pause", "put")

@app.route('/resume')
def resume():
    ensure_valid_token()
    return returns("Resumed", "/me/player/play", "put")
@app.route('/current')
def current():
    ensure_valid_token()
    return returns("Current", "/me/player/currently-playing", "get")

@app.route('/seek/<min>/<sec>')
@app.route('/seek/<min>/')
def seek(min, sec=0):
    ensure_valid_token()
    min = int(min);sec = int(sec); position_ms = min * 60 * 1000 + sec * 1000
    return returns(f"Seeked to {min} min & {sec} sec", f"/me/player/seek?position_ms={position_ms}", "put")

@app.route('/search/<query>')
def search(query):
    ensure_valid_token()
    headers = {
        "Authorization": f"Bearer {AuthTokens().get_access_token()}"
    }
    search_response = requests.get(
        f"https://api.spotify.com/v1/search?q={quote_plus(query)}&type=track&limit=1", headers=headers)
    if search_response.status_code != 200:
        return "Error searching for track"
    tracks = search_response.json()['tracks']['items']
    if len(tracks) > 0:
        track_id = tracks[0]['id']
        queue_response = requests.post(
            f"https://api.spotify.com/v1/me/player/queue?uri=spotify:track:{track_id}", headers=headers)
        if queue_response.status_code != 200:
            return "Error adding track to queue"
            
        return f'Added "{tracks[0]["name"]}" to queue'
    else:
        return 'Song not found'
#########################   RUN PARAMS  #####################################
if __name__ == '__main__':
    app.run(debug=True, port=5500)

#########################   TODO   #####################################

# - [ TODO ] Add a function to get the current playing song ✅
# - [ TODO ] Add a function to pause the current playing song ✅
# - [ TODO ] Add a function to go to the previous song ✅
# - [ TODO ] Add a function to go to the next song ✅
# - [ TODO ] Add a function to get the current playing song's duration 
# - [ TODO ] Add a function to seek to a certain part of the song ✅
