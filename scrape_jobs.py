from flask import Flask, render_template, request
import requests
from bs4 import BeautifulSoup
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import Pool, Manager
import time
from tqdm import tqdm
import sys

app = Flask(__name__)

base_url = 'https://remoteok.com/remote-dev-jobs?page={}'

def scrape_page(page_number):
    url = base_url.format(page_number)
    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    if response.status_code != 200:
        print(f'Failed to retrieve page {page_number}')
        return []
    
    soup = BeautifulSoup(response.content, 'html.parser')
    job_listings = soup.find_all('tr', class_='job')
    
    jobs = []
    for job in job_listings:
        title = job.find('h2', itemprop='title').get_text(strip=True)
        company = job.find('h3', itemprop='name').get_text(strip=True)
        location = job.find('div', class_='location').get_text(strip=True) if job.find('div', class_='location') else 'Remote'
        jobs.append({
            'Title': title,
            'Company': company,
            'Location': location
        })
    
    return jobs

def scrape_jobs(pages, max_workers=5):
    print("Starting parallel scraping using threads with mutex synchronisation...")
    start_time = time.time()
    
    all_jobs = []
    lock = threading.Lock()  # Mutex for synchronization
    
    def worker(page):
        try:
            jobs = scrape_page(page)
            with lock: # Ensuring only one thread accesses all_jobs at a time
                all_jobs.extend(jobs)
        except BrokenPipeError:
            sys.stderr.write("BrokenPipeError ignored\n")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(worker, page): page for page in range(1, pages + 1)}
        for future in tqdm(as_completed(futures), total=pages, desc="Scraping (Threads)"):
            future.result()  # Ensure any exceptions are raised
    
    end_time = time.time()
    spent_time = end_time - start_time
    print(f"Parallel (Threads) scraping completed in {spent_time:.2f} seconds.")
    return all_jobs


def scrape_jobs_sequential(pages):
    print("Starting sequential scraping...")
    start_time = time.time()
    
    all_jobs = []
    for page in tqdm(range(1, pages + 1), desc='Scraping Pages'):
        jobs = scrape_page(page)
        all_jobs.extend(jobs)
        print(f'Page {page} scraped successfully.')
    
    end_time = time.time()
    spent_time = end_time - start_time
    print(f"\nSequential scraping completed in {spent_time:.2f} seconds.")
    return all_jobs


def scrape_jobs_multiprocess(pages, max_workers=5):
    with Manager() as manager:
        all_jobs = manager.list()
        with Pool(processes=max_workers) as pool:
            results = pool.map(scrape_page, range(1, pages + 1))
            for jobs in tqdm(results, total=pages, desc="Scraping (Processes)"):
                all_jobs.extend(jobs)
        return list(all_jobs)

@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    max_pages = 2  # Number of pages to scrape
    max_workers = 1  # Number of workers
    method = request.args.get('method', 'processes')  # Method to use for scraping
    
    start_time = time.time()  # Start time for overall request processing
    
    if method == 'threads':
        jobs = scrape_jobs(max_pages, max_workers=max_workers)
    elif method == 'processes':
        jobs = scrape_jobs_multiprocess(max_pages, max_workers=max_workers)
    else:
        jobs = scrape_jobs_sequential(max_pages)
    
    end_time = time.time()  # End time for overall request processing
    spent_time = end_time - start_time  # Calculate total time spent
    
    jobs_per_page = 10  # Number of jobs per page
    start = (page - 1) * jobs_per_page
    end = start + jobs_per_page
    total_pages = (len(jobs) // jobs_per_page) + (1 if len(jobs) % jobs_per_page > 0 else 0)
    
    return render_template('index.html', jobs=jobs[start:end], page=page, total_pages=total_pages, method=method, spent_time=spent_time)

if __name__ == '__main__':
    app.run(debug=True)
