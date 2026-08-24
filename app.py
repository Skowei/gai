from flask import Flask, request, jsonify
import os
import requests
import time

app = Flask(__name__)

# Czytanie zmiennych środowiskowych ustawionych w docker-compose.yml
API_URL = os.environ.get('API_URL', 'http://localhost:8420')
API_KEY = os.environ.get('API_KEY', 'test-team')
API_ENDPOINT = '/v2/conversation/add'

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        query = data.get('query', '')
        
        # Generate a session ID if not provided (or use UUID)
        session_id = data.get('session_id') or f"sess-{int(time.time() * 1000)}"
        
        # Parse user/assistant roles from the query
        # If query contains "User:" prefix, treat as user message
        # Otherwise, if contains "Assistant:", treat as assistant message
        messages = []
        
        if query.strip().startswith('User:'):
            # Single user message
            role = 'user'
        elif query.strip().startswith('Assistant:') or query.strip() == '/clear':
            # Assistant message or clear command
            role = 'assistant'
        else:
            # Default to user for single-turn queries
            role = 'user'
        
        messages.append({
            'role': role,
            'content': query.strip()
        })
        
        response = requests.post(
            f'{API_URL}{API_ENDPOINT}',
            json={
                'team_id': data.get('team_id', os.environ.get('DEFAULT_ISOLATION_ID', 'DEFAULT_ISOLATION_ID')),
                'agent_id': data.get('agent_id', os.environ.get('AGENT_ID', 'default')),
                'user_id': data.get('user_id', os.environ.get('USER_ID', 'default')),
                'session_id': session_id,
                'messages': messages
            },
            headers={
                'Authorization': 'Bearer local',
                'x-tdai-service-id': API_KEY,
                'Content-Type': 'application/json'
            },
            timeout=15
        )
        result = response.json()
        
        if result.get('code') == 0:
            items = result.get('data', {}).get('items', [])
            return jsonify({
                'success': True,
                'response': '\n\n'.join(i.get('content') or i.get('message') for i in items)
            })
        else:
            return jsonify({
                'success': True,
                'response': result.get('message', result.get('text', str(result)))
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)