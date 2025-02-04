import json
import teslapy
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """
        Handle CORS preflight requests if needed.
        """
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        """
        Handle POST requests for Tesla login and battery retrieval.
        Body JSON should look like:
        {
          "email": "...",
          "password": "...",
          "mfa_code": "..." (if needed)
        }
        """
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        try:
            data = json.loads(body)
        except:
            self._send_response(400, {"error": "Invalid JSON body"})
            return

        email = data.get('email')
        password = data.get('password')
        mfa_code = data.get('mfa_code')  # might be None if not provided

        if not email or not password:
            self._send_response(400, {"error": "Missing email or password"})
            return

        # Initialize Tesla session without pre-stored token
        # The 'verify=True' param is default, but you can set to False to skip SSL checks (not recommended).
        with teslapy.Tesla(email=email, password=password) as tesla:
            # If user provided MFA code, inject it into the MFA callback
            # Teslapy does this by prompting, but we can override:
            def mfa_callback(_):
                # This function is called if Tesla indicates MFA is required
                return mfa_code or ""

            try:
                # Attempt to fetch an OAuth token
                # This might raise an exception if credentials or MFA are invalid
                tesla.fetch_token(token_refresh_callable=mfa_callback)
            except Exception as e:
                self._send_response(401, {"error": f"Authentication failed: {str(e)}"})
                return

            # If we get here, we have a valid token. Now fetch vehicles:
            vehicles = tesla.vehicle_list()
            if not vehicles:
                self._send_response(404, {"error": "No Tesla vehicles found."})
                return

            # Just take the first vehicle for demo
            vehicle = vehicles[0]

            # Wake up the vehicle (optional, might take a few seconds)
            vehicle.sync_wake_up()

            # Retrieve vehicle data
            vehicle_data = vehicle.get_vehicle_data()
            charge_state = vehicle_data.get('charge_state', {})
            battery_level = charge_state.get('battery_level')

            if battery_level is None:
                self._send_response(500, {"error": "Could not retrieve battery level."})
                return

            # Success! Return battery level.
            response_data = {
                "battery_level": battery_level,
                "vehicle_name": vehicle_data.get('display_name', 'Unknown Tesla')
            }
            self._send_response(200, response_data)

    def _send_response(self, status_code, payload):
        """
        Helper method to send JSON response
        """
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")  # For CORS
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode('utf-8'))
