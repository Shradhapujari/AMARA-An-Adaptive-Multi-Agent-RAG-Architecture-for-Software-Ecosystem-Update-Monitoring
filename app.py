from flask import Flask, send_file, jsonify, request
from flask_swagger_ui import get_swaggerui_blueprint
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ============================================
# SWAGGER UI CONFIGURATION
# ============================================

SWAGGER_URL = '/api/docs'
API_URL = '/api/swagger.yaml'

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "IoT Light Sensor API",
        'defaultModelsExpandDepth': -1,
        'defaultModelExpandDepth': 3,
        'displayRequestDuration': True,
        'docExpansion': 'list',
        'filter': True,
        'showExtensions': True,
        'showCommonExtensions': True
    }
)

app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

@app.route('/api/swagger.yaml')
def swagger_spec():
    """Serve the Swagger specification YAML file"""
    return send_file('swagger/swagger.yaml', mimetype='text/yaml')

# ============================================
# HOME & INFO ROUTES
# ============================================

@app.route('/')
def home():
    """Home page with links to documentation"""
    return '''
    <html>
    <head>
        <title>IoT Light Sensor API</title>
        <style>
            body { font-family: Arial; padding: 40px; max-width: 800px; margin: 0 auto; background: #f5f5f5; }
            .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #2c3e50; }
            .endpoint { background: #ecf0f1; padding: 10px; margin: 5px 0; border-radius: 5px; }
            .method { font-weight: bold; color: #27ae60; }
            a { color: #3498db; text-decoration: none; }
            a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🌟 IoT Light Sensor API</h1>
            <p>Welcome! The API is running successfully.</p>
            
            <h2>📚 Quick Links:</h2>
            <ul>
                <li><a href="/api/docs"><strong>Swagger UI Documentation</strong></a></li>
                <li><a href="/health">Health Check</a></li>
                <li><a href="/api/stats">System Statistics</a></li>
            </ul>
            
            <h2>📊 Available Endpoints (12 total):</h2>
            
            <h3>Health & Stats (2):</h3>
            <div class="endpoint"><span class="method">GET</span> /health</div>
            <div class="endpoint"><span class="method">GET</span> /api/stats</div>
            
            <h3>Sensor Data (2):</h3>
            <div class="endpoint"><span class="method">POST</span> /api/sensor/data</div>
            <div class="endpoint"><span class="method">GET</span> /api/readings</div>
            
            <h3>Usage Statistics (3):</h3>
            <div class="endpoint"><span class="method">POST</span> /api/usage/save</div>
            <div class="endpoint"><span class="method">GET</span> /api/usage/{date}</div>
            <div class="endpoint"><span class="method">GET</span> /api/usage/statistics</div>
            
            <h3>Room Management (3):</h3>
            <div class="endpoint"><span class="method">POST</span> /api/room/{room}/save</div>
            <div class="endpoint"><span class="method">GET</span> /api/room/{room}/{date}</div>
            <div class="endpoint"><span class="method">GET</span> /api/rooms/all/{date}</div>
            
            <h3>User Management (2):</h3>
            <div class="endpoint"><span class="method">POST</span> /api/user/register</div>
            <div class="endpoint"><span class="method">POST</span> /api/user/login</div>
        </div>
    </body>
    </html>
    '''

# ============================================
# ENDPOINT 1 & 2: HEALTH & STATS
# ============================================

@app.route('/health')
def health():
    """
    Endpoint 1: Health check - Lightweight check without database query
    Returns: Service status, name, timestamp, uptime
    """
    return jsonify({
        'status': 'healthy',
        'service': 'iot-light-sensor',
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'uptime': 86400
    })

@app.route('/api/stats')
def stats():
    """
    Endpoint 2: System statistics
    Returns: Total readings, active rooms, collections, last update
    """
    return jsonify({
        'totalReadings': 12458,
        'activeRooms': 6,
        'collections': ['room_living', 'room_bedroom', 'room_kitchen', 'room_bathroom', 'room_office', 'room_garage', 'daily_usage', 'users'],
        'lastUpdate': datetime.utcnow().isoformat() + 'Z'
    })

# ============================================
# ENDPOINT 3 & 4: SENSOR DATA
# ============================================

@app.route('/api/sensor/data', methods=['POST'])
def submit_sensor_data():
    """
    Endpoint 3: Submit sensor data from ESP32
    Accepts: room_id, light_state, lux, timestamp, battery_pct, power_mw, motion
    Returns: Success status with generated ID
    """
    data = request.get_json()
    
    # Validate required fields
    required = ['room_id', 'light_state', 'lux', 'timestamp']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400
    
    # Validate light_state
    if data['light_state'] not in ['ON', 'OFF']:
        return jsonify({'error': 'light_state must be ON or OFF'}), 400
    
    return jsonify({
        'status': 'success',
        'message': 'Sensor data recorded successfully',
        'id': '660c38fce3cba9423e4f8f23',
        'room': data.get('room_id'),
        'timestamp': data.get('timestamp'),
        'lux': data.get('lux')
    })

@app.route('/api/readings')
def get_readings():
    """
    Endpoint 4: Get latest readings with pagination
    Query params: limit (default 25), page (default 1), room (optional)
    Returns: Paginated sensor readings
    """
    limit = request.args.get('limit', 25, type=int)
    page = request.args.get('page', 1, type=int)
    room = request.args.get('room', None)
    
    # Mock data - in production this would query MongoDB
    readings = [
        {
            'id': '660c38fce3cba9423e4f8f23',
            'room_id': 'room-101',
            'room_name': 'living',
            'light_state': 'ON',
            'lux': 450.0,
            'timestamp': '2026-03-27T10:00:00Z',
            'battery_pct': 87,
            'power_mw': 2400,
            'motion': True
        },
        {
            'id': '660c38fce3cba9423e4f8f24',
            'room_id': 'room-102',
            'room_name': 'bedroom',
            'light_state': 'OFF',
            'lux': 12.0,
            'timestamp': '2026-03-27T10:01:00Z',
            'battery_pct': 92,
            'power_mw': 0,
            'motion': False
        },
        {
            'id': '660c38fce3cba9423e4f8f25',
            'room_id': 'room-103',
            'room_name': 'kitchen',
            'light_state': 'ON',
            'lux': 520.0,
            'timestamp': '2026-03-27T10:02:00Z',
            'battery_pct': 78,
            'power_mw': 2600,
            'motion': True
        }
    ]
    
    # Filter by room if specified
    if room:
        readings = [r for r in readings if r['room_name'] == room]
    
    return jsonify({
        'page': page,
        'limit': limit,
        'total': len(readings),
        'data': readings[:limit]
    })

# ============================================
# ENDPOINT 5, 6, 7: USAGE STATISTICS
# ============================================

@app.route('/api/usage/save', methods=['POST'])
def save_usage():
    """
    Endpoint 5: Save daily usage data
    Accepts: date, onSeconds, offSeconds (optional)
    Returns: Success status
    """
    data = request.get_json()
    
    if 'date' not in data or 'onSeconds' not in data:
        return jsonify({'error': 'Missing required fields: date and onSeconds'}), 400
    
    return jsonify({
        'status': 'success',
        'message': 'Usage data saved successfully',
        'date': data['date'],
        'onSeconds': data['onSeconds'],
        'offSeconds': data.get('offSeconds', 86400 - data['onSeconds'])
    })

@app.route('/api/usage/<date>')
def get_usage(date):
    """
    Endpoint 6: Get usage data for specific date
    Path param: date (YYYY-MM-DD)
    Returns: Usage data with on/off seconds and percentage
    """
    return jsonify({
        'date': date,
        'onSeconds': 28800,
        'offSeconds': 57600,
        'percentageOn': 33.33,
        'hoursOn': 8.0,
        'hoursOff': 16.0,
        'updatedAt': datetime.utcnow().isoformat() + 'Z'
    })

@app.route('/api/usage/statistics')
def get_usage_statistics():
    """
    Endpoint 7: Get weekly or monthly statistics
    Query params: period (weekly/monthly), startDate, endDate (optional)
    Returns: Aggregated usage statistics
    """
    period = request.args.get('period', 'weekly')
    start_date = request.args.get('startDate', '2026-03-20')
    end_date = request.args.get('endDate', '2026-03-27')
    
    return jsonify({
        'period': period,
        'startDate': start_date,
        'endDate': end_date,
        'totalOnSeconds': 201600,
        'totalOffSeconds': 403200,
        'avgOnSecondsPerDay': 28800,
        'avgHoursPerDay': 8.0,
        'peakDay': '2026-03-25',
        'peakOnSeconds': 43200,
        'lowestDay': '2026-03-21',
        'lowestOnSeconds': 14400
    })

# ============================================
# ENDPOINT 8, 9, 10: ROOM MANAGEMENT
# ============================================

@app.route('/api/room/<room>/save', methods=['POST'])
def save_room_usage(room):
    """
    Endpoint 8: Save room-specific usage data
    Path param: room (living, bedroom, kitchen, bathroom, office, garage)
    Accepts: date, onSeconds, avgLux (optional)
    Returns: Success status with room and date
    """
    valid_rooms = ['living', 'bedroom', 'kitchen', 'bathroom', 'office', 'garage']
    if room not in valid_rooms:
        return jsonify({
            'error': f'Invalid room. Valid rooms: {", ".join(valid_rooms)}'
        }), 400
    
    data = request.get_json()
    
    if 'date' not in data or 'onSeconds' not in data:
        return jsonify({'error': 'Missing required fields: date and onSeconds'}), 400
    
    return jsonify({
        'status': 'success',
        'message': f'Room usage data saved for {room}',
        'room': room,
        'date': data['date'],
        'onSeconds': data['onSeconds'],
        'avgLux': data.get('avgLux', 0)
    })

@app.route('/api/room/<room>/<date>')
def get_room_usage(room, date):
    """
    Endpoint 9: Get room usage for specific date
    Path params: room, date (YYYY-MM-DD)
    Returns: Room-specific usage data
    """
    valid_rooms = ['living', 'bedroom', 'kitchen', 'bathroom', 'office', 'garage']
    if room not in valid_rooms:
        return jsonify({
            'error': f'Invalid room. Valid rooms: {", ".join(valid_rooms)}'
        }), 400
    
    return jsonify({
        'room': room,
        'date': date,
        'onSeconds': 14400,
        'offSeconds': 72000,
        'avgLux': 450.0,
        'hoursOn': 4.0,
        'percentageOn': 16.67,
        'updatedAt': datetime.utcnow().isoformat() + 'Z'
    })

@app.route('/api/rooms/all/<date>')
def get_all_rooms(date):
    """
    Endpoint 10: Get all rooms data for specific date
    Path param: date (YYYY-MM-DD)
    Returns: Usage data for all 6 rooms
    """
    rooms = ['living', 'bedroom', 'kitchen', 'bathroom', 'office', 'garage']
    room_data = []
    
    for idx, room in enumerate(rooms):
        room_data.append({
            'room': room,
            'onSeconds': 14400 + (idx * 1800),
            'avgLux': 450.0 - (idx * 50),
            'hoursOn': round((14400 + (idx * 1800)) / 3600, 2),
            'percentageOn': round(((14400 + (idx * 1800)) / 86400) * 100, 2)
        })
    
    return jsonify({
        'date': date,
        'totalRooms': len(rooms),
        'rooms': room_data,
        'totalOnSeconds': sum(r['onSeconds'] for r in room_data),
        'avgLuxAllRooms': sum(r['avgLux'] for r in room_data) / len(room_data)
    })

# ============================================
# ENDPOINT 11 & 12: USER MANAGEMENT
# ============================================

@app.route('/api/user/register', methods=['POST'])
def register_user():
    """
    Endpoint 11: Register new user
    Accepts: email, password, name (optional)
    Returns: Success status with user ID
    """
    data = request.get_json()
    
    if 'email' not in data or 'password' not in data:
        return jsonify({'error': 'Email and password are required'}), 400
    
    # Validate email format (basic)
    if '@' not in data['email']:
        return jsonify({'error': 'Invalid email format'}), 400
    
    # Validate password length
    if len(data['password']) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
    
    return jsonify({
        'status': 'success',
        'message': 'User registered successfully',
        'userId': '660c38fce3cba9423e4f8f23',
        'email': data['email'],
        'name': data.get('name', 'Unknown'),
        'createdAt': datetime.utcnow().isoformat() + 'Z'
    })

@app.route('/api/user/login', methods=['POST'])
def login_user():
    """
    Endpoint 12: User login
    Accepts: email, password
    Returns: Success status with JWT token
    """
    data = request.get_json()
    
    if 'email' not in data or 'password' not in data:
        return jsonify({'error': 'Email and password are required'}), 400
    
    # In production, this would verify against database
    # For now, return success for any valid format
    
    return jsonify({
        'status': 'success',
        'message': 'Login successful',
        'userId': '660c38fce3cba9423e4f8f23',
        'email': data['email'],
        'token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2NjBjMzhmY2UzY2JhOTQyM2U0ZjhmMjMiLCJlbWFpbCI6InVzZXJAZXhhbXBsZS5jb20iLCJpYXQiOjE3MTE1MzM2ODh9.XYZ123',
        'expiresIn': 3600,
        'loginAt': datetime.utcnow().isoformat() + 'Z'
    })

# ============================================
# ERROR HANDLERS
# ============================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'error': 'Endpoint not found',
        'message': 'The requested URL was not found on the server',
        'status': 404
    }), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({
        'error': 'Internal server error',
        'message': 'An unexpected error occurred',
        'status': 500
    }), 500

# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    print('\n' + '='*70)
    print('🚀 IoT Light Sensor API Server Starting...')
    print('='*70)
    print('\n📚 Swagger UI:  http://localhost:5002/api/docs')
    print('🏠 Home Page:   http://localhost:5002')
    print('💚 Health:      http://localhost:5002/health')
    print('📊 Stats:       http://localhost:5002/api/stats')
    print('\n🎯 Total Endpoints: 12')
    print('   - Health & Stats: 2')
    print('   - Sensor Data: 2')
    print('   - Usage Statistics: 3')
    print('   - Room Management: 3')
    print('   - User Management: 2')
    print('\n' + '='*70 + '\n')
    
    app.run(debug=True, host='0.0.0.0', port=5002)
