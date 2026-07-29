"""Anti-detection: browser fingerprint simulation, request jitter, headers."""

import random
import asyncio
from dataclasses import dataclass

@dataclass
class BrowserProfile:
    ua: str
    ch_ua: str
    platform: str
    accept_language: str
    
    def get_headers(self, req_type="navigate") -> dict:
        headers = {
            "Accept-Language": self.accept_language,
            "User-Agent": self.ua,
        }
        
        if self.ch_ua:
            headers["Sec-CH-UA"] = self.ch_ua
            headers["Sec-CH-UA-Mobile"] = "?0"
            headers["Sec-CH-UA-Platform"] = f'"{self.platform}"'
            
        if req_type == "navigate":
            headers.update({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1"
            })
        elif req_type == "api":
            headers.update({
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "X-Requested-With": "XMLHttpRequest"
            })
        return headers

PROFILES = [
    # Chrome Windows
    BrowserProfile("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"', "Windows", "en-US,en;q=0.9"),
    BrowserProfile("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36", '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"', "Windows", "en-US,en;q=0.9,en-GB;q=0.8"),
    BrowserProfile("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36", '"Google Chrome";v="123", "Chromium";v="123", "Not:A-Brand";v="8"', "Windows", "en-US,en;q=0.8"),
    # Chrome macOS
    BrowserProfile("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36", '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"', "macOS", "en-US,en;q=0.9"),
    BrowserProfile("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36", '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"', "macOS", "en-US,en;q=0.9"),
    # Edge Windows
    BrowserProfile("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0", '"Chromium";v="124", "Microsoft Edge";v="124", "Not-A.Brand";v="99"', "Windows", "en-US,en;q=0.9"),
    BrowserProfile("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0", '"Microsoft Edge";v="125", "Chromium";v="125", "Not.A/Brand";v="24"', "Windows", "en-US,en;q=0.9"),
    # Firefox
    BrowserProfile("Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0", "", "Windows", "en-US,en;q=0.5"),
    BrowserProfile("Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0", "", "macOS", "en-US,en;q=0.5"),
    # Safari
    BrowserProfile("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15", "", "macOS", "en-US,en;q=0.9"),
]

for v in [120, 121, 122, 126, 127]:
    PROFILES.append(BrowserProfile(f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36", f'"Chromium";v="{v}", "Google Chrome";v="{v}", "Not-A.Brand";v="99"', "Windows", "en-US,en;q=0.9"))
    PROFILES.append(BrowserProfile(f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36", f'"Chromium";v="{v}", "Google Chrome";v="{v}", "Not-A.Brand";v="99"', "macOS", "en-US,en;q=0.9"))
    PROFILES.append(BrowserProfile(f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{v}.0.0.0 Safari/537.36 Edg/{v}.0.0.0", f'"Chromium";v="{v}", "Microsoft Edge";v="{v}", "Not-A.Brand";v="99"', "Windows", "en-US,en;q=0.9"))

def random_profile() -> BrowserProfile:
    return random.choice(PROFILES)

def random_user_agent() -> str:
    return random_profile().ua

def browser_headers(ua: str = None) -> dict:
    prof = random_profile()
    if ua: prof.ua = ua
    return prof.get_headers("navigate")

def api_headers(ua: str = None) -> dict:
    prof = random_profile()
    if ua: prof.ua = ua
    return prof.get_headers("api")

async def jitter(min_ms: int = 100, max_ms: int = 500):
    delay = random.uniform(min_ms / 1000, max_ms / 1000)
    await asyncio.sleep(delay)

async def step_jitter():
    await jitter(800, 2500)

def random_address() -> dict:
    first_names = ["James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda", "David", "Susan", "William", "Jessica", "Richard", "Sarah", "Joseph", "Karen", "Thomas", "Nancy", "Charles", "Lisa", "Christopher", "Betty", "Daniel", "Margaret", "Matthew", "Sandra", "Anthony", "Ashley", "Mark", "Kimberly", "Donald", "Emily", "Steven", "Donna", "Paul", "Michelle", "Andrew", "Dorothy", "Joshua", "Carol", "Kenneth", "Amanda", "Kevin", "Melissa", "Brian", "Deborah", "George", "Stephanie", "Edward", "Rebecca"]
    last_names = ["Smith", "Jones", "Taylor", "Brown", "Williams", "Wilson", "Johnson", "Davies", "Miller", "Davis", "Garcia", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Perez", "Thomas", "Moore", "Jackson", "Martin", "Lee", "White", "Thompson", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell", "Carter", "Roberts"]
    streets = ["Maple St", "Oak Ave", "Washington Blvd", "Lakeview Dr", "Park Way", "Broadway", "Elm St", "Pine Ave", "Main St", "Cedar Ln", "Highland Ave", "Sunset Blvd", "Ridge Rd", "Meadow Ln", "Willow Dr", "Cherry St", "River Rd", "North St", "South St", "West St", "East St", "Victoria St", "King St", "Queen St", "Church St", "Spring St", "Broad St", "Front St", "Center St", "Chestnut St", "Walnut St", "Locust St", "Spruce St", "Sycamore Ln", "Forest Ave"]
    
    locations = [
        ("New York", "NY", "10001", "212"),
        ("Los Angeles", "CA", "90001", "213"),
        ("Chicago", "IL", "60601", "312"),
        ("Houston", "TX", "77001", "713"),
        ("Phoenix", "AZ", "85001", "602"),
        ("Philadelphia", "PA", "19101", "215"),
        ("San Antonio", "TX", "78201", "210"),
        ("San Diego", "CA", "92101", "619"),
        ("Dallas", "TX", "75201", "214"),
        ("San Jose", "CA", "95101", "408"),
        ("Austin", "TX", "73301", "512"),
        ("Jacksonville", "FL", "32099", "904"),
        ("Fort Worth", "TX", "76101", "817"),
        ("Columbus", "OH", "43201", "614"),
        ("San Francisco", "CA", "94101", "415"),
        ("Charlotte", "NC", "28201", "704"),
        ("Indianapolis", "IN", "46201", "317"),
        ("Seattle", "WA", "98101", "206"),
        ("Denver", "CO", "80201", "303"),
        ("Washington", "DC", "20001", "202"),
        ("Boston", "MA", "02101", "617"),
        ("El Paso", "TX", "79901", "915"),
        ("Nashville", "TN", "37201", "615"),
        ("Detroit", "MI", "48201", "313"),
        ("Oklahoma City", "OK", "73101", "405"),
        ("Portland", "OR", "97201", "503"),
        ("Las Vegas", "NV", "89101", "702"),
        ("Memphis", "TN", "38101", "901"),
        ("Louisville", "KY", "40201", "502"),
        ("Baltimore", "MD", "21201", "410"),
    ]
    
    city, state, zip_code, area_code = random.choice(locations)
    
    return {
        "firstName": random.choice(first_names),
        "lastName": random.choice(last_names),
        "address1": f"{random.randint(100, 9999)} {random.choice(streets)}",
        "city": city,
        "zoneCode": state,
        "countryCode": "US",
        "postalCode": zip_code,
        "phone": f"{area_code}{random.randint(2000000, 9999999)}"
    }

def random_email(first_name: str, last_name: str) -> str:
    domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com", "aol.com", "protonmail.com", "mail.com", "me.com", "mac.com"]
    formats = [
        f"{first_name.lower()}{last_name.lower()}",
        f"{first_name.lower()}.{last_name.lower()}",
        f"{first_name.lower()[0]}{last_name.lower()}",
        f"{first_name.lower()}{random.randint(10, 9999)}"
    ]
    return f"{random.choice(formats)}@{random.choice(domains)}"