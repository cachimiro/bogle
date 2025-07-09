document.addEventListener('DOMContentLoaded', () => {
    // Configuration
    const WEBHOOK_URL = 'https://hook.eu2.make.com/gk8lgjcb4a5u4mug7389a4h17yd5mced';

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

    const sendToWebhookBtn = document.getElementById('sendToWebhookBtn');
    const feedbackMessageDiv = document.getElementById('feedbackMessage');

    // Summary display elements
    const summaryRevenue = document.getElementById('summaryRevenue');
    const summaryEmployees = document.getElementById('summaryEmployees');
    const summarySicCodes = document.getElementById('summarySicCodes');
    const summaryLocation = document.getElementById('summaryLocation');
    const summaryProfitPerEmployee = document.getElementById('summaryProfitPerEmployee');

    // Initial default values from requirements
    const defaultFilters = {
        revenueMin: 5000000,
        revenueMax: 600000000,
        employeesMin: 30,
        employeesMax: 500,
        sicCodes: "64191", // Default SIC code as a string
        location: "",
        profitPerEmployeeMin: null
    };

    function initializeFilters() {
        revenueMinInput.value = defaultFilters.revenueMin;
        revenueMaxInput.value = defaultFilters.revenueMax;
        employeesMinInput.value = defaultFilters.employeesMin;
        employeesMaxInput.value = defaultFilters.employeesMax;
        sicCodesInput.value = defaultFilters.sicCodes;
        locationInput.value = defaultFilters.location;
        profitPerEmployeeMinInput.value = defaultFilters.profitPerEmployeeMin === null ? '' : defaultFilters.profitPerEmployeeMin;

        // TODO: Initialize sliders here if using a library.
        // For now, input fields will drive the values.

        updateSummary();
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
            location: locationInput.value.trim() === "" ? "" : locationInput.value.trim()
        };
    }

    async function sendDataToWebhook() {
        const filterData = getFilterData();

        feedbackMessageDiv.textContent = '';
        feedbackMessageDiv.className = 'feedback-message'; // Reset classes

        try {
            sendToWebhookBtn.disabled = true;
            sendToWebhookBtn.textContent = 'Sending...';

            const response = await fetch(WEBHOOK_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(filterData),
            });

            if (response.ok) {
                // Assuming Make.com webhook returns 200 OK on success
                const responseBody = await response.text(); // Or response.json() if Make returns JSON
                console.log('Webhook response:', responseBody);
                feedbackMessageDiv.textContent = 'Data sent successfully to webhook!';
                feedbackMessageDiv.classList.add('success');
            } else {
                const errorText = await response.text();
                console.error('Webhook error:', response.status, errorText);
                feedbackMessageDiv.textContent = `Error sending data: ${response.status} ${errorText || response.statusText}`;
                feedbackMessageDiv.classList.add('error');
            }
        } catch (error) {
            console.error('Network or other error:', error);
            feedbackMessageDiv.textContent = `Failed to send data. Check console for details. (${error.message})`;
            feedbackMessageDiv.classList.add('error');
        } finally {
            sendToWebhookBtn.disabled = false;
            sendToWebhookBtn.textContent = 'Send Criteria to Webhook';
        }
    }

    // Event Listeners
    [revenueMinInput, revenueMaxInput, employeesMinInput, employeesMaxInput, sicCodesInput, locationInput, profitPerEmployeeMinInput].forEach(input => {
        input.addEventListener('input', updateSummary);
        input.addEventListener('change', updateSummary); // For number inputs that might change on blur
    });

    sendToWebhookBtn.addEventListener('click', sendDataToWebhook);

    // Initial setup
    initializeFilters();

    // --- Slider Implementation Notes ---
    // For a better UX with sliders, you'd typically use a library like noUiSlider or similar.
    // Example with noUiSlider (conceptual - library would need to be added to the project):
    /*
    if (typeof noUiSlider !== 'undefined') {
        // Revenue Slider
        noUiSlider.create(revenueSlider, {
            start: [defaultFilters.revenueMin, defaultFilters.revenueMax],
            connect: true,
            range: { 'min': 0, 'max': 1000000000 }, // Define overall min/max
            step: 100000, // Define step
            format: {
                to: value => Math.round(value),
                from: value => Number(value)
            }
        });
        revenueSlider.noUiSlider.on('update', (values) => {
            revenueMinInput.value = values[0];
            revenueMaxInput.value = values[1];
            updateSummary();
        });
        revenueMinInput.addEventListener('change', () => revenueSlider.noUiSlider.set([revenueMinInput.value, null]));
        revenueMaxInput.addEventListener('change', () => revenueSlider.noUiSlider.set([null, revenueMaxInput.value]));

        // Employee Slider (similar setup)
        noUiSlider.create(employeeSlider, {
            start: [defaultFilters.employeesMin, defaultFilters.employeesMax],
            connect: true,
            range: { 'min': 0, 'max': 10000 },
            step: 1,
            format: {
                to: value => Math.round(value),
                from: value => Number(value)
            }
        });
        employeeSlider.noUiSlider.on('update', (values) => {
            employeesMinInput.value = values[0];
            employeesMaxInput.value = values[1];
            updateSummary();
        });
        employeesMinInput.addEventListener('change', () => employeeSlider.noUiSlider.set([employeesMinInput.value, null]));
        employeesMaxInput.addEventListener('change', () => employeeSlider.noUiSlider.set([null, employeesMaxInput.value]));
    } else {
        console.warn('noUiSlider library not found. Sliders will not be initialized.');
        // Hide slider placeholders if library not present or provide alternative
        if(document.getElementById('revenueSlider')) document.getElementById('revenueSlider').style.display = 'none';
        if(document.getElementById('employeeSlider')) document.getElementById('employeeSlider').style.display = 'none';
    }
    */
    // For now, the input fields for Min/Max will work directly without graphical sliders.
    // If graphical sliders are desired, a library like noUiSlider should be integrated.
    // Hiding the slider placeholders as no library is currently integrated.
    const revSliderEl = document.getElementById('revenueSlider');
    const empSliderEl = document.getElementById('employeeSlider');
    if (revSliderEl) revSliderEl.style.display = 'none';
    if (empSliderEl) empSliderEl.style.display = 'none';

});
