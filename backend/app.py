import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import time
import threading
import requests
from datetime import datetime
import uuid
from twilio.rest import Client
import re # For regex operations in domain derivation
from urllib.parse import urlparse # For parsing URLs to get domain

from flask_cors import CORS # Import CORS

load_dotenv()

app = Flask(__name__)
CORS(app) # Enable CORS for all routes by default for development
          # For production, you might want to restrict origins: CORS(app, resources={r"/api/*": {"origins": "http://localhost:8000"}})

COMPANIES_HOUSE_API_URL = "https://api.company-information.service.gov.uk"
ANYMAILFINDER_API_URL = "https://api.anymailfinder.com/v5.0"

COMPANIES_HOUSE_API_KEY = os.getenv('COMPANIES_HOUSE_API_KEY')
ANYMAILFINDER_API_KEY = os.getenv('ANYMAILFINDER_API_KEY')
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
else:
    app.logger.warning("Twilio credentials not fully set. SMS functionality will be disabled.")

APP_BASE_URL_CONFIG = os.getenv("APP_BASE_URL", "http://localhost:8000")
try:
    MAX_COMPANIES_TO_PROCESS_CONFIG = int(os.getenv("MAX_COMPANIES_TO_PROCESS", "10"))
except ValueError:
    app.logger.warning("MAX_COMPANIES_TO_PROCESS env variable is not a valid integer. Defaulting to 10.")
    MAX_COMPANIES_TO_PROCESS_CONFIG = 10
try:
    MAX_INITIAL_SEARCH_RESULTS_CONFIG = int(os.getenv("MAX_INITIAL_SEARCH_RESULTS", "200"))
except ValueError:
    app.logger.warning("MAX_INITIAL_SEARCH_RESULTS env variable is not a valid integer. Defaulting to 200.")
    MAX_INITIAL_SEARCH_RESULTS_CONFIG = 200

tasks_db = {}

if not all([COMPANIES_HOUSE_API_KEY, ANYMAILFINDER_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
    app.logger.warning("One or more core API keys (Companies House, Anymailfinder, Twilio) are not set. Please check .env file.")


@app.route('/')
def home():
    return "Backend is running!"

@app.route('/api/submit_criteria', methods=['POST'])
def submit_criteria_route():
    if not request.is_json:
        app.logger.error("Request content type was not application/json")
        return jsonify({"status": "error", "message": "Request must be JSON"}), 400

    data = request.get_json()
    app.logger.info(f"Received data: {data}")

    if not data:
        app.logger.error("No data received in JSON payload")
        return jsonify({"status": "error", "message": "No data received"}), 400

    phone_number = data.get('phoneNumber')
    if not phone_number:
        app.logger.error("Phone number not provided in submitted criteria")
        return jsonify({"status": "error", "message": "Phone number is required"}), 400

    task_id = str(uuid.uuid4())
    tasks_db[task_id] = {"status": "pending", "data": data, "phone_number": phone_number, "results": None, "error": None, "sms_status": "pending"}

    app.logger.info(f"Task {task_id} created for phone {phone_number} with data: {data}")

    thread = threading.Thread(target=process_lead_generation_task, args=(task_id,))
    thread.start()

    app.logger.info(f"Task {task_id} started in background thread.")
    return jsonify({"status": "success", "message": "Request received, processing will begin shortly.", "task_id": task_id}), 202

def process_lead_generation_task(task_id):
    app.logger.info(f"[Task {task_id}] Background task started.")
    task_data = tasks_db[task_id]['data']
    phone_number_for_sms = tasks_db[task_id]['phone_number']

    try:
        app.logger.info(f"[Task {task_id}] Processing criteria: {task_data}")

        sic_codes = task_data.get('sicCodesArray', [])
        if not sic_codes:
            raise ValueError("No SIC codes provided for search.")

        primary_sic_code = sic_codes[0]
        app.logger.info(f"[Task {task_id}] Searching companies with primary SIC code: {primary_sic_code}")

        all_company_items_from_search = []
        current_start_index = 0
        items_per_page_ch = 100 # Max for this search endpoint

        while True:
            search_params = {
                'q': primary_sic_code,
                'items_per_page': items_per_page_ch,
                'start_index': current_start_index
            }
            search_page_results = make_companies_house_request("/search/companies", params=search_params)

            if not search_page_results or 'items' not in search_page_results or not search_page_results['items']:
                app.logger.info(f"[Task {task_id}] No more companies found for SIC {primary_sic_code} at start_index {current_start_index} or error in search page.")
                break

            all_company_items_from_search.extend(search_page_results['items'])
            app.logger.info(f"[Task {task_id}] Fetched {len(search_page_results['items'])} items from CH search. Total fetched so far: {len(all_company_items_from_search)}.")

            total_results_available = search_page_results.get('total_results', 0)
            current_start_index += items_per_page_ch

            if current_start_index >= total_results_available or len(all_company_items_from_search) >= MAX_INITIAL_SEARCH_RESULTS_CONFIG:
                app.logger.info(f"[Task {task_id}] Reached end of CH search results ({total_results_available} total) or initial search limit ({MAX_INITIAL_SEARCH_RESULTS_CONFIG}). Fetched {len(all_company_items_from_search)} items.")
                break

            time.sleep(0.5) # Small delay between paginated requests to be polite to CH API

        qualified_companies_profiles = []

        if not all_company_items_from_search:
            app.logger.info(f"[Task {task_id}] No companies found for SIC {primary_sic_code} after attempting pagination.")
            tasks_db[task_id]['results'] = []
            tasks_db[task_id]['status'] = 'completed_no_results'
        else:
            app.logger.info(f"[Task {task_id}] Total of {len(all_company_items_from_search)} company items fetched from CH search. Now filtering.")
            for company_item in all_company_items_from_search:
                company_number = company_item.get('company_number')
                if not company_number:
                    continue

                company_profile = make_companies_house_request(f"/company/{company_number}")
                if not company_profile:
                    app.logger.warning(f"[Task {task_id}] Could not fetch profile for company {company_number}.")
                    continue

                if company_profile.get('company_status') != 'active':
                    app.logger.debug(f"[Task {task_id}] Company {company_number} is not active. Skipping.")
                    continue

                ard_filter_type = task_data.get('budgetEndDateSearchType')
                acc_ref_date_info = company_profile.get('accounting_reference_date')

                if ard_filter_type and acc_ref_date_info:
                    ard_month_str = str(acc_ref_date_info.get('month', '')).zfill(2)
                    ard_day_str = str(acc_ref_date_info.get('day', '')).zfill(2)

                    if ard_filter_type == 'month':
                        search_month_str = task_data.get('budgetEndMonth')
                        if search_month_str and ard_month_str.isdigit() and int(ard_month_str) != int(search_month_str):
                            app.logger.debug(f"[Task {task_id}] Company {company_number} ARD month {ard_month_str} != search month {search_month_str}. Skipping.")
                            continue
                    elif ard_filter_type == 'range':
                        start_date_str = task_data.get('budgetEndStartDate')
                        end_date_str = task_data.get('budgetEndEndDate')
                        if start_date_str and end_date_str and ard_day_str.isdigit() and ard_month_str.isdigit():
                            try:
                                search_start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                                search_end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

                                ard_day = int(ard_day_str)
                                ard_month = int(ard_month_str)

                                if not (1 <= ard_month <= 12 and 1 <= ard_day <= 31):
                                    app.logger.warning(f"[Task {task_id}] Invalid ARD day/month for {company_number}: Day {ard_day}, Month {ard_month}. Skipping ARD range check.")
                                else:
                                    match_found_in_range = False
                                    # Iterate years from user's search_start_date.year - 1 to search_end_date.year + 1
                                    # This window covers ARDs that might fall just outside the direct year span but still be relevant
                                    year_range_to_check_start = search_start_date.year - 1
                                    year_range_to_check_end = search_end_date.year + 1

                                    for potential_ard_year in range(year_range_to_check_start, year_range_to_check_end + 1):
                                        try:
                                            company_ard_concrete_date = datetime(potential_ard_year, ard_month, ard_day).date()
                                            if search_start_date <= company_ard_concrete_date <= search_end_date:
                                                match_found_in_range = True
                                                app.logger.debug(f"[Task {task_id}] Company {company_number} ARD {company_ard_concrete_date} is IN range {start_date_str} - {end_date_str}.")
                                                break
                                        except ValueError:
                                            app.logger.debug(f"[Task {task_id}] Could not construct date for {potential_ard_year}-{ard_month_str}-{ard_day_str} for company {company_number}")
                                            continue

                                    if not match_found_in_range:
                                        app.logger.debug(f"[Task {task_id}] Company {company_number} ARD ({ard_day_str}/{ard_month_str}) does not fall into range {start_date_str} - {end_date_str} for relevant years. Skipping.")
                                        continue
                            except ValueError as date_err:
                                 app.logger.warning(f"[Task {task_id}] ARD range date parse error (user dates or company ARD): {date_err} for CNo {company_number}. Skipping ARD range check.")

                # 3. Filter by Location (if provided by user)
                user_location_filter = task_data.get('location', '').strip().lower()
                if user_location_filter:
                    address = company_profile.get('registered_office_address', {})
                    address_parts = [
                        address.get('address_line_1', ''),
                        address.get('address_line_2', ''),
                        address.get('locality', ''), # Often city
                        address.get('region', ''),   # Often county
                        address.get('postal_code', ''),
                        address.get('country', '')
                    ]
                    # Join all address parts into a single string for searching
                    full_address_str = " ".join(filter(None, address_parts)).lower()

                    if user_location_filter not in full_address_str:
                        app.logger.debug(f"[Task {task_id}] Company {company_number} location '{full_address_str}' does not match user filter '{user_location_filter}'. Skipping.")
                        continue

                # 4. Revenue & Employee Count Filtering (Investigation & Best Effort)
                # NOTE: The Companies House basic company profile API does NOT reliably provide structured,
                # current numerical data for revenue or employee count. These are typically found in filed PDF accounts.
                # This section is a placeholder to acknowledge the filter criteria exist but cannot be
                # accurately applied without significantly more complex document fetching and parsing.

                revenue_min = task_data.get('revenueMin')
                revenue_max = task_data.get('revenueMax')
                employees_min = task_data.get('employeesMin')
                employees_max = task_data.get('employeesMax')
                # profit_per_employee_min = task_data.get('profitPerEmployeeMin') # Depends on revenue/profit and employees

                # Example: Check accounts type if it gives a very rough hint (e.g., 'small' company)
                # last_accounts_type = company_profile.get('accounts', {}).get('last_accounts', {}).get('type')
                # This is usually too imprecise for specific min/max numerical filters.

                if revenue_min is not None or revenue_max is not None or \
                   employees_min is not None or employees_max is not None:
                    app.logger.info(f"[Task {task_id}] Revenue/Employee filter criteria present for CNo {company_number}, but precise filtering is not applied due to data unavailability in basic CH profile. Criteria: RevMin={revenue_min}, RevMax={revenue_max}, EmpMin={employees_min}, EmpMax={employees_max}")

                # If, in the future, some direct fields become available or a simplified logic is acceptable,
                # filtering would be added here. For now, we acknowledge and pass through.

                company_profile['search_date'] = datetime.now().isoformat()
                company_profile['original_search_criteria'] = task_data
                qualified_companies_profiles.append(company_profile)
                app.logger.info(f"[Task {task_id}] Company {company_number} provisionally qualified (passed status, ARD, location - revenue/employee not actively filtered).")

                if len(qualified_companies_profiles) >= MAX_COMPANIES_TO_PROCESS_CONFIG:
                    app.logger.info(f"[Task {task_id}] Reached processing limit of {MAX_COMPANIES_TO_PROCESS_CONFIG}.")
                    break

            app.logger.info(f"[Task {task_id}] CH search and basic filtering done. {len(qualified_companies_profiles)} companies provisionally qualified.")
            tasks_db[task_id]['status'] = 'completed_ch_search'
            tasks_db[task_id]['results'] = qualified_companies_profiles

        # Step 7: Anymailfinder Integration
        final_leads_list = []
        # Ensure we only proceed if qualified_companies_profiles was populated and is not None
        if tasks_db[task_id]['status'] == 'completed_ch_search' and qualified_companies_profiles:
            TARGET_ROLES_KEYWORDS = ['director', 'ceo', 'chief executive officer', 'owner', 'founder', 'cfo', 'chief financial officer']

            for company_profile_item in qualified_companies_profiles:
                company_number = company_profile_item.get('company_number')
                company_name = company_profile_item.get('company_name')
                accounting_ref_date = company_profile_item.get('accounting_reference_date', {})
                search_date_iso = company_profile_item.get('search_date')
                original_criteria = company_profile_item.get('original_search_criteria')

                app.logger.info(f"[Task {task_id}] Fetching officers for {company_name} ({company_number})")
                officers_data = make_companies_house_request(f"/company/{company_number}/officers", params={'items_per_page': 100})

                if not officers_data or 'items' not in officers_data:
                    app.logger.warning(f"[Task {task_id}] No officers or error for {company_number}.")
                    continue

                for officer in officers_data.get('items', []):
                    officer_role_raw = officer.get('officer_role', '').lower()
                    officer_name = officer.get('name', '')
                    resigned_on = officer.get('resigned_on')

                    if resigned_on: continue
                    is_decision_maker = any(keyword in officer_role_raw for keyword in TARGET_ROLES_KEYWORDS)

                    if is_decision_maker and officer_name:
                        app.logger.info(f"[Task {task_id}] DM: {officer_name} ({officer_role_raw}) at {company_name}")

                        derived_domain = None
                        # 1. Check for official website link from Companies House profile
                        company_links = company_profile_item.get('links', {})
                        official_website_url = company_links.get('company_website')
                        if official_website_url:
                            derived_domain = extract_domain_from_url(official_website_url)
                            app.logger.info(f"[Task {task_id}] Extracted domain '{derived_domain}' from CH profile website link: {official_website_url}")

                        # 2. If no domain from CH link, try heuristic derivation from company name
                        if not derived_domain:
                            derived_domain = heuristically_derive_domain_from_name(company_name)
                            if derived_domain:
                                app.logger.info(f"[Task {task_id}] Heuristically derived domain '{derived_domain}' from company name: {company_name}")

                        anymail_params = {}
                        if derived_domain:
                            anymail_params['company_domain'] = derived_domain
                            anymail_params['full_name'] = officer_name
                        else:
                            # Fallback to using company_name if no domain could be derived
                            anymail_params['company_name'] = company_name
                            anymail_params['full_name'] = officer_name
                            app.logger.info(f"[Task {task_id}] No domain derived, using company_name '{company_name}' for Anymailfinder.")

                        app.logger.info(f"[Task {task_id}] Querying Anymailfinder with params: {anymail_params}")
                        email_search_result = make_anymailfinder_request(params=anymail_params)
                        time.sleep(1)

                        if email_search_result and email_search_result.get('email') and email_search_result.get('status') in ['verified', ' probabilmente_valida']:
                            found_email = email_search_result['email']
                            app.logger.info(f"[Task {task_id}] Email for {officer_name}: {found_email}")
                            final_leads_list.append({
                                "company_name": company_name, "company_number": company_number,
                                "person_name": officer_name, "person_role": officer_role_raw,
                                "email": found_email,
                                "accounting_reference_date": f"{str(accounting_ref_date.get('day','N/A')).zfill(2)}/{str(accounting_ref_date.get('month','N/A')).zfill(2)}",
                                "search_performed_on": search_date_iso,
                                "original_search_criteria": original_criteria
                            })
                        elif email_search_result and email_search_result.get('error') == 'not_found':
                            app.logger.info(f"[Task {task_id}] Email not found (AMF) for {officer_name} at {company_name}.")
                        else:
                            app.logger.warning(f"[Task {task_id}] No email/error from AMF for {officer_name}. Resp: {email_search_result}")

            tasks_db[task_id]['results'] = final_leads_list
            tasks_db[task_id]['status'] = 'completed_anymailfinder' if final_leads_list else 'completed_no_emails'
            app.logger.info(f"[Task {task_id}] AMF done. {len(final_leads_list)} leads with emails.")

        elif tasks_db[task_id]['status'] == 'completed_no_results':
            app.logger.info(f"[Task {task_id}] Skipping Anymailfinder as no companies were found by CH search.")
            # Status remains 'completed_no_results', results remains [] from CH part or empty if CH failed.

        # Step 9: Twilio SMS Integration
        current_task_status = tasks_db[task_id]['status']
        if current_task_status not in ['failed', 'pending'] and phone_number_for_sms:
            if twilio_client and TWILIO_PHONE_NUMBER:
                leads_page_link = f"{APP_BASE_URL_CONFIG}/leads.html?id={task_id}"
                sms_body = f"Your leads request ({current_task_status}) is complete! View your leads here: {leads_page_link}"
                if current_task_status == 'completed_no_results' or current_task_status == 'completed_no_emails':
                    sms_body = f"Your leads request is complete ({current_task_status}). No leads with emails were found based on your criteria. Link for details: {leads_page_link}"

                try:
                    message = twilio_client.messages.create(to=phone_number_for_sms, from_=TWILIO_PHONE_NUMBER, body=sms_body)
                    app.logger.info(f"[Task {task_id}] SMS sent to {phone_number_for_sms}. SID: {message.sid}")
                    tasks_db[task_id]['sms_status'] = 'sent'
                except Exception as sms_e:
                    app.logger.error(f"[Task {task_id}] SMS fail to {phone_number_for_sms}: {sms_e}", exc_info=True)
                    tasks_db[task_id]['sms_status'] = 'failed_to_send'
                    tasks_db[task_id]['sms_error'] = str(sms_e)
            else:
                app.logger.warning(f"[Task {task_id}] Twilio not configured. Skip SMS.")
                tasks_db[task_id]['sms_status'] = 'not_configured'
        else:
            app.logger.info(f"[Task {task_id}] Skip SMS: status '{current_task_status}' or no phone.")

    except ValueError as ve:
        app.logger.error(f"[Task {task_id}] Value error: {ve}", exc_info=True)
        tasks_db[task_id]['status'] = 'failed'
        tasks_db[task_id]['error'] = str(ve)
    except Exception as e:
        app.logger.error(f"[Task {task_id}] Unhandled error: {e}", exc_info=True)
        tasks_db[task_id]['status'] = 'failed'
        tasks_db[task_id]['error'] = str(e)
    finally:
        app.logger.info(f"[Task {task_id}] Background task finished with status: {tasks_db[task_id]['status']}")

def make_companies_house_request(endpoint, params=None):
    headers = {'Authorization': COMPANIES_HOUSE_API_KEY}
    retries = 1 # Number of retries for rate limiting

    for attempt in range(retries + 1):
        try:
            response = requests.get(f"{COMPANIES_HOUSE_API_URL}{endpoint}", headers=headers, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            app.logger.error(f"CH HTTP error on attempt {attempt + 1}: {http_err} - Response: {response.text if response else 'No response text'}")
            if response is not None and response.status_code == 429 and attempt < retries:
                retry_after = int(response.headers.get("Retry-After", 5)) # Use Retry-After header if available, else 5s
                app.logger.warning(f"Rate limit hit for CH. Retrying attempt {attempt + 2} after {retry_after} seconds.")
                time.sleep(retry_after)
                continue # Go to next attempt
            # For other HTTP errors, or if retries exhausted for 429, break and return None below
            break
        except requests.exceptions.ConnectionError as conn_err:
            app.logger.error(f"CH Connection error on attempt {attempt + 1}: {conn_err}")
            if attempt < retries:
                time.sleep(5) # Wait before retrying connection error
                continue
            break
    except requests.exceptions.Timeout as timeout_err:
        app.logger.error(f"CH Timeout error: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        app.logger.error(f"CH Request error: {req_err}")
    return None

def make_anymailfinder_request(params=None):
    if not params: params = {}
    params['api_key'] = ANYMAILFINDER_API_KEY
    retries = 1 # Number of retries

    for attempt in range(retries + 1):
        try:
            response = requests.get(f"{ANYMAILFINDER_API_URL}/search/person.json", params=params, timeout=15)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            app.logger.error(f"Anymailfinder HTTP error on attempt {attempt + 1}: {http_err} - Response: {response.text if response else 'No response text'}")
            if response is not None and response.status_code == 429 and attempt < retries:
                # Anymailfinder might not send Retry-After, so use a fixed delay
                retry_delay = 10
                app.logger.warning(f"Rate limit hit for Anymailfinder. Retrying attempt {attempt + 2} after {retry_delay} seconds.")
                time.sleep(retry_delay)
                continue
            elif response is not None and response.status_code == 404: # Specific handling for 404
                return {"error": "not_found", "message": "Person not found or no email available."}
            break # For other HTTP errors or if retries exhausted
        except requests.exceptions.ConnectionError as conn_err:
            app.logger.error(f"Anymailfinder Connection error on attempt {attempt + 1}: {conn_err}")
            if attempt < retries:
                time.sleep(10) # Wait before retrying connection error
                continue
            break
        except requests.exceptions.Timeout as timeout_err:
            app.logger.error(f"Anymailfinder Timeout error on attempt {attempt + 1}: {timeout_err}")
            # Decide if retry on timeout is useful, for now, fail
            break
        except requests.exceptions.RequestException as req_err: # Ensure this is at the same level as other excepts in the loop
            app.logger.error(f"Anymailfinder Request error on attempt {attempt + 1}: {req_err}")
            if attempt < retries:
                time.sleep(5) # Generic wait for other request exceptions before retry
                continue
            break # Break if retries exhausted or it's a non-retryable request exception

    return None # Default return if loop finishes without success

def extract_domain_from_url(website_url):
    """Extracts the domain (e.g., example.com) from a full URL."""
    if not website_url:
        return None
    try:
        # Add scheme if missing, as urlparse needs it for netloc
        if not website_url.startswith(('http://', 'https://')):
            website_url = 'https://' + website_url
        parsed_url = urlparse(website_url)
        domain = parsed_url.netloc
        # Remove 'www.' prefix if it exists
        if domain.startswith('www.'):
            domain = domain[4:]
        return domain if domain else None
    except Exception as e:
        app.logger.debug(f"Could not parse domain from URL '{website_url}': {e}")
        return None

def heuristically_derive_domain_from_name(company_name):
    """Tries to guess a domain from a company name. Highly heuristic."""
    if not company_name:
        return None

    name = company_name.lower()
    # Remove common suffixes more carefully
    suffixes_to_remove = [
        ' limited liability partnership', ' public limited company',
        ' community interest company', ' ltd', ' limited',
        ' plc', ' llp', ' cic'
    ] # Order matters: longer ones first
    for suffix in suffixes_to_remove:
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip() # remove suffix and trailing space
            break

    # Remove non-alphanumeric characters except hyphens (which are valid in domains)
    # Replace multiple spaces/hyphens with a single hyphen, then remove leading/trailing hyphens
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'\s+', '-', name) # Replace spaces with hyphens
    name = re.sub(r'-+', '-', name)   # Replace multiple hyphens with single
    name = name.strip('-')           # Remove leading/trailing hyphens

    if not name:
        return None # If name becomes empty after cleaning

    # For UK, .co.uk is common, then .com.
    # This is a very basic guess and does not verify existence.
    # For simplicity, we return the .co.uk version. A more advanced version might return a list.
    return f"{name}.co.uk"


@app.route('/api/get_leads/<task_id>', methods=['GET'])
def get_leads_route(task_id):
    app.logger.info(f"Received request to get leads for task_id: {task_id}")
    task_info = tasks_db.get(task_id)

    if not task_info:
        app.logger.warning(f"Task ID {task_id} not found in tasks_db.")
        return jsonify({"status": "error", "message": "Task ID not found or results expired."}), 404

    response_data = {
        "task_id": task_id,
        "status": task_info.get("status"),
        "phone_number": task_info.get("phone_number"),
        "results": task_info.get("results"),
        "error": task_info.get("error"),
        "sms_status": task_info.get("sms_status"),
        "sms_error": task_info.get("sms_error"),
        "task_data": task_info.get("data")
    }

    app.logger.info(f"Returning data for task_id {task_id}: Status - {task_info.get('status')}, Results count - {len(task_info.get('results', [])) if task_info.get('results') is not None else 'N/A'}")
    return jsonify(response_data), 200

if __name__ == '__main__':
    app.run(debug=True, port=5001)
