import time
import database
from datetime import datetime

class RateLimiter:
    def __init__(self, tpm_limit=40, ban_limit=3600, ban_duration=3600):
        self.tpm_limit = tpm_limit  # Requests per minute
        self.ban_limit = ban_limit  # Requests per hour for permanent ban
        self.ban_duration = ban_duration # Ban duration in seconds (1 hour)

        self.ip_requests_minute = {}  # {ip: [(timestamp, count)]}
        self.ip_requests_hour = {}    # {ip: [(timestamp, count)]}
        
        # Explicitly initialize as a dictionary to help the linter
        self.banned_ips = {} 
        self.banned_ips.update(database.get_all_banned_ips())

    def _clean_old_requests(self, ip, request_dict, time_window):
        current_time = time.time()
        # Remove requests older than time_window
        request_dict[ip] = [(t, c) for t, c in request_dict.get(ip, []) if current_time - t < time_window]

    def check_rate_limit(self, ip):
        current_time = time.time()

        # Check if IP is permanently banned
        if ip in self.banned_ips:
            return False

        # Clean old requests for minute and hour windows
        self._clean_old_requests(ip, self.ip_requests_minute, 60)
        self._clean_old_requests(ip, self.ip_requests_hour, 3600)

        # Update request count for the current minute
        self.ip_requests_minute.setdefault(ip, []).append((current_time, 1))
        current_minute_requests = sum(count for _, count in self.ip_requests_minute[ip])

        # Update request count for the current hour
        self.ip_requests_hour.setdefault(ip, []).append((current_time, 1))
        current_hour_requests = sum(count for _, count in self.ip_requests_hour[ip])

        # Check for permanent ban
        if current_hour_requests > self.ban_limit:
            self.banned_ips[ip] = datetime.now() # Assign to dict
            database.add_banned_ip(ip)  # Persist the ban to the database
            return False

        # Check TPM limit
        if current_minute_requests > self.tpm_limit:
            return False

        return True

rate_limiter = RateLimiter()

if __name__ == "__main__":
    # Example Usage
    # Initialize the database for the test
    database.initialize_database()
    
    rl = RateLimiter()
    test_ip = "192.168.1.1"
    banned_ip = "192.168.1.2"

    # Clean up any previous bans for this test IP
    database.remove_banned_ip(test_ip)
    database.remove_banned_ip(banned_ip)
    
    # Re-initialize the rate limiter to clear the in-memory ban list for the test
    rl = RateLimiter()

    print(f"Testing IP: {test_ip}")
    for i in range(50):
        allowed = rl.check_rate_limit(test_ip)
        if i == 39:
            print(f"Request {i+1}: Allowed? {allowed} (Should be True)")
        elif i == 40:
            print(f"Request {i+1}: Allowed? {allowed} (Should be False - TPM limit)")
        if i % 10 == 0 and i > 0:
            time.sleep(0.1)

    print("\nSimulating 3600 requests in an hour for banned IP...")
    for i in range(3601):
        allowed = rl.check_rate_limit(banned_ip)
        if i == 3599:
            print(f"Banned IP Request {i+1}: Allowed? {allowed} (Should be True)")
        elif i == 3600:
            print(f"Banned IP Request {i+1}: Allowed? {allowed} (Should be False - Ban limit)")
        if i % 500 == 0:
            time.sleep(0.01)

    print(f"\nIs {banned_ip} banned in current instance? {banned_ip in rl.banned_ips}")

    # Test banned IP again
    print(f"Testing banned IP {banned_ip} after ban:")
    allowed = rl.check_rate_limit(banned_ip)
    print(f"Banned IP Request: Allowed? {allowed} (Should be False)")

    # Verify persistence by creating a new RateLimiter instance
    print("\nVerifying persistence with a new RateLimiter instance...")
    new_rl = RateLimiter()
    print(f"Is {banned_ip} banned in new instance? {banned_ip in new_rl.banned_ips}")
    allowed_new = new_rl.check_rate_limit(banned_ip)
    print(f"New instance check for banned IP: Allowed? {allowed_new} (Should be False)")