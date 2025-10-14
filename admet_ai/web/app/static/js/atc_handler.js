// ATC Code handling
document.addEventListener('DOMContentLoaded', function() {
    const atcSelect = document.getElementById('atc-code-select');
    if (atcSelect) {
        atcSelect.addEventListener('change', function() {
            updateATCCode(this.value);
        });
    }
});

function updateATCCode(atcCode) {
    fetch(`/set_atc_code?atc_code=${encodeURIComponent(atcCode)}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        }
    })
    .then(response => response.json())
    .then(data => {
        // Update DrugBank size display
        const sizeElement = document.getElementById('drugbank-size');
        if (sizeElement && data.drugbank_size_string) {
            sizeElement.textContent = data.drugbank_size_string;
        }
        
        // Update DrugBank plot if predictions exist
        updateDrugBankPlot();
    })
    .catch(error => console.error('Error:', error));
}

function updateDrugBankPlot() {
    const xTask = document.getElementById('drugbank-x-task').value;
    const yTask = document.getElementById('drugbank-y-task').value;
    
    fetch(`/drugbank_plot?x_task=${encodeURIComponent(xTask)}&y_task=${encodeURIComponent(yTask)}`)
        .then(response => response.json())
        .then(data => {
            const plotContainer = document.getElementById('drugbank-plot');
            if (plotContainer && data.svg) {
                plotContainer.innerHTML = data.svg;
            }
        })
        .catch(error => console.error('Error:', error));
}