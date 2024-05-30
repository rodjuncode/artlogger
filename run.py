import argparse
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

# Create the parser
parser = argparse.ArgumentParser(description='Process a GitHub URL.')

# Add the arguments
parser.add_argument('URL', metavar='URL', type=str, help='The GitHub URL to process')
parser.add_argument('--branch', metavar='branch', type=str, default='main', help='The branch to checkout')
parser.add_argument('--wait', metavar='wait', type=int, default=5, help='The number of seconds to wait for the page to load')

# Parse the arguments
args = parser.parse_args()

# Store the absolute path of the parent directory
parent_dir = os.path.abspath(os.getcwd())

# Define the absolute paths of the 'repo' and 'log' directories
repo_dir = os.path.join(parent_dir, 'repo')
log_dir = os.path.join(parent_dir, 'log')

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

# Get all commits and filter out those with "#ignorelog" in the message
commits = [commit for commit in repo.iter_commits() if '#ignorelog' not in commit.message]

print(f'Processed URL: {args.URL}')
print(f'Number of commits without "#ignorelog": {len(commits)}')

# Set up Selenium with a headless browser
webdriver_service = Service(ChromeDriverManager().install())
chrome_options = Options()
chrome_options.add_argument("--headless")
driver = webdriver.Chrome(service=webdriver_service, options=chrome_options)

# Define the starting port
port = 8000
Handler = http.server.SimpleHTTPRequestHandler

# Start the server before the loop
httpd = socketserver.TCPServer(("", port), Handler)
print(f"Serving at port {port}")
httpd_thread = threading.Thread(target=httpd.serve_forever)
httpd_thread.start()

# Create a markdown file in the 'log' directory
with open(os.path.join(log_dir, 'process_history.md'), 'w') as f:
    # Write the title to the markdown file
    f.write("# Process History\n")

for commit in reversed(commits):
    # Checkout the commit
    repo.git.checkout(commit)

    # Print the current working directory
    print(f"Current working directory: {os.getcwd()}")

    # Check if there are any remotes
    if repo.remotes:
        # Get the first remote's URL
        remote_url = next(iter(repo.remotes)).url
        remote_url = next(iter(repo.remotes)).url.replace('.git', '')
    else:
        # Remote url is false
        remote_url = False

    # Append to the markdown file in the 'log' directory
    with open(os.path.join(log_dir, 'process_history.md'), 'a') as f:
        # Write the commit message as a subtitle
        f.write(f"## {commit.message}\n")

        # Check if the remote URL exists
        if remote_url:
            # Write the commit hash as a link
            f.write(f"[{commit.hexsha}]({remote_url}/commit/{commit.hexsha})\n\n")
            

    # Check if the 'repo' directory exists before trying to change to it
    if os.path.exists(repo_dir):
        os.chdir(repo_dir)
    else:
        print(f"The directory '{repo_dir}' does not exist.")
        continue

    # Navigate to the page
    driver.get(f'http://localhost:{port}')

    # Wait for the page to load
    time.sleep(args.wait)

    # Check if there is a canvas element on the page
    canvas_elements = driver.find_elements(By.TAG_NAME, 'canvas')
    if canvas_elements:
        # Get the canvas as a PNG
        canvas = canvas_elements[0]
        canvas_base64 = driver.execute_script("return arguments[0].toDataURL('image/png').substring(21);", canvas)
        canvas_png = base64.b64decode(canvas_base64)

        # Save the PNG to the 'log' directory with the commit hash as the filename
        png_path = os.path.join(log_dir, f'{commit.hexsha}.png')
        with open(os.path.join(log_dir, f'{commit.hexsha}.png'), 'wb') as f:
            f.write(canvas_png)

        # Append the PNG to the markdown file
        with open(os.path.join(log_dir, 'process_history.md'), 'a') as f:
            f.write(f"![{commit.hexsha}]({commit.hexsha}.png)\n")            
    else:
        print(f"No canvas element found for commit {commit.hexsha}")

        # Append a message indicating that no visualization is available to the markdown file
        with open(os.path.join(log_dir, 'process_history.md'), 'a') as f:
            f.write("No available visualization for this commit\n")

# Shutdown the server after the loop
httpd.shutdown()

# Close the browser
driver.quit()

# Delete the 'repo' directory
if os.path.exists(repo_dir):
    shutil.rmtree(repo_dir)

print(f"Deleted the directory '{repo_dir}'")