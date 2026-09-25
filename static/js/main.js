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
        const selectedOpt = prodSelect && prodSelect.selectedIndex >= 0 ? prodSelect.options[prodSelect.selectedIndex] : null;
        const prodText = selectedOpt && selectedOpt.value ? selectedOpt.text : "No product selected";
        const catText = document.getElementById("fault_category") ? document.getElementById("fault_category").value : "";
        const damageTypeText = document.getElementById("damage_type") ? document.getElementById("damage_type").value : "";
        const dateText = document.getElementById("fault_occurrence_date") ? document.getElementById("fault_occurrence_date").value : "";
        const descText = document.getElementById("fault_description") ? document.getElementById("fault_description").value : "";
        const amountText = document.getElementById("claim_amount") ? document.getElementById("claim_amount").value : "0.00";

        // Structured summary preview
        const summaryProd = document.getElementById("summary-product");
        const summaryCat = document.getElementById("summary-category");
        const summaryDate = document.getElementById("summary-date");
        const summaryDesc = document.getElementById("summary-desc");
        const summaryAmount = document.getElementById("summary-amount");

        if (summaryProd) summaryProd.textContent = prodText;
        if (summaryCat) summaryCat.textContent = catText || "Not specified";
        if (summaryDate) summaryDate.textContent = dateText || "Not specified";
        if (summaryDesc) summaryDesc.textContent = descText || "No details provided";
        if (summaryAmount) summaryAmount.textContent = "$" + parseFloat(amountText || 0).toFixed(2);

        // Req 1.6.xxxiii: Claim Preparation Assistance calculations
        const missingInfo = [];
        const missingDocs = [];
        const contradictions = [];
        const actions = [];
        let score = 100;

        // 1. Missing Information
        if (!selectedOpt || !selectedOpt.value) {
            missingInfo.push("Registered equipment asset must be selected.");
            actions.push("Select an eligible product in Step 1.");
            score -= 25;
        }
        if (!catText) {
            missingInfo.push("Defect category must be chosen.");
            actions.push("Specify failure category in Step 2.");
            score -= 15;
        }
        if (!damageTypeText) {
            missingInfo.push("Suspected damage nature must be indicated.");
            actions.push("Select damage type in Step 2.");
            score -= 10;
        }
        if (!descText || descText.trim().length < 10) {
            missingInfo.push("Fault description is missing or too brief (min 10 chars).");
            actions.push("Provide descriptive explanation of the defect.");
            score -= 15;
        }
        if (!dateText) {
            missingInfo.push("Incident occurrence date is required.");
            actions.push("Provide exact failure date in Step 2.");
            score -= 15;
        }

        // 2. Missing Documents
        const receiptInput = document.getElementById("invoice_document");
        const warrantyCardInput = document.getElementById("warranty_card");
        const damagePhotoInput = document.getElementById("damage_photo");
        const serialPhotoInput = document.getElementById("serial_photo");

        const hasReceipt = receiptInput && receiptInput.files && receiptInput.files.length > 0;
        const hasWarrantyCard = warrantyCardInput && warrantyCardInput.files && warrantyCardInput.files.length > 0;
        const hasDamagePhoto = damagePhotoInput && damagePhotoInput.files && damagePhotoInput.files.length > 0;
        const hasSerialPhoto = serialPhotoInput && serialPhotoInput.files && serialPhotoInput.files.length > 0;

        if (!hasReceipt) {
            missingDocs.push("Purchase Receipt / Tax Invoice");
            actions.push("Attach purchase receipt or invoice for OCR verification.");
            score -= 20;
        }
        if (!hasWarrantyCard) {
            missingDocs.push("Warranty Card / Certificate");
        }
        if (!hasDamagePhoto) {
            missingDocs.push("Fault / Damage Evidence (Photo/Video)");
        }
        if (!hasSerialPhoto) {
            missingDocs.push("Serial-Number Photograph");
        }

        // 3. Approaching Deadlines
        let deadlineHtml = '<span class="text-success"><i class="bi bi-shield-check"></i> Standard active coverage</span>';
        if (selectedOpt && selectedOpt.value) {
            const remaining = parseInt(selectedOpt.getAttribute("data-remaining") || 0);
            const expiry = selectedOpt.getAttribute("data-expiry");
            const status = selectedOpt.getAttribute("data-status");

            if (status === "Expired" || remaining <= 0) {
                deadlineHtml = `<span class="text-danger fw-bold"><i class="bi bi-shield-slash"></i> Warranty Expired on ${expiry}</span>`;
                actions.push("Check if equipment qualifies for extended warranty grace period.");
                score -= 15;
            } else if (remaining <= 30) {
                deadlineHtml = `<span class="text-warning-emphasis fw-bold"><i class="bi bi-clock-history"></i> Approaching Expiry: ${remaining} days remaining (expires ${expiry})</span>`;
                actions.push("Submit claim promptly before upcoming warranty expiration.");
            } else {
                deadlineHtml = `<span class="text-success"><i class="bi bi-shield-check"></i> Active Warranty: ${remaining} days remaining until ${expiry}</span>`;
            }

            // Reporting delay check
            if (dateText) {
                const faultDateObj = new Date(dateText);
                const today = new Date();
                const diffTime = today - faultDateObj;
                const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
                if (diffDays > 30) {
                    deadlineHtml += `<div class="extra-small text-warning mt-1"><i class="bi bi-exclamation-triangle"></i> Reported ${diffDays} days after occurrence. Standard reporting window is 30 days.</div>`;
                    actions.push("Note that delayed reporting may trigger manual review adjudication.");
                }
            }
        }

        // 4. Possible Contradictions
        if (dateText) {
            const faultDateObj = new Date(dateText);
            const today = new Date();
            today.setHours(23, 59, 59, 999);
            if (faultDateObj > today) {
                contradictions.push(`Fault date (${dateText}) is in the future relative to submission.`);
                actions.push("Correct defect occurrence date to a valid past or present calendar date.");
                score -= 25;
            }

            if (selectedOpt && selectedOpt.getAttribute("data-start")) {
                const purchaseDateObj = new Date(selectedOpt.getAttribute("data-start"));
                if (faultDateObj < purchaseDateObj) {
                    contradictions.push(`Fault occurrence date (${dateText}) predates purchase date (${selectedOpt.getAttribute("data-start")}).`);
                    actions.push("Verify fault date against invoice purchase date to resolve chronological contradiction.");
                    score -= 25;
                }
            }
        }

        // Render Quadrant 1: Missing Information
        const missingInfoList = document.getElementById("prep-missing-info-list");
        if (missingInfoList) {
            if (missingInfo.length === 0) {
                missingInfoList.innerHTML = '<li class="text-success"><i class="bi bi-check2"></i> All mandatory form fields completed</li>';
            } else {
                missingInfoList.innerHTML = missingInfo.map(m => `<li class="text-danger fw-semibold"><i class="bi bi-exclamation-circle me-1"></i>${m}</li>`).join("");
            }
        }

        // Render Quadrant 2: Missing Documents
        const missingDocsList = document.getElementById("prep-missing-docs-list");
        if (missingDocsList) {
            if (missingDocs.length === 0) {
                missingDocsList.innerHTML = '<li class="text-success"><i class="bi bi-check2"></i> All recommended evidence files attached</li>';
            } else {
                missingDocsList.innerHTML = missingDocs.map(d => `<li class="text-warning-emphasis"><i class="bi bi-paperclip me-1"></i>Missing: ${d}</li>`).join("");
            }
        }

        // Render Quadrant 3: Approaching Deadlines
        const deadlinesBox = document.getElementById("prep-deadlines-box");
        if (deadlinesBox) {
            deadlinesBox.innerHTML = deadlineHtml;
        }

        // Render Quadrant 4: Possible Contradictions
        const contradictionsList = document.getElementById("prep-contradictions-list");
        if (contradictionsList) {
            if (contradictions.length === 0) {
                contradictionsList.innerHTML = '<li class="text-success"><i class="bi bi-check2"></i> Chronological sequence verified (purchase &rarr; incident &rarr; submission)</li>';
            } else {
                contradictionsList.innerHTML = contradictions.map(c => `<li class="text-danger fw-semibold"><i class="bi bi-shield-slash me-1"></i>${c}</li>`).join("");
            }
        }

        // Render Recommended Corrective Actions
        const actionsList = document.getElementById("prep-actions-list");
        if (actionsList) {
            if (actions.length === 0) {
                actionsList.innerHTML = '<li class="text-success"><i class="bi bi-check-circle-fill me-1"></i>Dossier is complete and ready. Proceed to final review and submit for evaluation.</li>';
            } else {
                actionsList.innerHTML = actions.map(a => `<li class="text-slate-800"><i class="bi bi-arrow-right-short text-primary fw-bold"></i>${a}</li>`).join("");
            }
        }

        // Render Readiness Meter
        score = Math.max(10, Math.min(100, score));
        const badge = document.getElementById("prep-readiness-badge");
        const bar = document.getElementById("prep-readiness-bar");
        if (badge) {
            badge.textContent = `${score}% Ready`;
            if (score >= 85) {
                badge.className = "badge bg-success-subtle text-success border border-success-subtle fs-6 font-mono";
            } else if (score >= 60) {
                badge.className = "badge bg-warning-subtle text-warning-emphasis border border-warning-subtle fs-6 font-mono";
            } else {
                badge.className = "badge bg-danger-subtle text-danger border border-danger-subtle fs-6 font-mono";
            }
        }
        if (bar) {
            bar.style.width = `${score}%`;
            if (score >= 85) {
                bar.className = "progress-bar bg-success";
            } else if (score >= 60) {
                bar.className = "progress-bar bg-warning";
            } else {
                bar.className = "progress-bar bg-danger";
            }
        }
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
                    if (!data.success) {
                        if (fileInput) fileInput.value = "";
                        filePreview.innerHTML = `
                            <div class="alert alert-danger d-flex align-items-center gap-2 mt-3 mb-0">
                                <i class="bi bi-exclamation-octagon-fill fs-4 text-danger"></i>
                                <div class="flex-grow-1">
                                    <div class="fw-bold">Document Rejected: ${file.name}</div>
                                    <small>${data.error || 'No valid receipt or invoice information was found in this image. Please upload a clear purchase invoice.'}</small>
                                </div>
                                <span class="badge bg-danger">Rejected</span>
                            </div>
                        `;
                        ocrPanel.innerHTML = `
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <span class="fw-bold small text-danger"><i class="bi bi-exclamation-triangle-fill me-2"></i>Document Extraction Failed</span>
                                <span class="badge bg-danger extra-small">Not Accepted</span>
                            </div>
                            <p class="extra-small text-muted mb-0">
                                The uploaded file does not contain recognizable invoice or receipt details and was not accepted. Please upload a valid purchase receipt or invoice document.
                            </p>
                        `;
                        return;
                    }

                    const e = data.entities || data.extracted_entities || {};
                    ocrPanel.innerHTML = `
                        <div class="d-flex justify-content-between align-items-center mb-2 pb-1 border-bottom">
                            <span class="fw-bold small text-slate-800"><i class="bi bi-cpu text-primary me-2"></i>Extracted Data Verification</span>
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
                if (fileInput) fileInput.value = "";
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
