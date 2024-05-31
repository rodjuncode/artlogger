import argparse
from re import template
import git
import os
import http.server
import socketserver
import shutil
import threading
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
import time
import base64
from jinja2 import Environment, FileSystemLoader, select_autoescape

# constants
PORT = 8000
HISTORY_FILE = "index"

# Create the parser
parser = argparse.ArgumentParser(description="Process a GitHub URL.")

# Add the arguments
parser.add_argument("URL", metavar="URL", type=str, help="The GitHub URL to process")
parser.add_argument(
    "--branch",
    metavar="branch",
    type=str,
    default="main",
    help="The branch to checkout",
)
parser.add_argument(
    "--wait",
    metavar="wait",
    type=int,
    default=5,
    help="The number of seconds to wait for the page to load",
)

# Parse the arguments
args = parser.parse_args()

# Store the absolute path of the parent directory
parent_dir = os.path.abspath(os.getcwd())

# Define the absolute paths of the 'repo' and 'log' directories
repo_dir = os.path.join(parent_dir, "repo")
log_dir = os.path.join(parent_dir, "log")
template_dir = os.path.join(parent_dir, "template")

# Remove the 'repo' and 'log' directories if they exist
for directory in [repo_dir, log_dir]:
    if os.path.exists(directory):
        shutil.rmtree(directory)

# Create the 'log' directory
os.makedirs(log_dir)

# Clone the repository
repo = git.Repo.clone_from(args.URL, repo_dir)

# Checkout the specified branch
repo.git.checkout(args.branch)

remote_url = next(iter(repo.remotes)).url.replace(".git", "")

# Check if the 'repo' directory exists before trying to change to it
if os.path.exists(repo_dir):
    os.chdir(repo_dir)

# Get all commits and filter out those with "#ignorelog" in the message
commits = [
    commit for commit in repo.iter_commits() if "#ignorelog" not in commit.message
]

print(f"Processed URL: {args.URL}")
print(f'Number of commits without "#ignorelog": {len(commits)}')

# Set up Selenium with a headless browser
webdriver_service = Service(ChromeDriverManager().install())
chrome_options = Options()
chrome_options.add_argument("--headless")
driver = webdriver.Chrome(service=webdriver_service, options=chrome_options)

# Define the starting port
Handler = http.server.SimpleHTTPRequestHandler

# Start the server before the loop
httpd = socketserver.TCPServer(("", PORT), Handler)
print(f"Serving at port {PORT}")
httpd_thread = threading.Thread(target=httpd.serve_forever)
httpd_thread.start()

# Set up the Jinja2 environment
env = Environment(
    loader=FileSystemLoader(template_dir), autoescape=select_autoescape(["html"])
)

# Get the main template
main_template = env.get_template("main_template.html")

# Create a list to store the commit data
commits_html = []

for commit in reversed(commits):

    print(f"Processing commit {commit.hexsha}...")

    # create the html data for the commit
    commit_html_data = {
        "hexsha": commit.hexsha,
        "message": commit.message,
        "author": commit.author,
        "committed_date": commit.committed_date,
        "url": f"{remote_url}/commit/{commit.hexsha}",
        "png_exists": False,
    }

    # Checkout the commit
    repo.git.checkout(commit)

    # Navigate to the page
    driver.get(f"http://localhost:{PORT}")

    # Wait for the page to load
    time.sleep(args.wait)

    # Check if there is a canvas element on the page
    canvas_elements = driver.find_elements(By.TAG_NAME, "canvas")
    if canvas_elements:
        # Get the canvas as a PNG
        canvas = canvas_elements[0]
        canvas_base64 = driver.execute_script(
            "return arguments[0].toDataURL('image/png').substring(21);", canvas
        )
        canvas_png = base64.b64decode(canvas_base64)

        # Save the PNG to the 'log' directory with the commit hash as the filename
        png_path = os.path.join(log_dir, f"{commit.hexsha}.png")
        with open(os.path.join(log_dir, f"{commit.hexsha}.png"), "wb") as f:
            f.write(canvas_png)

        # Append the PNG to the markdown file
        with open(os.path.join(log_dir, HISTORY_FILE + ".html"), "a") as f:
            f.write(f'<img src="{commit.hexsha}.png" alt="{commit.hexsha}">\n')

        # Add the PNG path to the commit data
        if os.path.exists(png_path):
            commit_html_data["png_exists"] = True
            commit_html_data["png_path"] = f"{commit.hexsha}.png"
    else:
        print(f"No canvas element found for commit {commit.hexsha}")

    # Append the commit data to the list
    commits_html.append(commit_html_data)

html = main_template.render(commits=commits_html)

with open(os.path.join(log_dir, HISTORY_FILE + ".html"), "w") as f:
    f.write(html)

# Shutdown the server after the loop
httpd.shutdown()

# Close the browser
driver.quit()

# Delete the 'repo' directory
if os.path.exists(repo_dir):
    shutil.rmtree(repo_dir)

print(f"Deleted the directory '{repo_dir}'")
