import os
from flask import Flask, request, jsonify
from dotenv import load_dotenv

import time # For simulating work
import threading # For background tasks
import requests # For making HTTP requests to APIs
from datetime import datetime # For handling dates
import uuid # For generating unique task IDs

from twilio.rest import Client # Import Twilio client

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
COMPANIES_HOUSE_API_URL = "https://api.company-information.service.gov.uk"
ANYMAILFINDER_API_URL = "https://api.anymailfinder.com/v5.0"

# Initialize Twilio Client if credentials are available
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
else:
    app.logger.warning("Twilio credentials not fully set. SMS functionality will be disabled.")

APP_BASE_URL_CONFIG = os.getenv("APP_BASE_URL", "http://localhost:8000") # Assuming frontend runs on port 8000 or is configured
try:
    MAX_COMPANIES_TO_PROCESS_CONFIG = int(os.getenv("MAX_COMPANIES_TO_PROCESS", "10"))
except ValueError:
    app.logger.warning("MAX_COMPANIES_TO_PROCESS env variable is not a valid integer. Defaulting to 10.")
    MAX_COMPANIES_TO_PROCESS_CONFIG = 10


# In-memory store for task statuses and results (for simplicity, replace with Redis/DB in production)
# This is a very basic example for illustration.
tasks_db = {}

# Load API keys from environment variables
COMPANIES_HOUSE_API_KEY = os.getenv('COMPANIES_HOUSE_API_KEY')
ANYMAILFINDER_API_KEY = os.getenv('ANYMAILFINDER_API_KEY')
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# Basic configuration check
if not all([COMPANIES_HOUSE_API_KEY, ANYMAILFINDER_API_KEY, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
    app.logger.warning("One or more API keys are not set. Please check your .env file.")

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

    # Basic validation (can be expanded)
    if not data:
        app.logger.error("No data received in JSON payload")
        return jsonify({"status": "error", "message": "No data received"}), 400

    phone_number = data.get('phoneNumber')
    if not phone_number: # Crucial for SMS notification
        app.logger.error("Phone number not provided in submitted criteria")
        return jsonify({"status": "error", "message": "Phone number is required"}), 400

    # Generate a unique ID for this task
    task_id = str(uuid.uuid4())
    tasks_db[task_id] = {"status": "pending", "data": data, "phone_number": phone_number, "results": None}

    app.logger.info(f"Task {task_id} created for phone {phone_number} with data: {data}")

    # Start the background task
    thread = threading.Thread(target=process_lead_generation_task, args=(task_id,))
    thread.start()

    app.logger.info(f"Task {task_id} started in background thread.")
    return jsonify({"status": "success", "message": "Request received, processing will begin shortly.", "task_id": task_id}), 202 # 202 Accepted


def process_lead_generation_task(task_id):
    """
    This function runs in a background thread.
    It will eventually contain the logic for:
    1. Companies House API Search & Filtering
    2. Identify Decision Makers & Anymailfinder API Integration
    3. Store Leads Data (update tasks_db[task_id]['results'])
    4. Twilio SMS Integration
    """
    app.logger.info(f"[Task {task_id}] Background task started.")
    task_data = tasks_db[task_id]['data']
    phone_number_for_sms = tasks_db[task_id]['phone_number']

    try:
        app.logger.info(f"[Task {task_id}] Processing criteria: {task_data}")

        sic_codes = task_data.get('sicCodesArray', [])
        if not sic_codes:
            raise ValueError("No SIC codes provided for search.")

        # Using the first SIC code for initial search.
        # Companies House API search by SIC is more of a keyword search on 'description'
        # or exact code. A more advanced search might iterate or use different CH search capabilities.
        primary_sic_code = sic_codes[0]
        app.logger.info(f"[Task {task_id}] Searching companies with primary SIC code: {primary_sic_code}")

        # Search parameters for Companies House
        # items_per_page: max 100 for /search/companies
        # For simplicity, fetch first page. Implement pagination if needed.
        search_params = {'q': primary_sic_code, 'items_per_page': 100}
        search_results = make_companies_house_request("/search/companies", params=search_params)

        if not search_results or 'items' not in search_results:
            app.logger.info(f"[Task {task_id}] No companies found for SIC {primary_sic_code} or error in search.")
            tasks_db[task_id]['results'] = []
            tasks_db[task_id]['status'] = 'completed_no_results'
            return # Exiting the task function

        app.logger.info(f"[Task {task_id}] Found {search_results.get('total_results', 0)} potential companies. Processing first {len(search_results['items'])} items.")

        qualified_companies_profiles = []
        for company_item in search_results['items']:
            company_number = company_item.get('company_number')
            if not company_number:
                continue

            # Fetch full company profile
            company_profile = make_companies_house_request(f"/company/{company_number}")
            if not company_profile:
                app.logger.warning(f"[Task {task_id}] Could not fetch profile for company {company_number}.")
                continue

            # 1. Filter by Company Status (must be active)
            if company_profile.get('company_status') != 'active':
                app.logger.debug(f"[Task {task_id}] Company {company_number} is not active (status: {company_profile.get('company_status')}). Skipping.")
                continue

            # 2. Filter by Accounting Reference Date (Budget End Date)
            ard_filter_type = task_data.get('budgetEndDateSearchType')
            acc_ref_date_info = company_profile.get('accounting_reference_date')

            if ard_filter_type and acc_ref_date_info:
                ard_month = acc_ref_date_info.get('month')
                ard_day = acc_ref_date_info.get('day') # Not used for month-only search yet, but good to have

                if ard_filter_type == 'month':
                    search_month = task_data.get('budgetEndMonth')
                    if search_month and int(ard_month) != int(search_month):
                        app.logger.debug(f"[Task {task_id}] Company {company_number} ARD month {ard_month} does not match search month {search_month}. Skipping.")
                        continue
                elif ard_filter_type == 'range':
                    start_date_str = task_data.get('budgetEndStartDate')
                    end_date_str = task_data.get('budgetEndEndDate')
                    if start_date_str and end_date_str and ard_day and ard_month:
                        # This requires careful date logic: construct the company's next ARD or current financial year end
                        # For simplicity, this example will just compare months if day is not perfectly handled.
                        # A robust solution would calculate the full ARD for the relevant year.
                        # This is a placeholder for more complex date range logic.
                        # For now, let's assume we only have month from CH and compare against range start/end months.
                        # This is a simplification and needs refinement for accurate date range filtering.
                        try:
                            search_start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
                            search_end_date = datetime.strptime(end_date_str, "%Y-%m-%d")

                            # Simplistic: check if ARD month is within the range's start/end months (ignoring year for this example)
                            # This is NOT a complete date range check.
                            current_year = datetime.now().year
                            company_ard_this_year_approx = datetime(current_year, int(ard_month), int(ard_day))

                            # This logic is very basic and should be improved for real date range matching
                            if not (search_start_date <= company_ard_this_year_approx <= search_end_date):
                                # app.logger.debug(f"[Task {task_id}] Company {company_number} ARD {ard_month}-{ard_day} outside range {start_date_str}-{end_date_str}. Skipping.")
                                # continue # Temporarily disabling this complex filter for now
                                pass


            # TODO: Implement further filtering: Revenue, Employees, Location, ProfitPerEmployee
            # These often require parsing accounts filings, which is significantly more complex.
            # For now, let's assume companies passing status and ARD (if specified) are provisionally qualified.

            company_profile['search_date'] = datetime.now().isoformat() # Add search date
            company_profile['original_search_criteria'] = task_data # Store what was searched for
            qualified_companies_profiles.append(company_profile)
            app.logger.info(f"[Task {task_id}] Company {company_number} provisionally qualified.")

            if len(qualified_companies_profiles) >= MAX_COMPANIES_TO_PROCESS_CONFIG:
                app.logger.info(f"[Task {task_id}] Reached processing limit of {MAX_COMPANIES_TO_PROCESS_CONFIG} provisionally qualified companies.")
                break


        # Placeholder for actual results (will be built in next steps)
        # For now, results are the profiles of qualified companies
        tasks_db[task_id]['results'] = qualified_companies_profiles
        tasks_db[task_id]['status'] = 'completed_ch_search' # New status
        app.logger.info(f"[Task {task_id}] Companies House search and initial filtering completed. Found {len(qualified_companies_profiles)} companies.")

        app.logger.info(f"[Task {task_id}] Companies House search and initial filtering completed. Found {len(qualified_companies_profiles)} companies.")

        # Step 7: Identify Decision Makers & Anymailfinder API Integration
        final_leads_list = []
        TARGET_ROLES_KEYWORDS = ['director', 'ceo', 'chief executive officer', 'owner', 'founder', 'cfo', 'chief financial officer'] # Case-insensitive matching

        for company_profile in qualified_companies_profiles:
            company_number = company_profile.get('company_number')
            company_name = company_profile.get('company_name')
            accounting_ref_date = company_profile.get('accounting_reference_date', {})
            search_date_iso = company_profile.get('search_date')
            original_criteria = company_profile.get('original_search_criteria')

            app.logger.info(f"[Task {task_id}] Fetching officers for {company_name} ({company_number})")
            officers_data = make_companies_house_request(f"/company/{company_number}/officers", params={'items_per_page': 100})

            if not officers_data or 'items' not in officers_data:
                app.logger.warning(f"[Task {task_id}] No officers found or error for company {company_number}.")
                continue

            for officer in officers_data.get('items', []):
                officer_role_raw = officer.get('officer_role', '').lower()
                officer_name = officer.get('name', '')
                resigned_on = officer.get('resigned_on')

                if resigned_on: # Skip resigned officers
                    continue

                is_decision_maker = any(keyword in officer_role_raw for keyword in TARGET_ROLES_KEYWORDS)

                if is_decision_maker and officer_name:
                    app.logger.info(f"[Task {task_id}] Identified decision maker: {officer_name} ({officer_role_raw}) at {company_name}")

                    # Attempt to derive company domain (simplistic for now)
                    # A robust solution would use a dedicated library or service to find company websites/domains
                    # Example: "ACME LTD" -> "acmeltd.com" - very naive.
                    # Anymailfinder is better if it can take just company name, but docs suggest domain is preferred.
                    # Let's assume Anymailfinder can attempt with company_name if domain is not solid.
                    # The API docs for person search say "company_domain OR company_name"

                    anymail_params = {'company_name': company_name, 'full_name': officer_name}
                    # Or, if we had domain: anymail_params = {'company_domain': derived_domain, 'full_name': officer_name}

                    app.logger.info(f"[Task {task_id}] Querying Anymailfinder for {officer_name} at {company_name}")
                    email_search_result = make_anymailfinder_request(params=anymail_params)
                    time.sleep(1) # Basic rate limiting for Anymailfinder if making many calls

                    if email_search_result and email_search_result.get('email') and email_search_result.get('status') in ['verified', ' probabilmente_valida']: # 'probabilmente_valida' is 'likely valid'
                        found_email = email_search_result['email']
                        app.logger.info(f"[Task {task_id}] Found email for {officer_name}: {found_email}")
                        final_leads_list.append({
                            "company_name": company_name,
                            "company_number": company_number,
                            "person_name": officer_name,
                            "person_role": officer_role_raw,
                            "email": found_email,
                            "accounting_reference_date": f"{accounting_ref_date.get('day', 'N/A')}/{accounting_ref_date.get('month', 'N/A')}",
                            "search_performed_on": search_date_iso,
                            "original_search_criteria": original_criteria # For display/CSV
                        })
                    elif email_search_result and email_search_result.get('error') == 'not_found':
                        app.logger.info(f"[Task {task_id}] Email not found by Anymailfinder for {officer_name} at {company_name} (explicitly not found).")
                    else:
                        app.logger.warning(f"[Task {task_id}] Email not found or error from Anymailfinder for {officer_name} at {company_name}. Response: {email_search_result}")

        tasks_db[task_id]['results'] = final_leads_list
        tasks_db[task_id]['status'] = 'completed_anymailfinder' if final_leads_list else 'completed_no_emails'
        app.logger.info(f"[Task {task_id}] Anymailfinder processing complete. Found {len(final_leads_list)} leads with emails.")

        # Step 9: Twilio SMS Integration
        if tasks_db[task_id]['status'] in ['completed_anymailfinder', 'completed_no_emails'] and phone_number_for_sms:
            if twilio_client and TWILIO_PHONE_NUMBER:
                # TODO: Define how the frontend URL is constructed. For now, assume a relative path.
                # This needs to be the domain where your leads.html page will be served.
                # For local dev, it might be http://localhost:PORT_OF_YOUR_FRONTEND/leads.html?id=TASK_ID
                # Or if using Flask to serve leads.html: http://localhost:5001/leads/TASK_ID

                # Using a placeholder for the base URL for now. This should be configured.
                APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000") # Assuming frontend runs on port 8000 or is configured
                leads_page_link = f"{APP_BASE_URL}/leads.html?id={task_id}" # Or /leads/{task_id} if using path params for leads page

                sms_body = f"Your leads request is complete! View your leads here: {leads_page_link}"
                try:
                    message = twilio_client.messages.create(
                        to=phone_number_for_sms,
                        from_=TWILIO_PHONE_NUMBER,
                        body=sms_body
                    )
                    app.logger.info(f"[Task {task_id}] SMS sent successfully to {phone_number_for_sms}. Message SID: {message.sid}")
                    tasks_db[task_id]['sms_status'] = 'sent'
                except Exception as sms_e:
                    app.logger.error(f"[Task {task_id}] Failed to send SMS to {phone_number_for_sms}: {sms_e}", exc_info=True)
                    tasks_db[task_id]['sms_status'] = 'failed_to_send'
                    tasks_db[task_id]['sms_error'] = str(sms_e)
            else:
                app.logger.warning(f"[Task {task_id}] Twilio client or phone number not configured. Skipping SMS.")
                tasks_db[task_id]['sms_status'] = 'not_configured'
        else:
            app.logger.info(f"[Task {task_id}] Skipping SMS due to task status '{tasks_db[task_id]['status']}' or missing phone number.")


    except ValueError as ve:
        app.logger.error(f"[Task {task_id}] Value error during processing: {ve}", exc_info=True)
        tasks_db[task_id]['status'] = 'failed'
        tasks_db[task_id]['error'] = str(ve)
    except Exception as e:
        app.logger.error(f"[Task {task_id}] Unhandled error during background processing: {e}", exc_info=True)
        tasks_db[task_id]['status'] = 'failed'
        tasks_db[task_id]['error'] = str(e)
    finally:
        app.logger.info(f"[Task {task_id}] Background task finished with status: {tasks_db[task_id]['status']}")

def make_companies_house_request(endpoint, params=None):
    """Helper function to make requests to Companies House API."""
    headers = {'Authorization': COMPANIES_HOUSE_API_KEY}
    try:
        response = requests.get(f"{COMPANIES_HOUSE_API_URL}{endpoint}", headers=headers, params=params, timeout=10)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        app.logger.error(f"HTTP error occurred: {http_err} - Response: {response.text}")
    except requests.exceptions.ConnectionError as conn_err:
        app.logger.error(f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        app.logger.error(f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        app.logger.error(f"An error occurred: {req_err}")
    return None

def make_anymailfinder_request(params=None):
    """Helper function to make requests to Anymailfinder API for person search."""
    # Note: Anymailfinder uses API key in params, not headers for this specific endpoint
    # as per https://anymailfinder.com/email-finder-api/docs/find-decision-maker-email
    # It states: "The API key can be sent either through an api_key GET parameter or through the X-Api-Key header."
    # Using GET parameter for this example based on their primary doc example.

    if not params:
        params = {}
    params['api_key'] = ANYMAILFINDER_API_KEY

    try:
        # The endpoint is /search/person.json
        response = requests.get(f"{ANYMAILFINDER_API_URL}/search/person.json", params=params, timeout=15)
        response.raise_for_status()

        # Anymailfinder specific success check (based on common patterns, verify with actual usage)
        # Their docs don't specify HTTP codes for all scenarios, but mention "email" field presence.
        # Some services return 200 even if email not found, with a status in body.
        # For now, assume 200 means some form of valid response, check for email later.
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        # Anymailfinder might return 404 if no person found, or 400/401 for bad requests/key
        # Or 429 for rate limits.
        app.logger.error(f"Anymailfinder HTTP error: {http_err} - Response: {response.text}")
        if response.status_code == 404: # Potentially "not found"
            return {"error": "not_found", "message": "Person not found or no email available."}
        # Could add specific handling for 429 (rate limit) if needed
    except requests.exceptions.ConnectionError as conn_err:
        app.logger.error(f"Anymailfinder Connection error: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        app.logger.error(f"Anymailfinder Timeout error: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        app.logger.error(f"Anymailfinder Request error: {req_err}")
    return None

@app.route('/api/get_leads/<task_id>', methods=['GET'])
def get_leads_route(task_id):
    app.logger.info(f"Received request to get leads for task_id: {task_id}")
    task_info = tasks_db.get(task_id)

    if not task_info:
        app.logger.warning(f"Task ID {task_id} not found in tasks_db.")
        return jsonify({"status": "error", "message": "Task ID not found or results expired."}), 404

    # Prepare a response that includes status, results, and original data for context
    response_data = {
        "task_id": task_id,
        "status": task_info.get("status"),
        "phone_number": task_info.get("phone_number"), # For context, not strictly for leads page
        "results": task_info.get("results"),
        "error": task_info.get("error"), # Include error message if task failed
        "sms_status": task_info.get("sms_status"), # Include SMS status
        "sms_error": task_info.get("sms_error"),   # Include SMS error if any
        "task_data": task_info.get("data") # The original criteria submitted
    }

    # The frontend (leads_script.js) expects 'results' to be the list of leads.
    # It also uses 'task_data' (original_search_criteria from the first lead)
    # or 'task_data' directly from this response to display search criteria.
    # If results are directly under task_info['results'] and contain original_search_criteria,
    # leads_script.js will find it. Otherwise, it can use task_info['data'].

    app.logger.info(f"Returning data for task_id {task_id}: Status - {task_info.get('status')}, Results count - {len(task_info.get('results', [])) if task_info.get('results') is not None else 'N/A'}")
    return jsonify(response_data), 200


if __name__ == '__main__':
    app.run(debug=True, port=5001) # Running on a different port than typical frontend dev servers
