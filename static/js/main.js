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
                if (data.success && data.entities) {
                    const e = data.entities;
                    ocrPanel.innerHTML = `
                        <div class="d-flex justify-content-between align-items-center mb-2 pb-1 border-bottom">
                            <span class="fw-bold small text-slate-800"><i class="bi bi-cpu text-primary me-2"></i>Live OCR Extraction Results (Req 1.6.vi)</span>
                            <span class="badge bg-success-subtle text-success extra-small">Verified</span>
                        </div>
                        <div class="row g-2 extra-small">
                            <div class="col-sm-4">
                                <span class="text-muted d-block">Invoice #:</span>
                                <strong class="font-mono text-dark">${e.invoice_number || 'N/A'}</strong>
                            </div>
                            <div class="col-sm-4">
                                <span class="text-muted d-block">Purchase Date:</span>
                                <strong class="text-dark">${e.purchase_date || 'N/A'}</strong>
                            </div>
                            <div class="col-sm-4">
                                <span class="text-muted d-block">Serial Number:</span>
                                <strong class="font-mono text-primary">${e.serial_number || 'N/A'}</strong>
                            </div>
                            <div class="col-sm-4">
                                <span class="text-muted d-block">Purchase Price:</span>
                                <strong class="text-success">$${e.purchase_amount ? parseFloat(e.purchase_amount).toFixed(2) : '0.00'}</strong>
                            </div>
                            <div class="col-sm-8">
                                <span class="text-muted d-block">Merchant / Retailer:</span>
                                <strong class="text-dark">${e.retailer || 'N/A'}</strong>
                            </div>
                            <div class="col-12 mt-1">
                                <span class="text-muted d-block">SHA-256 Digest:</span>
                                <code class="extra-small text-secondary">${data.sha256 || 'N/A'}</code>
                            </div>
                        </div>
                    `;
                }
            })
            .catch(err => {
                console.error("Live OCR extraction preview failed:", err);
            });
        }
    }

    // 5. Quick Demo Credentials Auto-Fill & Instant 1-Click Login
    window.fillCredentials = function (email, password) {
        const emailInput = document.getElementById("email");
        const passwordInput = document.getElementById("password");
        if (emailInput && passwordInput) {
            emailInput.value = email;
            passwordInput.value = password;
        }
    };

    window.quickLogin = function (email, password) {
        const emailInput = document.getElementById("email");
        const passwordInput = document.getElementById("password");
        const form = document.getElementById("loginForm");
        if (emailInput && passwordInput) {
            emailInput.value = email;
            passwordInput.value = password;
        }
        if (form) {
            form.submit();
        }
    };
});
