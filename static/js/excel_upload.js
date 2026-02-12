// Excel Upload Handler

document.addEventListener('DOMContentLoaded', function() {
    const uploadForm = document.getElementById('excelUploadForm');
    const fileInput = document.getElementById('excelFile');
    const uploadBtn = document.getElementById('uploadBtn');
    const resultsDiv = document.getElementById('uploadResults');
    
    if (!uploadForm) return;
    
    fileInput.addEventListener('change', function() {
        const file = this.files[0];
        if (file) {
            const fileName = file.name;
            const fileSize = (file.size / 1024).toFixed(2);
            document.getElementById('fileName').textContent = `${fileName} (${fileSize} KB)`;
        }
    });
    
    uploadForm.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const file = fileInput.files[0];
        if (!file) {
            alert('Please select a file');
            return;
        }
        
        // Show loading
        uploadBtn.disabled = true;
        uploadBtn.textContent = 'Uploading...';
        resultsDiv.innerHTML = '<div class="spinner"></div>';
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const response = await fetch('/admin/students/upload', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (data.success) {
                let resultHtml = `
                    <div class="alert alert-success">
                        <strong>Success!</strong> ${data.message}
                        <br>
                        <small>Students added: ${data.details.success}</small>
                        ${data.details.failed > 0 ? `<br><small>Failed: ${data.details.failed}</small>` : ''}
                    </div>
                `;
                
                // Display credentials
                if (data.details.credentials && data.details.credentials.length > 0) {
                    resultHtml += `
                        <div class="card" style="margin-top: 1rem; background-color: #d1f4ff; border-left: 4px solid #0ea5e9;">
                            <h4 style="color: #0c4a6e; margin-bottom: 1rem;">✅ Student Login Credentials</h4>
                            <p style="color: #0c4a6e; margin-bottom: 0.5rem;">
                                <strong>Login Instructions:</strong>
                            </p>
                            <ul style="color: #0c4a6e; margin-bottom: 1rem;">
                                <li><strong>Username:</strong> Student's PRN</li>
                                <li><strong>Password:</strong> Student's Phone Number</li>
                            </ul>
                            <button onclick="downloadCredentials()" class="btn btn-primary" style="margin-bottom: 1rem;">
                                Download Credentials as CSV
                            </button>
                            <div style="max-height: 300px; overflow-y: auto;">
                                <table style="width: 100%; border-collapse: collapse;">
                                    <thead style="background-color: #0ea5e9; color: white; position: sticky; top: 0;">
                                        <tr>
                                            <th style="padding: 0.5rem; border: 1px solid #ddd;">PRN (Username)</th>
                                            <th style="padding: 0.5rem; border: 1px solid #ddd;">Name</th>
                                            <th style="padding: 0.5rem; border: 1px solid #ddd;">Phone (Password)</th>
                                            <th style="padding: 0.5rem; border: 1px solid #ddd;">Email</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                    `;
                    
                    data.details.credentials.forEach(cred => {
                        resultHtml += `
                            <tr>
                                <td style="padding: 0.5rem; border: 1px solid #ddd;"><strong>${cred.username}</strong></td>
                                <td style="padding: 0.5rem; border: 1px solid #ddd;">${cred.name}</td>
                                <td style="padding: 0.5rem; border: 1px solid #ddd;"><strong>${cred.password}</strong></td>
                                <td style="padding: 0.5rem; border: 1px solid #ddd;">${cred.email}</td>
                            </tr>
                        `;
                    });
                    
                    resultHtml += `
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    `;
                    
                    // Store credentials globally for download
                    window.studentCredentials = data.details.credentials;
                }
                
                resultsDiv.innerHTML = resultHtml;
                
                if (data.details.errors.length > 0) {
                    let errorHtml = '<div class="alert alert-error" style="margin-top: 1rem;"><strong>Errors:</strong><ul>';
                    data.details.errors.forEach(error => {
                        errorHtml += `<li>${error}</li>`;
                    });
                    errorHtml += '</ul></div>';
                    resultsDiv.innerHTML += errorHtml;
                }
                
                // Reset form
                uploadForm.reset();
                document.getElementById('fileName').textContent = 'No file selected';
                
                // Don't auto-reload anymore so users can save credentials
                // setTimeout(() => {
                //     window.location.reload();
                // }, 3000);
            } else {
                resultsDiv.innerHTML = `
                    <div class="alert alert-error">
                        <strong>Error!</strong> ${data.message}
                    </div>
                `;
            }
        } catch (error) {
            resultsDiv.innerHTML = `
                <div class="alert alert-error">
                    <strong>Error!</strong> Failed to upload file. ${error.message}
                </div>
            `;
        } finally {
            uploadBtn.disabled = false;
            uploadBtn.textContent = 'Upload Students';
        }
    });
});

// Download Sample Excel Template
function downloadSampleTemplate() {
    const sampleData = [
        ['PRN', 'Name', 'Branch', 'Email', 'Phone', 'Consultancy', 'Total_Fees'],
        ['2023001', 'John Doe', 'Computer Science', 'john@example.com', '9876543210', 'ABC Consultancy', '50000'],
        ['2023002', 'Jane Smith', 'Electronics', 'jane@example.com', '9876543211', 'ABC Consultancy', '45000']
    ];
    
    let csv = sampleData.map(row => row.join(',')).join('\n');
    
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'student_template.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
}

// Download Student Credentials
function downloadCredentials() {
    if (!window.studentCredentials || window.studentCredentials.length === 0) {
        alert('No credentials to download');
        return;
    }
    
    const headers = ['PRN (Username)', 'Name', 'Phone (Password)', 'Email', 'Login Instructions'];
    const rows = window.studentCredentials.map(cred => [
        cred.username,
        cred.name,
        cred.password,
        cred.email,
        'Username: PRN | Password: Phone Number'
    ]);
    
    let csv = [headers, ...rows].map(row => row.join(',')).join('\n');
    
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const timestamp = new Date().toISOString().split('T')[0];
    a.download = `student_credentials_${timestamp}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
    
    alert('Credentials downloaded! Students can login with:\nUsername: Their PRN\nPassword: Their Phone Number');
}