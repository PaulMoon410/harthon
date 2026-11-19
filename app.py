from functools import wraps
import atexit
import hmac
import os

from flask import Flask, jsonify, redirect, render_template, render_template_string, request, url_for

from python_sessions import SessionManager

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 65536
sessions = SessionManager()
atexit.register(sessions.close_all)


def require_api_key(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        key = os.environ.get('PYTHON_API_KEY', '')
        if len(key) < 32 or not key.isascii():
            return jsonify({'error': 'PYTHON_API_KEY must be configured with at least 32 ASCII characters'}), 503
        auth = request.headers.get('Authorization', '')
        if not hmac.compare_digest(auth.encode('utf-8'), ('Bearer ' + key).encode('utf-8')):
            return jsonify({'error': 'Unauthorized'}), 401
        return function(*args, **kwargs)
    return wrapped


@app.after_request
def prevent_caching(response):
    response.headers['Cache-Control'] = 'no-store'
    return response

# Health check endpoint
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'message': 'Python app running on Render'})

# Home endpoint
@app.route('/')
def home():
    return redirect(url_for('console'))

# Status endpoint
@app.route('/api/status')
def status():
    return jsonify({
        'app': 'python-render-app',
        'version': '1.0.0',
        'environment': os.environ.get('ENVIRONMENT', 'production'),
        'timestamp': os.getenv('TIMESTAMP', '')
    })

# Simple dashboard with terminal-like display
@app.route('/dashboard')
def dashboard():
    # Inline simple HTML with JavaScript that polls /api/status every 2s
    html = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Harold's Live Dashboard</title>
        <style>
            body {font-family: monospace; background: #111; color: #0f0; padding: 20px;}
            #log {background: #222; padding: 10px; border-radius: 4px; height: 80vh; overflow-y: auto;}
            #link {margin-top: 10px;}
        </style>
    </head>
    <body>
        <h1>Harold's Live Dashboard</h1>
        <div id="log"></div>
        <div id="link"><a href="/console" style="color:#0ff;">Python Console</a></div>
        <script>
            const logDiv = document.getElementById('log');
            function fetchStatus() {
                fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    const entry = document.createElement('div');
                    entry.textContent = new Date().toLocaleTimeString() + ' - ' + JSON.stringify(data);
                    logDiv.prepend(entry);
                    if (logDiv.childElementCount > 50) logDiv.removeChild(logDiv.lastChild);
                })
                .catch(err => console.error(err));
            }
            fetchStatus();
            setInterval(fetchStatus, 2000);
        </script>
    </body>
    </html>
    '''
    return render_template_string(html)


@app.get('/console')
def console():
    return render_template('console.html')


@app.post('/api/sessions')
@require_api_key
def create_session():
    session_id = sessions.create()
    if session_id is None:
        return jsonify({'error': 'Session limit reached'}), 503
    return jsonify({'session_id': session_id}), 201


@app.post('/api/sessions/<session_id>/execute')
@require_api_key
def execute(session_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get('code'), str) or not data['code'].strip():
        return jsonify({'error': 'Provide a non-empty code string in a JSON object'}), 400
    result, error = sessions.execute(session_id, data['code'])
    if error:
        messages = {
            'not_found': ('Session not found', 404),
            'busy': ('Session is already running a command', 409),
            'timeout': ('Execution timed out; session was closed', 504),
            'terminated': ('Python process terminated; session was closed', 502),
        }
        message, status_code = messages[error]
        return jsonify({'error': message}), status_code
    return jsonify(result)


@app.delete('/api/sessions/<session_id>')
@require_api_key
def delete_session(session_id):
    error = sessions.delete(session_id)
    if error == 'not_found':
        return jsonify({'error': 'Session not found'}), 404
    if error == 'busy':
        return jsonify({'error': 'Session is already running a command'}), 409
    return '', 204


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
