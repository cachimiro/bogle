document.addEventListener('DOMContentLoaded', () => {
    const leadsTableBody = document.getElementById('leadsTableBody');
    const downloadCsvBtn = document.getElementById('downloadCsvBtn');
    const noLeadsMessage = document.getElementById('noLeadsMessage');
    const loadingMessage = document.getElementById('loadingMessage');
    const searchInfoDiv = document.getElementById('searchInfo');
    const searchDateSpan = document.getElementById('searchDate');
    const searchCriteriaPre = document.getElementById('searchCriteria');

    let leadsData = []; // To store fetched leads for CSV export

    const getTaskIdFromUrl = () => {
        const params = new URLSearchParams(window.location.search);
        return params.get('id');
    };

    const fetchLeads = async (taskId) => {
        if (!taskId) {
            loadingMessage.textContent = 'Error: No Task ID provided in URL.';
            loadingMessage.style.color = 'red';
            return;
        }

        try {
            // Ensure backend is running on port 5001 as configured in backend/app.py
            const BACKEND_BASE_URL = 'http://localhost:5001';
            const response = await fetch(`${BACKEND_BASE_URL}/api/get_leads/${taskId}`);

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ message: response.statusText }));
                throw new Error(`Failed to fetch leads: ${errorData.message || response.status}`);
            }

            const data = await response.json();
            loadingMessage.style.display = 'none';

            if (data && data.results && data.results.length > 0) {
                leadsData = data.results; // Store for CSV
                populateTable(leadsData);
                displaySearchInfo(data.results[0]); // Assuming search info is consistent per lead
                downloadCsvBtn.style.display = 'inline-block';
                searchInfoDiv.style.display = 'block';
            } else if (data && data.status && data.status !== 'completed_anymailfinder' && data.status !== 'completed_no_emails' && data.status !== 'completed_ch_search' ) {
                // If status indicates task is still pending or failed at an earlier stage
                noLeadsMessage.textContent = `Task status: ${data.status}. Leads are not yet available or processing failed. Error: ${data.error || 'N/A'}`;
                noLeadsMessage.style.display = 'block';
            }

            else {
                 noLeadsMessage.textContent = 'No leads found matching your criteria, or no emails could be identified.';
                noLeadsMessage.style.display = 'block';
                // Display search info even if no leads, if available in task data
                if (data && data.task_data) { // Assuming backend sends original task_data if results are empty
                   displaySearchInfoFromTaskData(data.task_data);
                   searchInfoDiv.style.display = 'block';
                } else if (data && data.results && data.results.length === 0 && data.results[0] && data.results[0].original_search_criteria) {
                    // Fallback if results is an empty array but contains search criteria
                    displaySearchInfo(data.results[0]);
                    searchInfoDiv.style.display = 'block';
                }
            }

        } catch (error) {
            console.error('Error fetching leads:', error);
            loadingMessage.style.display = 'none';
            noLeadsMessage.textContent = `Error loading leads: ${error.message}. Please try again later.`;
            noLeadsMessage.style.display = 'block';
            noLeadsMessage.style.color = 'red';
        }
    };

    const displaySearchInfo = (leadWithSearchInfo) => {
        if (leadWithSearchInfo && leadWithSearchInfo.search_performed_on) {
            searchDateSpan.textContent = new Date(leadWithSearchInfo.search_performed_on).toLocaleString();
        }
        if (leadWithSearchInfo && leadWithSearchInfo.original_search_criteria) {
            // Pretty print the JSON for readability
            searchCriteriaPre.textContent = JSON.stringify(leadWithSearchInfo.original_search_criteria, null, 2);
        } else {
            searchCriteriaPre.textContent = "N/A";
        }
    };

    const displaySearchInfoFromTaskData = (taskData) => {
        // This function is for when backend sends the original task data directly
        // searchDateSpan can be set to current time or a timestamp from taskData if backend adds it
        searchDateSpan.textContent = new Date().toLocaleString() + " (approx.)";
        searchCriteriaPre.textContent = JSON.stringify(taskData, null, 2);
    };


    const populateTable = (leads) => {
        leadsTableBody.innerHTML = ''; // Clear existing rows

        leads.forEach(lead => {
            const row = leadsTableBody.insertRow();
            row.insertCell().textContent = lead.company_name || 'N/A';
            row.insertCell().textContent = lead.company_number || 'N/A';
            row.insertCell().textContent = lead.person_name || 'N/A';
            row.insertCell().textContent = lead.person_role || 'N/A';
            row.insertCell().textContent = lead.email || 'N/A';
            row.insertCell().textContent = lead.accounting_reference_date || 'N/A';
        });
    };

    const downloadCSV = () => {
        if (leadsData.length === 0) {
            alert("No leads to download.");
            return;
        }

        const headers = [
            "Company Name", "Company Number", "Person Name", "Person Role", "Email",
            "Accounting Ref. Date (Day/Month)", "Search Performed On",
            // Add original search criteria headers - this can get complex if criteria is nested
            // For simplicity, we can stringify the whole criteria object or pick main ones
            "Original Revenue Min", "Original Revenue Max", "Original SIC Codes"
            // Add more criteria fields as needed
        ];

        const csvRows = [headers.join(',')];

        leadsData.forEach(lead => {
            const criteria = lead.original_search_criteria || {};
            const row = [
                `"${(lead.company_name || '').replace(/"/g, '""')}"`, // Escape double quotes
                `"${(lead.company_number || '').replace(/"/g, '""')}"`,
                `"${(lead.person_name || '').replace(/"/g, '""')}"`,
                `"${(lead.person_role || '').replace(/"/g, '""')}"`,
                `"${(lead.email || '').replace(/"/g, '""')}"`,
                `"${(lead.accounting_reference_date || '').replace(/"/g, '""')}"`,
                `"${(new Date(lead.search_performed_on).toLocaleString() || '').replace(/"/g, '""')}"`,
                `"${(criteria.revenueMin || '')}"`,
                `"${(criteria.revenueMax || '')}"`,
                `"${(criteria.sicCodesArray ? criteria.sicCodesArray.join('; ') : '')}"`
            ];
            csvRows.push(row.join(','));
        });

        const csvString = csvRows.join('\n');
        const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        if (link.download !== undefined) { // feature detection
            const url = URL.createObjectURL(blob);
            link.setAttribute('href', url);
            link.setAttribute('download', 'leads.csv');
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        } else {
            alert("CSV download is not supported in your browser.");
        }
    };

    // Initialization
    const taskId = getTaskIdFromUrl();
    if (taskId) {
        fetchLeads(taskId);
    } else {
        loadingMessage.textContent = 'Error: Task ID is missing from the URL.';
        loadingMessage.style.color = 'red';
        console.error("Task ID missing from URL.");
    }

    downloadCsvBtn.addEventListener('click', downloadCSV);
});
