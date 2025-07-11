document.addEventListener('DOMContentLoaded', () => {
    // Configuration
    const SUBMIT_CRITERIA_URL = '/api/submit_criteria'; // Updated to new backend endpoint

    // DOM Elements
    const revenueMinInput = document.getElementById('revenueMin');
    const revenueMaxInput = document.getElementById('revenueMax');
    // TODO: Implement or integrate a slider library for revenueSlider
    // const revenueSlider = document.getElementById('revenueSlider');

    const employeesMinInput = document.getElementById('employeesMin');
    const employeesMaxInput = document.getElementById('employeesMax');
    // TODO: Implement or integrate a slider library for employeeSlider
    // const employeeSlider = document.getElementById('employeeSlider');

    const sicCodesInput = document.getElementById('sicCodes');
    const locationInput = document.getElementById('location');
    const profitPerEmployeeMinInput = document.getElementById('profitPerEmployeeMin');
    const phoneNumberInput = document.getElementById('phoneNumber');

    // Budget End Date elements
    const budgetEndMonthRadio = document.getElementById('budgetEndMonthRadio');
    const budgetEndRangeRadio = document.getElementById('budgetEndRangeRadio');
    const budgetEndMonthSelectorDiv = document.getElementById('budgetEndMonthSelector');
    const budgetEndRangeSelectorDiv = document.getElementById('budgetEndRangeSelector');
    const budgetEndMonthInput = document.getElementById('budgetEndMonth');
    const budgetEndStartDateInput = document.getElementById('budgetEndStartDate');
    const budgetEndEndDateInput = document.getElementById('budgetEndEndDate');

    const sendToWebhookBtn = document.getElementById('sendToWebhookBtn');
    const feedbackMessageDiv = document.getElementById('feedbackMessage');

    // Summary display elements
    const summaryRevenue = document.getElementById('summaryRevenue');
    const summaryEmployees = document.getElementById('summaryEmployees');
    const summarySicCodes = document.getElementById('summarySicCodes');
    const summaryLocation = document.getElementById('summaryLocation');
    const summaryProfitPerEmployee = document.getElementById('summaryProfitPerEmployee');
    const summaryPhoneNumber = document.getElementById('summaryPhoneNumber');
    const summaryBudgetEndDate = document.getElementById('summaryBudgetEndDate'); // Added Budget End Date summary

    // Initial default values from requirements
    const defaultFilters = {
        revenueMin: 5000000,
        revenueMax: 600000000,
        employeesMin: 30,
        employeesMax: 500,
        sicCodes: "64191",
        location: "",
        profitPerEmployeeMin: null,
        phoneNumber: "",
        budgetEndDateSearchType: "month", // Default search type
        budgetEndMonth: "",
        budgetEndStartDate: "",
        budgetEndEndDate: ""
    };

    function initializeFilters() {
        revenueMinInput.value = defaultFilters.revenueMin;
        revenueMaxInput.value = defaultFilters.revenueMax;
        employeesMinInput.value = defaultFilters.employeesMin;
        employeesMaxInput.value = defaultFilters.employeesMax;
        sicCodesInput.value = defaultFilters.sicCodes;
        locationInput.value = defaultFilters.location;
        profitPerEmployeeMinInput.value = defaultFilters.profitPerEmployeeMin === null ? '' : defaultFilters.profitPerEmployeeMin;
        phoneNumberInput.value = defaultFilters.phoneNumber;

        // Budget End Date Filters
        budgetEndMonthRadio.checked = defaultFilters.budgetEndDateSearchType === 'month';
        budgetEndRangeRadio.checked = defaultFilters.budgetEndDateSearchType === 'range';
        budgetEndMonthInput.value = defaultFilters.budgetEndMonth;
        budgetEndStartDateInput.value = defaultFilters.budgetEndStartDate;
        budgetEndEndDateInput.value = defaultFilters.budgetEndEndDate;
        toggleBudgetEndSelectors(); // Show/hide based on initial radio state

        updateSummary();
    }

    function toggleBudgetEndSelectors() {
        if (budgetEndMonthRadio.checked) {
            budgetEndMonthSelectorDiv.style.display = 'block';
            budgetEndRangeSelectorDiv.style.display = 'none';
        } else if (budgetEndRangeRadio.checked) {
            budgetEndMonthSelectorDiv.style.display = 'none';
            budgetEndRangeSelectorDiv.style.display = 'block';
        }
    }

    function updateSummary() {
        const currentRevenueMin = revenueMinInput.value ? parseInt(revenueMinInput.value, 10).toLocaleString() : 'N/A';
        const currentRevenueMax = revenueMaxInput.value ? parseInt(revenueMaxInput.value, 10).toLocaleString() : 'N/A';
        summaryRevenue.textContent = `£${currentRevenueMin} - £${currentRevenueMax}`;

        const currentEmployeesMin = employeesMinInput.value || 'N/A';
        const currentEmployeesMax = employeesMaxInput.value || 'N/A';
        summaryEmployees.textContent = `${currentEmployeesMin} - ${currentEmployeesMax}`;

        summarySicCodes.textContent = sicCodesInput.value || 'Not set';
        summaryLocation.textContent = locationInput.value || 'Not set';
        summaryProfitPerEmployee.textContent = profitPerEmployeeMinInput.value ? `£${parseInt(profitPerEmployeeMinInput.value, 10).toLocaleString()}` : 'Not set';
        summaryPhoneNumber.textContent = phoneNumberInput.value || 'Not set';

        // Budget End Date Summary
        if (budgetEndMonthRadio.checked && budgetEndMonthInput.value) {
            const monthName = budgetEndMonthInput.options[budgetEndMonthInput.selectedIndex].text;
            summaryBudgetEndDate.textContent = `Month: ${monthName}`;
        } else if (budgetEndRangeRadio.checked && (budgetEndStartDateInput.value || budgetEndEndDateInput.value)) {
            summaryBudgetEndDate.textContent = `Range: ${budgetEndStartDateInput.value || 'N/A'} to ${budgetEndEndDateInput.value || 'N/A'}`;
        } else {
            summaryBudgetEndDate.textContent = 'Not set';
        }
    }

    function getFilterData() {
        const sicCodesValue = sicCodesInput.value.trim();
        let sicCodesArray = [];
        if (sicCodesValue) {
            sicCodesArray = sicCodesValue.split(',')
                                     .map(code => code.trim())
                                     .filter(code => code !== "");
        }

        return {
            revenueMin: revenueMinInput.value ? parseInt(revenueMinInput.value, 10) : null,
            revenueMax: revenueMaxInput.value ? parseInt(revenueMaxInput.value, 10) : null,
            employeesMin: employeesMinInput.value ? parseInt(employeesMinInput.value, 10) : null,
            employeesMax: employeesMaxInput.value ? parseInt(employeesMaxInput.value, 10) : null,
            profitPerEmployeeMin: profitPerEmployeeMinInput.value ? parseInt(profitPerEmployeeMinInput.value, 10) : null,
            sicCodesArray: sicCodesArray,
            location: locationInput.value.trim() === "" ? "" : locationInput.value.trim(),
            phoneNumber: phoneNumberInput.value.trim(),
            budgetEndDateSearchType: budgetEndMonthRadio.checked ? "month" : "range",
            budgetEndMonth: budgetEndMonthRadio.checked ? (budgetEndMonthInput.value || null) : null,
            budgetEndStartDate: budgetEndRangeRadio.checked ? (budgetEndStartDateInput.value || null) : null,
            budgetEndEndDate: budgetEndRangeRadio.checked ? (budgetEndEndDateInput.value || null) : null
        };
    }

    async function sendDataToWebhook() {
        const filterData = getFilterData();

        // Basic validation for phone number
        if (!filterData.phoneNumber) {
            feedbackMessageDiv.textContent = 'Please enter a phone number.';
            feedbackMessageDiv.className = 'feedback-message error';
            phoneNumberInput.focus();
            return;
        }

        feedbackMessageDiv.textContent = '';
        feedbackMessageDiv.className = 'feedback-message'; // Reset classes

        try {
            sendToWebhookBtn.disabled = true;
            sendToWebhookBtn.textContent = 'Sending...';

            const response = await fetch(SUBMIT_CRITERIA_URL, { // Changed to SUBMIT_CRITERIA_URL
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(filterData),
            });

            const responseData = await response.json(); // Expecting JSON response from our backend

            if (response.ok && responseData.status === 'success') {
                console.log('Backend response:', responseData);
                // Redirect to confirmation page on success
                window.location.href = 'confirmation.html';
            } else {
                console.error('Backend error:', response.status, responseData);
                const errorMessage = responseData.message || `Error: ${response.status}`;
                feedbackMessageDiv.textContent = `Error submitting criteria: ${errorMessage}`;
                feedbackMessageDiv.classList.add('error');
            }
        } catch (error) {
            console.error('Network or other error:', error);
            feedbackMessageDiv.textContent = `Failed to send data. Check console for details. (${error.message})`;
            feedbackMessageDiv.classList.add('error');
        } finally {
            sendToWebhookBtn.disabled = false;
            sendToWebhookBtn.textContent = 'Send Request'; // Ensure button text is correct
        }
    }

    // Event Listeners
    const inputsToTrack = [
        revenueMinInput, revenueMaxInput, employeesMinInput, employeesMaxInput,
        sicCodesInput, locationInput, profitPerEmployeeMinInput, phoneNumberInput,
        budgetEndMonthInput, budgetEndStartDateInput, budgetEndEndDateInput
    ];

    inputsToTrack.forEach(input => {
        if (input) { // Check if element exists
            input.addEventListener('input', updateSummary);
            input.addEventListener('change', updateSummary);
        }
    });

    [budgetEndMonthRadio, budgetEndRangeRadio].forEach(radio => {
        if (radio) {
            radio.addEventListener('change', () => {
                toggleBudgetEndSelectors();
                updateSummary(); // Update summary when radio changes
            });
        }
    });

    sendToWebhookBtn.addEventListener('click', sendDataToWebhook);

    // Initial setup
    initializeFilters();

    // Hiding the graphical slider placeholders as no library is currently integrated.
    const revSliderEl = document.getElementById('revenueSlider');
    const empSliderEl = document.getElementById('employeeSlider');
    if (revSliderEl) revSliderEl.style.display = 'none';
    if (empSliderEl) empSliderEl.style.display = 'none';

});
