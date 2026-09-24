/**
 * AssureX Claim Engine - Client-Side Interactive Logic
 * Handles intake wizard steps, dropzone previews, and dashboard utilities.
 */

document.addEventListener("DOMContentLoaded", function () {
    // 1. Initialize Bootstrap Tooltips & Popovers
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (el) {
        return new bootstrap.Tooltip(el);
    });

    // 2. Auto-dismiss Flash Alerts after 6 seconds
    const autoAlerts = document.querySelectorAll(".alert-dismissible");
    autoAlerts.forEach(function (alert) {
        setTimeout(function () {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 6000);
    });

    // 3. Multi-Step Claim Intake Wizard Controller
    const wizardPanes = document.querySelectorAll(".wizard-step-pane");
    const wizardTabs = document.querySelectorAll(".wizard-step-tab");

    window.goToWizardStep = function (stepNumber) {
        // Validate Step 1 before proceeding to Step 2
        if (stepNumber === 2) {
            const productSelect = document.getElementById("product_id");
            if (productSelect && !productSelect.value) {
                alert("Please select a registered product before proceeding.");
                return;
            }
        }

        // Validate Step 2 before proceeding to Step 3
        if (stepNumber === 3) {
            const faultCategory = document.getElementById("fault_category");
            const faultDesc = document.getElementById("fault_description");
            const faultDate = document.getElementById("fault_occurrence_date");
            if (!faultCategory || !faultCategory.value) {
                alert("Please select the defect category.");
                return;
            }
            if (!faultDesc || faultDesc.value.trim().length < 10) {
                alert("Please provide a detailed defect description (minimum 10 characters).");
                return;
            }
            if (!faultDate || !faultDate.value) {
                alert("Please specify the date when the defect occurred.");
                return;
            }
        }

        // Validate Step 3 before proceeding to Step 4
        if (stepNumber === 4) {
            const receiptFile = document.getElementById("invoice_document");
            if (!receiptFile || !receiptFile.files || receiptFile.files.length === 0) {
                alert("Please upload the purchase invoice / receipt document for OCR verification.");
                return;
            }
            // Populate Review Summary in Step 4
            populateReviewSummary();
        }

        // Update active pane
        wizardPanes.forEach(function (pane) {
            pane.classList.remove("active");
        });
        const targetPane = document.getElementById("step-" + stepNumber);
        if (targetPane) {
            targetPane.classList.add("active");
        }

        // Update active tab indicator
        wizardTabs.forEach(function (tab) {
            const tabStep = parseInt(tab.getAttribute("data-step"));
            if (tabStep === stepNumber) {
                tab.classList.add("active");
            } else {
                tab.classList.remove("active");
            }
            if (tabStep < stepNumber) {
                tab.classList.add("completed");
            } else {
                tab.classList.remove("completed");
            }
        });

        // Scroll smoothly to top of wizard
        const wizardCard = document.querySelector(".wizard-container");
        if (wizardCard) {
            wizardCard.scrollIntoView({ behavior: "smooth", block: "start" });
        }
    };

    function populateReviewSummary() {
        const prodSelect = document.getElementById("product_id");
        const prodText = prodSelect ? prodSelect.options[prodSelect.selectedIndex].text : "N/A";
        const catText = document.getElementById("fault_category") ? document.getElementById("fault_category").value : "N/A";
        const dateText = document.getElementById("fault_occurrence_date") ? document.getElementById("fault_occurrence_date").value : "N/A";
        const descText = document.getElementById("fault_description") ? document.getElementById("fault_description").value : "N/A";
        const amountText = document.getElementById("claim_amount") ? document.getElementById("claim_amount").value : "0.00";

        const summaryProd = document.getElementById("summary-product");
        const summaryCat = document.getElementById("summary-category");
        const summaryDate = document.getElementById("summary-date");
        const summaryDesc = document.getElementById("summary-desc");
        const summaryAmount = document.getElementById("summary-amount");

        if (summaryProd) summaryProd.textContent = prodText;
        if (summaryCat) summaryCat.textContent = catText;
        if (summaryDate) summaryDate.textContent = dateText;
        if (summaryDesc) summaryDesc.textContent = descText;
        if (summaryAmount) summaryAmount.textContent = "$" + parseFloat(amountText || 0).toFixed(2);
    }

    // 4. File Dropzone Drag-and-Drop Handler
    const dropzone = document.getElementById("receipt-dropzone");
    const fileInput = document.getElementById("invoice_document");
    const filePreview = document.getElementById("file-preview-info");

    if (dropzone && fileInput) {
        dropzone.addEventListener("click", function () {
            fileInput.click();
        });

        ["dragenter", "dragover"].forEach(function (eventName) {
            dropzone.addEventListener(eventName, function (e) {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.add("dragover");
            }, false);
        });

        ["dragleave", "drop"].forEach(function (eventName) {
            dropzone.addEventListener(eventName, function (e) {
                e.preventDefault();
                e.stopPropagation();
                dropzone.classList.remove("dragover");
            }, false);
        });

        dropzone.addEventListener("drop", function (e) {
            const dt = e.dataTransfer;
            const files = dt.files;
            if (files && files.length > 0) {
                fileInput.files = files;
                updateFilePreview(files[0]);
            }
        });

        fileInput.addEventListener("change", function () {
            if (fileInput.files && fileInput.files.length > 0) {
                updateFilePreview(fileInput.files[0]);
            }
        });
    }

    function updateFilePreview(file) {
        if (!filePreview) return;
        const fileSizeMB = (file.size / (1024 * 1024)).toFixed(2);
        filePreview.innerHTML = `
            <div class="alert alert-success d-flex align-items-center gap-2 mt-3 mb-0">
                <i class="bi bi-file-earmark-check-fill fs-4 text-success"></i>
                <div class="flex-grow-1">
                    <div class="fw-bold">${file.name}</div>
                    <small class="text-muted">Size: ${fileSizeMB} MB | MIME: ${file.type || 'Document'}</small>
                </div>
                <span class="badge bg-primary">Ready for OCR</span>
            </div>
        `;

        // Live OCR extraction preview (Req 1.6.vi & vii)
        const ocrPanel = document.getElementById("ocr-results-panel");
        if (ocrPanel) {
            ocrPanel.innerHTML = `
                <div class="text-center py-2">
                    <div class="spinner-border spinner-border-sm text-primary me-2"></div>
                    <span class="extra-small text-muted">Running live OCR entity extraction & cryptographic hash computation...</span>
                </div>
            `;
            const formData = new FormData();
            formData.append("document", file);
            fetch("/claims/ocr-extract", {
                method: "POST",
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                    const e = data.extracted_entities || {};
                    ocrPanel.innerHTML = `
                        <div class="d-flex justify-content-between align-items-center mb-2 pb-1 border-bottom">
                            <span class="fw-bold small text-slate-800"><i class="bi bi-cpu text-primary me-2"></i>Extracted Data Verification (Req 1.6.vii)</span>
                            <span class="badge bg-success-subtle text-success extra-small">Extracted &amp; Editable</span>
                        </div>
                        <p class="extra-small text-muted mb-3">
                            Review and correct any inaccurate or incomplete values extracted from your invoice before proceeding:
                        </p>
                        <div class="row g-2 extra-small">
                            <div class="col-sm-6 col-md-3">
                                <label class="text-muted d-block extra-small">Invoice / Receipt #</label>
                                <input type="text" class="form-control form-control-sm font-mono" id="wizard_verified_invoice" value="${e.invoice_number || ''}">
                            </div>
                            <div class="col-sm-6 col-md-3">
                                <label class="text-muted d-block extra-small">Purchase Date</label>
                                <input type="date" class="form-control form-control-sm" id="wizard_verified_date" value="${e.purchase_date || ''}">
                            </div>
                            <div class="col-sm-6 col-md-3">
                                <label class="text-muted d-block extra-small">Hardware Serial #</label>
                                <input type="text" class="form-control form-control-sm font-mono text-primary fw-semibold" id="wizard_verified_serial" value="${e.serial_number || ''}">
                            </div>
                            <div class="col-sm-6 col-md-3">
                                <label class="text-muted d-block extra-small">Purchase / Claim Value ($)</label>
                                <input type="number" step="0.01" class="form-control form-control-sm fw-bold text-success" id="wizard_verified_amount" value="${e.purchase_amount ? parseFloat(e.purchase_amount).toFixed(2) : '150.00'}" onchange="if(document.getElementById('claim_amount')) document.getElementById('claim_amount').value = this.value">
                            </div>
                            <div class="col-sm-12 col-md-6 mt-2">
                                <label class="text-muted d-block extra-small">Merchant / Retailer</label>
                                <input type="text" class="form-control form-control-sm" id="wizard_verified_retailer" value="${e.retailer || ''}">
                            </div>
                            <div class="col-sm-12 col-md-6 mt-2">
                                <label class="text-muted d-block extra-small">Cryptographic SHA-256 Digest</label>
                                <input type="text" class="form-control form-control-sm font-mono extra-small bg-white" readonly value="${data.sha256 || 'N/A'}">
                            </div>
                        </div>
                        <div class="alert alert-success d-flex align-items-center gap-2 mt-3 mb-0 py-2 extra-small">
                            <i class="bi bi-check-circle-fill fs-6 text-success"></i>
                            <div>Values verified and synchronized with claim adjudication features.</div>
                        </div>
                    `;

                    // Synchronize verified amount with Step 2 claim amount
                    if (e.purchase_amount && document.getElementById('claim_amount')) {
                        document.getElementById('claim_amount').value = parseFloat(e.purchase_amount).toFixed(2);
                    }
                })
            .catch(err => {
                console.error("Live OCR extraction preview failed:", err);
            });
        }
    }
});

// Top-level global definitions for Demo Credentials & Instant 1-Click Login
window.fillCredentials = function (email, password) {
    var emailInput = document.getElementById("email");
    var passwordInput = document.getElementById("password");
    if (emailInput && passwordInput) {
        emailInput.value = email;
        passwordInput.value = password;
    }
};

window.quickLogin = function (email, password) {
    try {
        var emailInput = document.getElementById("email");
        var passwordInput = document.getElementById("password");
        var form = document.getElementById("loginForm");
        if (emailInput && passwordInput) {
            emailInput.value = email;
            passwordInput.value = password;
        }
        if (form) {
            form.submit();
        }
    } catch(e) {
        console.error("quickLogin error:", e);
    }
};
