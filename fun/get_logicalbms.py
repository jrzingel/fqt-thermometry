# Spoof a browser connection to Logical BMS to get interesting building status information

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://logicalbms.unsw.edu.au"
USERNAME = "guest"
PASSWORD = "guest"

session = requests.Session()
session.verify = False  # if server uses self-signed SSL certs


# First get the login page
LOGIN_URL = f"{BASE_URL}/?language=en"

r = session.get(LOGIN_URL)
r.raise_for_status()

soup = BeautifulSoup(r.content, "html.parser")

# Get the session tokens
tokens = {}
for name in ["login-auth-tok", "login-tracker"]:
    el = soup.find("input", {"name": name})
    if el.has_attr("value"):
        tokens[name] = el["value"]
    else:
        print(f"Missing token: {name}")
        tokens[name] = ""
print(tokens)


# Perform the login request
form = {
    "touchscr": "false",
    "name": USERNAME,
    "login-auth-tok": tokens["login-auth-tok"],
    "login-tracker": tokens["login-tracker"],
    "pass": PASSWORD
}

# Post the request
r = session.post(LOGIN_URL, data=form, allow_redirects=False)
r.raise_for_status()

print(r.status_code)


# login_url = f"{BASE_URL}/servlet/LoginServlet"  # adjust based on DevTools
#
# r = session.post(login_url, data=payload)
#
# payload = {
#     "username": USERNAME,
#     "password": PASSWORD
#     # If the login form has hidden fields (CSRF, etc.), include them here
# }
#
# r.raise_for_status()

# After login, WebCTRL often redirects to /servlet/Workbench or similar
# WBS id appears in URLs like ?wbs=-1461233334
# Grab one msgservlet/servertest request to extract WBS


